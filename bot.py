# -*- coding: utf-8 -*-
"""
QR MASTER — Hamma narsa bitta faylda
Ishga tushirish: python bot.py
"""
import os, sys, hmac, hashlib, json, threading, time, sqlite3, io
from datetime import datetime
from functools import wraps
from urllib.parse import parse_qsl


# ═══════════════════════════════════════════════════════════
# AVTOMATIK O'RNATISH
# ═══════════════════════════════════════════════════════════
def ensure_packages():
    pkgs = {
        "telebot": "pyTelegramBotAPI",
        "flask": "Flask",
        "flask_cors": "Flask-Cors",
        "qrcode": "qrcode[pil]",
        "PIL": "Pillow",
    }
    missing = []
    import importlib
    for mod, pkg in pkgs.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"📦 O'rnatilmoqda: {', '.join(missing)}")
        import subprocess
        for pkg in missing:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        print("✅ O'rnatildi! Qayta ishga tushirilmoqda...\n")
        import time; time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)


ensure_packages()

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand, InputFile
)
import qrcode


# ═══════════════════════════════════════════════════════════
# SOZLAMALAR — FAQAT SHU YERNI O'ZGARTIRING!
# ═══════════════════════════════════════════════════════════
BOT_TOKEN    = os.getenv("BOT_TOKEN", "8894647397:AAHpIC0PyVsjQ_XgDZOZGAVdOemN9YSBnMA")
BOT_USERNAME = os.getenv("BOT_USERNAME", "SizningBotUsername")
WEBAPP_URL   = os.getenv("WEBAPP_URL", "http://localhost:8000")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "8261542613").split(",")]
MONETAG_ZONE = os.getenv("MONETAG_ZONE", "11990967")
PORT         = int(os.getenv("PORT", 8000))
DB_FILE      = os.getenv("DB_FILE", "qr_master.db")
# ═══════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════
def db_init():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        telegram_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        last_name TEXT, language TEXT DEFAULT 'uz', referrer_id INTEGER,
        status TEXT DEFAULT 'active', qr_count INTEGER DEFAULT 0,
        ad_count INTEGER DEFAULT 0, created_at TEXT, last_active TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS qr_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, qr_type TEXT,
        name TEXT, qr_data TEXT, payload_hash TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS channels(
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, name TEXT,
        username TEXT, invite_link TEXT, check_mode TEXT DEFAULT 'member',
        is_active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals(
        id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER,
        referred_id INTEGER UNIQUE, status TEXT DEFAULT 'active', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS support_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, message TEXT,
        admin_reply TEXT, status TEXT DEFAULT 'open', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ad_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, format TEXT,
        event_type TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS admins(
        telegram_id INTEGER PRIMARY KEY, added_by INTEGER, created_at TEXT)""")

    defaults = {
        "force_sub_enabled": "0", "referral_enabled": "1",
        "monetag_enabled": "1", "free_qr_count": "3", "qr_per_ad": "5",
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    conn.commit(); conn.close()


def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting(key, default=""):
    conn = db()
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return r["value"] if r else default


def set_setting(key, value):
    conn = db()
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))
    conn.commit(); conn.close()


def is_admin(uid):
    if uid in ADMIN_IDS: return True
    conn = db()
    r = conn.execute("SELECT 1 FROM admins WHERE telegram_id=?", (uid,)).fetchone()
    conn.close()
    return bool(r)


def get_user(tg_id):
    conn = db()
    r = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tg_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def upsert_user(tg):
    conn = db()
    e = conn.execute("SELECT 1 FROM users WHERE telegram_id=?", (tg["id"],)).fetchone()
    now = datetime.utcnow().isoformat()
    if not e:
        conn.execute("""INSERT INTO users(telegram_id,username,first_name,last_name,
            language,created_at,last_active) VALUES(?,?,?,?,?,?,?)""",
            (tg["id"], tg.get("username"), tg.get("first_name"),
             tg.get("last_name"), tg.get("language_code", "uz"), now, now))
        is_new = True
    else:
        conn.execute("""UPDATE users SET username=?,first_name=?,last_name=?,
            last_active=? WHERE telegram_id=?""",
            (tg.get("username"), tg.get("first_name"), tg.get("last_name"),
             now, tg["id"]))
        is_new = False
    conn.commit(); conn.close()
    return is_new


def add_qr(user_id, qr_type, name, qr_data):
    conn = db()
    conn.execute("""INSERT INTO qr_history(user_id,qr_type,name,qr_data,
        payload_hash,created_at) VALUES(?,?,?,?,?,?)""",
        (user_id, qr_type, name, qr_data,
         hashlib.sha256(qr_data.encode()).hexdigest(),
         datetime.utcnow().isoformat()))
    conn.execute("UPDATE users SET qr_count=qr_count+1 WHERE telegram_id=?", (user_id,))
    conn.commit(); conn.close()


def get_qrs(user_id, limit=50, offset=0):
    conn = db()
    rows = conn.execute("""SELECT id,qr_type,name,qr_data,created_at FROM qr_history
        WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (user_id, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_qrs(user_id):
    conn = db()
    r = conn.execute("SELECT COUNT(*) FROM qr_history WHERE user_id=?", (user_id,)).fetchone()[0]
    conn.close()
    return r


def del_qr(qr_id, user_id):
    conn = db()
    r = conn.execute("SELECT 1 FROM qr_history WHERE id=? AND user_id=?",
                     (qr_id, user_id)).fetchone()
    if r:
        conn.execute("DELETE FROM qr_history WHERE id=?", (qr_id,))
        conn.execute("UPDATE users SET qr_count=MAX(0,qr_count-1) WHERE telegram_id=?",
                     (user_id,))
        conn.commit(); conn.close()
        return True
    conn.close()
    return False


def add_ref(referrer, referred):
    if referrer == referred: return False
    conn = db()
    try:
        conn.execute("INSERT INTO referrals(referrer_id,referred_id,created_at) VALUES(?,?,?)",
                     (referrer, referred, datetime.utcnow().isoformat()))
        conn.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def count_refs(user_id):
    conn = db()
    t = conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)).fetchone()[0]
    conn.close()
    return t


def get_refs(user_id, limit=10, offset=0):
    conn = db()
    rows = conn.execute("""SELECT r.*, u.first_name, u.username
        FROM referrals r LEFT JOIN users u ON u.telegram_id=r.referred_id
        WHERE r.referrer_id=? ORDER BY r.created_at DESC LIMIT ? OFFSET ?""",
        (user_id, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_channels():
    conn = db()
    rows = conn.execute("SELECT * FROM channels WHERE is_active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def make_qr_png(data):
    qr = qrcode.QRCode(box_size=10, border=4,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO(); img.save(bio, "PNG"); bio.seek(0)
    return bio


db_init()


# ═══════════════════════════════════════════════════════════
# BOT
# ═══════════════════════════════════════════════════════════
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def check_sub(uid):
    if get_setting("force_sub_enabled") != "1": return True
    for ch in get_channels():
        try:
            m = bot.get_chat_member(ch["chat_id"], uid)
            if m.status in ("left", "kicked"): return False
        except: pass
    return True


def sub_prompt(chat_id):
    channels = get_channels()
    if not channels: return
    text = "🔒 <b>Obuna bo'ling:</b>\n\n"
    kb = InlineKeyboardMarkup()
    for i, ch in enumerate(channels, 1):
        text += f"{i}. <b>{ch['name']}</b>\n"
        link = ch["invite_link"] or f"https://t.me/{ch['username']}"
        if link: kb.add(InlineKeyboardButton(f"📢 {ch['name']}", url=link))
    kb.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    bot.send_message(chat_id, text, reply_markup=kb)


def reply_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("🧩 QR kod yaratish", web_app=WebAppInfo(url=WEBAPP_URL)),
        KeyboardButton("📜 Mening QR larim"),
    )
    kb.add(
        KeyboardButton("👥 Referal tizimi"),
        KeyboardButton("📊 Statistika"),
    )
    kb.add(
        KeyboardButton("✉️ Adminga xabar"),
        KeyboardButton("🌐 Til"),
    )
    return kb


@bot.message_handler(commands=["start"])
def cmd_start(m):
    uid = m.from_user.id
    is_new = upsert_user({
        "id": uid, "username": m.from_user.username,
        "first_name": m.from_user.first_name, "last_name": m.from_user.last_name,
        "language_code": m.from_user.language_code})

    # Referal
    args = m.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
            if is_new and add_ref(ref_id, uid):
                try: bot.send_message(ref_id, "🎉 Yangi referal!")
                except: pass
        except: pass

    if not check_sub(uid):
        sub_prompt(m.chat.id); return

    bot.send_message(m.chat.id,
        f"👋 Salom, <b>{m.from_user.first_name or 'do\'stim'}</b>!\n\n"
        "🎯 <b>QR Master</b> — universal QR kod generator.\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=reply_kb())

    if is_admin(uid):
        bot.send_message(m.chat.id, "👑 Admin panel: /admin")


@bot.message_handler(commands=["admin"])
def cmd_admin(m):
    if not is_admin(m.from_user.id):
        bot.reply_to(m, "🚫 Admin emas"); return
    admin_menu(m.chat.id)


def admin_menu(chat_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Statistika", callback_data="adm_stats"),
        InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm_users:0"),
    )
    kb.add(
        InlineKeyboardButton("📣 Broadcast", callback_data="adm_bc"),
        InlineKeyboardButton("🔒 Obuna", callback_data="adm_subs"),
    )
    kb.add(
        InlineKeyboardButton("👑 Adminlar", callback_data="adm_admins"),
        InlineKeyboardButton("📋 Xabarlar", callback_data="adm_msgs"),
    )
    kb.add(InlineKeyboardButton("📢 Reklama", callback_data="adm_ads"))
    bot.send_message(chat_id, "👑 <b>ADMIN PANEL</b>", reply_markup=kb)


@bot.message_handler(commands=["id"])
def cmd_id(m):
    bot.reply_to(m, f"🆔 <code>{m.from_user.id}</code>")


@bot.message_handler(func=lambda m: m.text == "📜 Mening QR larim")
def my_qrs(m):
    if not check_sub(m.from_user.id):
        sub_prompt(m.chat.id); return
    show_qrs(m.chat.id, m.from_user.id, 0)


def show_qrs(chat_id, uid, offset):
    total = count_qrs(uid)
    if total == 0:
        bot.send_message(chat_id,
            "📜 QR kodlar yo'q.\n\n🧩 Mini App orqali yarating!",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🚀 QR yaratish",
                    web_app=WebAppInfo(url=WEBAPP_URL))))
        return

    qrs = get_qrs(uid, 5, offset)
    text = f"📜 <b>Sizning QR kodlaringiz</b> ({offset+1}-{offset+len(qrs)}/{total})\n\n"
    for i, q in enumerate(qrs, 1):
        text += f"{offset+i}. <b>{q['name']}</b>\n"
        text += f"   <code>{q['qr_data'][:40]}...</code>\n\n"

    kb = InlineKeyboardMarkup(row_width=4)
    for q in qrs:
        kb.add(
            InlineKeyboardButton(f"📥 #{q['id']}", callback_data=f"qr_dl:{q['id']}"),
            InlineKeyboardButton(f"🗑 #{q['id']}", callback_data=f"qr_del:{q['id']}")
        )

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"qr_pg:{offset-5}"))
    if offset + 5 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"qr_pg:{offset+5}"))
    if nav: kb.row(*nav)

    bot.send_message(chat_id, text, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "👥 Referal tizimi")
def ref_menu(m):
    uid = m.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    total = count_refs(uid)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📋 Nusxalash", callback_data="copy_ref"))
    kb.add(InlineKeyboardButton("📤 Ulashish",
        url=f"https://t.me/share/url?url={link}&text=QR Master"))
    if total > 0:
        kb.add(InlineKeyboardButton(f"👥 Ro'yxat ({total})", callback_data="ref_list:0"))
    bot.send_message(m.chat.id,
        f"👥 <b>Referal tizimi</b>\n\n"
        f"🔗 <code>{link}</code>\n\n"
        f"📊 Jami: <b>{total}</b>",
        reply_markup=kb)


def show_refs(chat_id, uid, offset, msg_id=None):
    total = count_refs(uid)
    refs = get_refs(uid, 10, offset)
    text = f"👥 <b>Referallar</b> ({offset+1}-{offset+len(refs)}/{total})\n\n"
    for i, r in enumerate(refs, 1):
        name = r.get("first_name") or "Foydalanuvchi"
        uname = f"@{r['username']}" if r.get("username") else "—"
        text += f"{offset+i}. {name} ({uname})\n"

    kb = InlineKeyboardMarkup()
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"ref_list:{offset-10}"))
    nav.append(InlineKeyboardButton("🔙", callback_data="ref_back"))
    if offset + 10 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"ref_list:{offset+10}"))
    kb.row(*nav)

    if msg_id:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def stats_menu(m):
    uid = m.from_user.id
    u = get_user(uid)
    refs = count_refs(uid)
    bot.send_message(m.chat.id,
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"🆔 <code>{uid}</code>\n"
        f"👤 {u['first_name'] or '—'}\n"
        f"🧩 QR: <b>{u['qr_count']}</b>\n"
        f"📢 Reklama: <b>{u['ad_count']}</b>\n"
        f"👥 Referallar: <b>{refs}</b>")


@bot.message_handler(func=lambda m: m.text == "✉️ Adminga xabar")
def support(m):
    msg = bot.send_message(m.chat.id, "✉️ Xabaringizni yozing:")
    bot.register_next_step_handler(msg, save_msg)


def save_msg(message):
    if message.content_type != "text":
        bot.reply_to(message, "❌ Matn"); return
    uid = message.from_user.id
    conn = db()
    conn.execute("INSERT INTO support_messages(user_id,message,created_at) VALUES(?,?,?)",
                 (uid, message.text, datetime.utcnow().isoformat()))
    mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit(); conn.close()
    bot.reply_to(message, "✅ Yuborildi!")
    for admin_id in ADMIN_IDS:
        try:
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("💬 Javob", callback_data=f"reply:{mid}"))
            bot.send_message(admin_id,
                f"✉️ <b>#{mid}</b> | @{message.from_user.username or '—'}\n\n{message.text}",
                reply_markup=kb)
        except: pass


@bot.message_handler(func=lambda m: m.text == "🌐 Til")
def lang_menu(m):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("🇺🇿 UZ", callback_data="lang:uz"),
        InlineKeyboardButton("🇷🇺 RU", callback_data="lang:ru"),
        InlineKeyboardButton("🇬🇧 EN", callback_data="lang:en"))
    bot.send_message(m.chat.id, "🌐 Til:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    uid = call.from_user.id
    data = call.data
    bot.answer_callback_query(call.id)

    if data.startswith("lang:"):
        lang = data[5:]
        conn = db()
        conn.execute("UPDATE users SET language=? WHERE telegram_id=?", (lang, uid))
        conn.commit(); conn.close()
        bot.send_message(uid, f"✅ {lang.upper()}")

    elif data == "check_sub":
        if check_sub(uid):
            bot.edit_message_text("✅ Tasdiqlandi!", uid, call.message.message_id)
            bot.send_message(uid, "🏠", reply_markup=reply_kb())
        else:
            bot.answer_callback_query(call.id, "❌", show_alert=True)

    elif data == "copy_ref":
        bot.send_message(uid, f"<code>https://t.me/{BOT_USERNAME}?start=ref_{uid}</code>")

    elif data.startswith("ref_list:"):
        offset = int(data.split(":")[1])
        show_refs(uid, uid, offset, call.message.message_id)

    elif data == "ref_back":
        bot.delete_message(uid, call.message.message_id)
        ref_menu(call.message)

    elif data.startswith("qr_pg:"):
        offset = int(data.split(":")[1])
        bot.delete_message(uid, call.message.message_id)
        show_qrs(uid, uid, offset)

    elif data.startswith("qr_dl:"):
        qr_id = int(data.split(":")[1])
        conn = db()
        r = conn.execute("SELECT qr_data,name FROM qr_history WHERE id=? AND user_id=?",
                         (qr_id, uid)).fetchone()
        conn.close()
        if r:
            try:
                img = make_qr_png(r["qr_data"])
                bot.send_photo(uid, InputFile(img, f"qr_{qr_id}.png"),
                    caption=f"📥 <b>{r['name']}</b>\n\n<code>{r['qr_data'][:100]}</code>")
            except Exception as e:
                bot.send_message(uid, f"❌ {e}")

    elif data.startswith("qr_del:"):
        qr_id = int(data.split(":")[1])
        if del_qr(qr_id, uid):
            bot.delete_message(uid, call.message.message_id)
            show_qrs(uid, uid, 0)
        else:
            bot.answer_callback_query(call.id, "❌", show_alert=True)

    elif not is_admin(uid):
        return

    elif data == "adm_stats":
        conn = db()
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = conn.execute("SELECT COUNT(*) FROM users WHERE date(created_at)=date('now')").fetchone()[0]
        qr_total = conn.execute("SELECT COUNT(*) FROM qr_history").fetchone()[0]
        ads = conn.execute("SELECT COUNT(*) FROM ad_events WHERE event_type='completed'").fetchone()[0]
        conn.close()
        text = (f"📊 <b>STATISTIKA</b>\n\n"
                f"👥 Jami: {total} | Bugun: {today}\n"
                f"🧩 QR: {qr_total}\n"
                f"📢 Reklama: {ads}")
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("adm_users:"):
        offset = int(data.split(":")[1])
        conn = db()
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        users = conn.execute("""SELECT * FROM users ORDER BY last_active DESC LIMIT 10 OFFSET ?""",
                             (offset,)).fetchall()
        conn.close()
        text = f"👥 <b>Foydalanuvchilar</b> ({offset+1}-{offset+len(users)}/{total})\n\n"
        for i, u in enumerate(users, 1):
            text += f"{offset+i}. {u['first_name'] or '—'} | <code>{u['telegram_id']}</code>\n"
        kb = InlineKeyboardMarkup()
        nav = []
        if offset > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_users:{offset-10}"))
        if offset + 10 < total:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_users:{offset+10}"))
        if nav: kb.row(*nav)
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_bc":
        msg = bot.send_message(uid, "📣 Xabar:")
        bot.register_next_step_handler(msg, bc_ok)

    elif data == "adm_bc_ok":
        text = bot._bc_text
        conn = db()
        users = conn.execute("SELECT telegram_id FROM users").fetchall()
        conn.close()
        sent = failed = 0
        for u in users:
            try:
                bot.send_message(u["telegram_id"], text)
                sent += 1; time.sleep(0.05)
            except: failed += 1
        bot.send_message(uid, f"✅ {sent} | ❌ {failed}")

    elif data == "adm_subs":
        conn = db()
        chans = conn.execute("SELECT * FROM channels").fetchall()
        conn.close()
        text = f"🔒 Holat: {'✅' if get_setting('force_sub_enabled')=='1' else '❌'}\n\n"
        for ch in chans: text += f"• {ch['name']}\n"
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ Kanal", callback_data="adm_add_ch"))
        kb.add(InlineKeyboardButton("🔄 Almashtirish", callback_data="adm_tog_sub"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_add_ch":
        msg = bot.send_message(uid, "Format: <code>@username|Nomi</code>")
        bot.register_next_step_handler(msg, add_ch)

    elif data == "adm_tog_sub":
        cur = get_setting("force_sub_enabled", "0")
        set_setting("force_sub_enabled", "0" if cur == "1" else "1")
        bot.answer_callback_query(call.id, "✅")

    elif data == "adm_admins":
        admins = ADMIN_IDS + [r["telegram_id"] for r in db().execute("SELECT telegram_id FROM admins").fetchall()]
        text = "👑 <b>Adminlar</b>\n\n" + "\n".join(f"• <code>{a}</code>" for a in admins)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("➕ Qo'shish", callback_data="adm_add_adm"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_add_adm":
        msg = bot.send_message(uid, "Yangi admin Telegram ID:")
        bot.register_next_step_handler(msg, add_adm)

    elif data == "adm_msgs":
        conn = db()
        msgs = conn.execute("SELECT * FROM support_messages WHERE status='open' ORDER BY created_at DESC LIMIT 10").fetchall()
        conn.close()
        text = "📋 <b>Xabarlar</b>\n\n"
        if not msgs: text += "Yo'q"
        else:
            for m in msgs: text += f"#{m['id']}: {m['message'][:40]}\n"
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_ads":
        text = (f"📢 <b>Reklama</b>\n\n"
                f"Holat: {'✅' if get_setting('monetag_enabled')=='1' else '❌'}\n"
                f"Tekin QR: {get_setting('free_qr_count')}\n"
                f"Har N: {get_setting('qr_per_ad')}")
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🧩 Tekin", callback_data="adm_set_free"),
            InlineKeyboardButton("📢 N", callback_data="adm_set_perad"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_set_free":
        msg = bot.send_message(uid, "Nechta tekin?")
        bot.register_next_step_handler(msg, set_val, "free_qr_count")

    elif data == "adm_set_perad":
        msg = bot.send_message(uid, "Har nechta QR da?")
        bot.register_next_step_handler(msg, set_val, "qr_per_ad")

    elif data == "adm_back":
        bot.delete_message(uid, call.message.message_id)
        admin_menu(uid)

    elif data.startswith("reply:"):
        mid = int(data.split(":")[1])
        msg = bot.send_message(uid, f"💬 Javob #{mid}:")
        bot.register_next_step_handler(msg, send_reply, mid)


def bc_ok(message):
    if message.content_type != "text":
        bot.reply_to(message, "❌"); return
    bot._bc_text = message.text
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ Yuborish", callback_data="adm_bc_ok"),
           InlineKeyboardButton("❌", callback_data="adm_back"))
    bot.send_message(message.chat.id, f"📣 {message.text}\n\n<b>Tasdiq?</b>", reply_markup=kb)


def add_ch(message):
    try:
        p = message.text.split("|")
        if len(p) < 2: raise ValueError("Format")
        u = p[0].strip(); n = p[1].strip()
        chat_id = u
        try: chat_id = bot.get_chat(u).id
        except: pass
        conn = db()
        conn.execute("""INSERT INTO channels(chat_id,name,username,invite_link,check_mode)
            VALUES(?,?,?,?,?)""",
            (str(chat_id), n, u, f"https://t.me/{u.lstrip('@')}", "member"))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, "✅")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ {e}")


def add_adm(message):
    try:
        aid = int(message.text.strip())
        conn = db()
        conn.execute("INSERT OR IGNORE INTO admins(telegram_id,added_by,created_at) VALUES(?,?,?)",
                     (aid, message.from_user.id, datetime.utcnow().isoformat()))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, f"✅ Admin: {aid}")
        try: bot.send_message(aid, "🎉 Siz admin!")
        except: pass
    except: bot.send_message(message.chat.id, "❌ Raqam")


def set_val(message, key):
    try:
        set_setting(key, str(int(message.text.strip())))
        bot.send_message(message.chat.id, "✅")
    except: bot.send_message(message.chat.id, "❌")


def send_reply(message, mid):
    if message.content_type != "text":
        bot.reply_to(message, "❌"); return
    conn = db()
    r = conn.execute("SELECT user_id FROM support_messages WHERE id=?", (mid,)).fetchone()
    if r:
        conn.execute("UPDATE support_messages SET admin_reply=?,status='answered' WHERE id=?",
                     (message.text, mid))
        conn.commit()
        try:
            bot.send_message(r["user_id"], f"📬 <b>Admin:</b>\n\n{message.text}")
            bot.send_message(message.chat.id, "✅")
        except: pass
    conn.close()


# ═══════════════════════════════════════════════════════════
# FLASK — BACKEND + HTML BITTA DOMENDA
# ═══════════════════════════════════════════════════════════
app = Flask(__name__)
CORS(app, origins="*", allow_headers=["*"], methods=["GET", "POST", "DELETE", "OPTIONS"])


@app.after_request
def cors_headers(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Telegram-Init-Data'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return r


def validate_init(init_data):
    if not init_data: raise ValueError("initData yo'q")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    h = parsed.pop("hash", None)
    if not h: raise ValueError("hash yo'q")
    check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, h): raise ValueError("Imzo xato")
    u = parsed.get("user")
    if not u: raise ValueError("User yo'q")
    return json.loads(u)


def auth(f):
    @wraps(f)
    def w(*a, **k):
        try:
            tg = validate_init(request.headers.get("X-Telegram-Init-Data", ""))
        except ValueError as e:
            print(f"❌ Auth: {e}")
            return jsonify({"detail": str(e)}), 401
        return f(tg, *a, **k)
    return w


# ═══════════════════════════════════════════════════════════
# HTML PAGE
# ═══════════════════════════════════════════════════════════
HTML_PAGE = r'''<!DOCTYPE html>
<html lang="uz" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>QR Master</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script src="//libtl.com/sdk.js" data-zone="''' + MONETAG_ZONE + r'''" data-sdk="show_''' + MONETAG_ZONE + r'''"></script>
<style>
:root{--bg:#fff;--fg:#0f172a;--muted:#64748b;--card:#f1f5f9;--primary:#6366f1;
--primary-2:#8b5cf6;--border:#e2e8f0;--success:#22c55e;--danger:#ef4444;--radius:16px}
[data-theme="dark"]{--bg:#0f172a;--fg:#f1f5f9;--muted:#94a3b8;--card:#1e293b;--border:#334155}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--fg);padding-bottom:80px;min-height:100dvh}
.header{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;
background:var(--bg);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:19px}
.logo-mark{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,var(--primary),var(--primary-2));
display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900}
.avatar{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#06b6d4,var(--primary));
display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:14px}
.main{padding:0 16px}
.hero{margin:16px 0;padding:22px;border-radius:var(--radius);background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff}
.hero h2{font-size:20px;margin-bottom:6px}.hero p{font-size:13px;opacity:.9}
.section-title{font-size:15px;font-weight:700;margin:22px 0 12px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.type-card{background:var(--card);border:none;border-radius:14px;padding:14px 8px;
display:flex;flex-direction:column;align-items:center;gap:6px;cursor:pointer;color:var(--fg);font-family:inherit;transition:transform .15s}
.type-card:active{transform:scale(.94)}
.type-icon{font-size:24px}.type-label{font-size:11px;text-align:center;font-weight:600}
.nav{position:fixed;bottom:0;left:0;right:0;display:flex;background:var(--bg);
border-top:1px solid var(--border);padding:8px 0 calc(8px + env(safe-area-inset-bottom))}
.nav-btn{flex:1;background:none;border:none;color:var(--muted);display:flex;
flex-direction:column;align-items:center;gap:2px;padding:6px;font-size:10px;font-weight:600;cursor:pointer;font-family:inherit}
.nav-btn.active{color:var(--primary)}.nav-btn .ico{font-size:20px}
.page{display:none;animation:fade .25s}.page.active{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.field{margin-bottom:14px}.field label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px;font-weight:600}
.input,.select,.textarea{width:100%;padding:14px 16px;background:var(--card);
border:1.5px solid transparent;border-radius:14px;font-size:15px;color:var(--fg);outline:none;font-family:inherit}
.input:focus,.textarea:focus,.select:focus{border-color:var(--primary)}
.textarea{resize:vertical;min-height:80px}
.btn{width:100%;padding:16px;border:none;border-radius:14px;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit;transition:transform .15s}
.btn:active{transform:scale(.97)}
.btn-primary{background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff}
.btn-ghost{background:var(--card);color:var(--fg)}
.qr-result{margin-top:20px;padding:20px;border-radius:var(--radius);background:var(--card);text-align:center}
.qr-result img,.qr-result canvas{border-radius:12px;max-width:100%;height:auto}
.qr-actions{display:flex;gap:8px;margin-top:14px}
.qr-actions .btn{padding:12px;font-size:13px}
.toast-wrap{position:fixed;top:80px;left:50%;transform:translateX(-50%);z-index:1000;
display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{padding:12px 20px;border-radius:12px;color:#fff;font-size:14px;font-weight:600;max-width:85vw;text-align:center}
.toast.success{background:var(--success)}.toast.error{background:var(--danger)}.toast.info{background:var(--primary)}
.empty{text-align:center;padding:40px 20px;color:var(--muted);font-size:14px}
.empty .ico{font-size:44px;display:block;margin-bottom:10px;opacity:.5}
.hist-item{display:flex;align-items:center;gap:12px;padding:14px;background:var(--card);border-radius:14px;margin-bottom:8px}
.hist-info{flex:1;min-width:0}
.hist-info h4{font-size:14px;font-weight:700;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hist-info p{font-size:12px;color:var(--muted)}
.icon-btn{width:34px;height:34px;border-radius:10px;border:none;background:var(--bg);
color:var(--fg);cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center}
.profile-card{padding:20px;border-radius:var(--radius);background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;text-align:center;margin-bottom:16px}
.profile-card .av{width:70px;height:70px;border-radius:50%;background:rgba(255,255,255,.2);
margin:0 auto 10px;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800}
.profile-card h3{font-size:17px;margin-bottom:4px}
.profile-card p{font-size:13px;opacity:.85}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px}
.stat{background:rgba(255,255,255,.15);padding:12px;border-radius:12px}
.stat b{display:block;font-size:20px;font-weight:800}
.stat span{font-size:11px;opacity:.85}
.loading{position:fixed;inset:0;background:rgba(15,23,42,.55);display:none;align-items:center;justify-content:center;z-index:2000}
.loading.on{display:flex}
.spin{width:42px;height:42px;border:3px solid rgba(255,255,255,.25);border-top-color:#fff;border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.ref-link{background:var(--card);padding:12px;border-radius:10px;font-family:monospace;font-size:11px;
word-break:break-all;margin:10px 0;border:1px solid var(--border)}
</style>
</head>
<body>

<div class="header">
  <div class="logo"><div class="logo-mark">QR</div><span>QR Master</span></div>
  <div class="avatar" id="avatar">U</div>
</div>

<div class="main">
  <div class="page active" id="page-home">
    <div class="hero"><h2>🎯 QR Master</h2><p>12+ turdagi QR kod yaratish</p></div>
    <div class="section-title">QR turlari</div>
    <div class="grid" id="typeGrid"></div>
    <div class="section-title">So'nggi QR kodlar</div>
    <div id="recentList"></div>
  </div>

  <div class="page" id="page-create">
    <div class="section-title" id="createTitle">QR kod</div>
    <div id="dynamicFields"></div>
    <div class="section-title" style="margin-top:6px">🎨 Dizayn</div>
    <div class="field"><label>QR rangi</label>
      <input type="color" id="fillColor" value="#0f172a" style="width:100%;height:50px;border:none;border-radius:12px"></div>
    <div class="field"><label>Fon rangi</label>
      <input type="color" id="backColor" value="#ffffff" style="width:100%;height:50px;border:none;border-radius:12px"></div>
    <div class="field"><label>O'lcham</label>
      <select class="select" id="qrSize">
        <option value="256">256×256</option><option value="512" selected>512×512</option>
        <option value="1024">1024×1024</option></select></div>
    <button class="btn btn-primary" id="genBtn">✨ Yaratish</button>
    <button class="btn btn-ghost" id="backBtn" style="margin-top:8px">← Orqaga</button>
    <div class="qr-result" id="qrResult" style="display:none">
      <div id="qrContainer"></div>
      <div class="qr-actions">
        <button class="btn btn-primary" id="dlBtn">⬇️ Yuklab olish</button>
        <button class="btn btn-ghost" id="saveHistBtn">💾 Saqlash</button>
      </div>
    </div>
  </div>

  <div class="page" id="page-history">
    <div class="section-title">🕐 Tarix</div>
    <div id="historyList"></div>
  </div>

  <div class="page" id="page-ref">
    <div class="section-title">👥 Referal tizimi</div>
    <div class="hero"><h2>🎁 Do'stlarni taklif qiling</h2><p>Har bir referal uchun mukofot</p></div>
    <div class="field"><label>Havolangiz:</label>
      <div class="ref-link" id="refLink">—</div></div>
    <button class="btn btn-primary" id="copyRef">📋 Nusxalash</button>
    <button class="btn btn-ghost" id="shareRef" style="margin-top:8px">📤 Ulashish</button>
    <div class="section-title" style="margin-top:20px">Referallaringiz</div>
    <div id="refList"></div>
  </div>

  <div class="page" id="page-profile">
    <div class="profile-card">
      <div class="av" id="profileAv">U</div>
      <h3 id="profileName">Foydalanuvchi</h3>
      <p id="profileUsername">@username</p>
      <div class="stats">
        <div class="stat"><b id="statQR">0</b><span>QR</span></div>
        <div class="stat"><b id="statAds">0</b><span>Reklama</span></div>
        <div class="stat"><b id="statRef">0</b><span>Referal</span></div>
      </div>
    </div>
    <button class="btn btn-ghost" id="themeBtn">🌗 Mavzu</button>
  </div>
</div>

<nav class="nav">
  <button class="nav-btn active" data-page="home"><span class="ico">🏠</span>Asosiy</button>
  <button class="nav-btn" data-page="ref"><span class="ico">👥</span>Referal</button>
  <button class="nav-btn" data-page="history"><span class="ico">🕐</span>Tarix</button>
  <button class="nav-btn" data-page="profile"><span class="ico">👤</span>Profil</button>
</nav>

<div class="toast-wrap" id="toastWrap"></div>
<div class="loading" id="loading"><div class="spin"></div></div>

<script>
const MONETAG_ZONE = "''' + MONETAG_ZONE + r'''";

const AdManager = {
  async show() {
    const fn = window['show_' + MONETAG_ZONE];
    if (typeof fn !== 'function') { console.warn('SDK yo\'q'); return false; }
    try { await fn('pop'); return true; }
    catch (e) { console.warn(e); return false; }
  }
};

const App = {
  currentType: 'universal', currentData: null, initData: '', me: null,

  async init() {
    const tg = window.Telegram?.WebApp;
    if (tg) { tg.ready(); tg.expand();
      document.documentElement.setAttribute('data-theme', tg.colorScheme === 'dark' ? 'dark' : 'light');
    }
    this.initData = tg?.initData || '';
    this.renderTypes(); this.bindNav(); this.bindForm(); this.bindProfile(); this.bindRef();
    this.loadProfile();

    if (this.initData) {
      try {
        this.me = await this.api('/api/auth/me', 'POST');
        document.getElementById('statQR').textContent = this.me.qr_count || 0;
        document.getElementById('statAds').textContent = this.me.ad_count || 0;
        document.getElementById('statRef').textContent = this.me.referrals || 0;
        await this.loadHistory();
        await this.loadRefs();
      } catch (e) { console.warn(e); this.toast('Xato: ' + e.message, 'error'); }
    } else {
      this.toast('Telegram orqali oching!', 'error');
    }
  },

  async api(path, method = 'GET', body = null) {
    const opts = { method, headers: {
      'X-Telegram-Init-Data': this.initData, 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    if (!r.ok) { const e = await r.json().catch(() => ({ detail: 'Xatolik' }));
      throw new Error(e.detail || 'Xatolik'); }
    return r.json();
  },

  loadProfile() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user || {};
    const f = (u.first_name || 'F').charAt(0).toUpperCase();
    document.getElementById('avatar').textContent = f;
    document.getElementById('profileAv').textContent = f;
    document.getElementById('profileName').textContent =
      ((u.first_name || '') + ' ' + (u.last_name || '')).trim() || 'Foydalanuvchi';
    document.getElementById('profileUsername').textContent = u.username ? '@' + u.username : 'Telegram';
  },

  types: [
    {id:'universal',icon:'✨',label:'Universal',fields:[{k:'text',l:'Matn / URL',t:'textarea',p:'Istalgan matn'}]},
    {id:'url',icon:'🔗',label:'URL',fields:[{k:'url',l:'Havola',t:'url',p:'https://example.com'}]},
    {id:'text',icon:'📝',label:'Matn',fields:[{k:'text',l:'Matn',t:'textarea'}]},
    {id:'wifi',icon:'📶',label:'Wi-Fi',fields:[
      {k:'ssid',l:'Tarmoq',t:'text'},{k:'pass',l:'Parol',t:'text'},
      {k:'sec',l:'Xavfsizlik',t:'select',opts:['WPA','WEP','nopass']}]},
    {id:'vcard',icon:'👤',label:'Kontakt',fields:[
      {k:'first',l:'Ism',t:'text'},{k:'last',l:'Familiya',t:'text'},
      {k:'phone',l:'Telefon',t:'tel'},{k:'email',l:'Email',t:'email'}]},
    {id:'phone',icon:'📞',label:'Telefon',fields:[{k:'phone',l:'Raqam',t:'tel',p:'+998901234567'}]},
    {id:'sms',icon:'💬',label:'SMS',fields:[{k:'phone',l:'Telefon',t:'tel'},{k:'msg',l:'Xabar',t:'textarea'}]},
    {id:'email',icon:'✉️',label:'Email',fields:[{k:'to',l:'Kimga',t:'email'},{k:'subject',l:'Mavzu',t:'text'}]},
    {id:'tg',icon:'✈️',label:'TG',fields:[{k:'username',l:'Username',t:'text',p:'durov'}]},
    {id:'geo',icon:'📍',label:'Geo',fields:[
      {k:'lat',l:'Kenglik',t:'text',p:'41.311081'},{k:'lng',l:'Uzunlik',t:'text',p:'69.240562'}]},
    {id:'event',icon:'📅',label:'Tadbir',fields:[
      {k:'title',l:'Nomi',t:'text'},{k:'start',l:'Boshlanish',t:'text',p:'2025-12-31 18:00'}]},
    {id:'custom',icon:'⚙️',label:'Maxsus',fields:[{k:'raw',l:'Format',t:'textarea'}]},
  ],

  renderTypes() {
    document.getElementById('typeGrid').innerHTML = this.types.map(t =>
      `<button class="type-card" data-type="${t.id}">
        <span class="type-icon">${t.icon}</span>
        <span class="type-label">${t.label}</span></button>`).join('');
    document.querySelectorAll('.type-card').forEach(b => {
      b.onclick = () => this.openCreate(b.dataset.type); });
  },

  openCreate(id) {
    const t = this.types.find(x => x.id === id); if (!t) return;
    this.currentType = id;
    document.getElementById('createTitle').textContent = `${t.icon} ${t.label}`;
    document.getElementById('dynamicFields').innerHTML = t.fields.map(f => {
      let el;
      if (f.t === 'textarea') el = `<textarea class="textarea" id="f_${f.k}" placeholder="${f.p||''}"></textarea>`;
      else if (f.t === 'select') el = `<select class="select" id="f_${f.k}">${f.opts.map(o=>`<option>${o}</option>`).join('')}</select>`;
      else el = `<input class="input" type="${f.t}" id="f_${f.k}" placeholder="${f.p||''}">`;
      return `<div class="field"><label>${f.l}</label>${el}</div>`;
    }).join('');
    document.getElementById('qrResult').style.display = 'none';
    this.goPage('create');
  },

  buildPayload() {
    const v = id => (document.getElementById('f_' + id)?.value || '').trim();
    const enc = encodeURIComponent;
    const m = {
      universal: () => v('text'), text: () => v('text'), url: () => v('url'),
      wifi: () => `WIFI:T:${v('sec')||'WPA'};S:${v('ssid')};P:${v('pass')};;`,
      vcard: () => ['BEGIN:VCARD','VERSION:3.0',`N:${v('last')};${v('first')};;;`,
        `FN:${v('first')} ${v('last')}`.trim(),
        v('phone')?`TEL:${v('phone')}`:'', v('email')?`EMAIL:${v('email')}`:'',
        'END:VCARD'].filter(Boolean).join('\n'),
      phone: () => `tel:${v('phone')}`,
      sms: () => `SMSTO:${v('phone')}:${v('msg')}`,
      email: () => `mailto:${v('to')}?subject=${enc(v('subject'))}`,
      tg: () => `https://t.me/${v('username').replace('@','')}`,
      geo: () => `geo:${v('lat')},${v('lng')}`,
      event: () => ['BEGIN:VEVENT',`SUMMARY:${v('title')}`,
        `DTSTART:${v('start').replace(/[-: ]/g,'')}`,'END:VEVENT'].join('\n'),
      custom: () => v('raw'),
    };
    return (m[this.currentType] || (() => ''))();
  },

  async generate() {
    const data = this.buildPayload();
    if (!data) return this.toast("Ma'lumot kiriting", 'error');
    if (typeof QRCode === 'undefined') return this.toast("QR kutubxona yo'q", 'error');

    const size = parseInt(document.getElementById('qrSize').value);
    const fill = document.getElementById('fillColor').value;
    const back = document.getElementById('backColor').value;

    try {
      this.showLoading(true);
      const c = document.getElementById('qrContainer');
      c.innerHTML = '';
      new QRCode(c, { text: data, width: size, height: size,
        colorDark: fill, colorLight: back, correctLevel: QRCode.CorrectLevel.H });
      this.currentData = data;
      document.getElementById('qrResult').style.display = 'block';
      document.getElementById('qrResult').scrollIntoView({ behavior: 'smooth' });
      this.toast('Yaratildi ✅', 'success');
    } catch (e) { this.toast('Xato: ' + e.message, 'error'); }
    finally { this.showLoading(false); }
  },

  download() {
    const canvas = document.querySelector('#qrContainer canvas');
    if (!canvas) return this.toast("QR yo'q", 'error');
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = `qrmaster-${Date.now()}.png`;
    a.click();
    this.toast('Yuklab olindi ✅', 'success');
  },

  async saveToHistory() {
    if (!this.currentData) return;
    try {
      this.showLoading(true);
      const res = await this.api('/api/qr/create', 'POST', {
        qr_type: this.currentType,
        name: this.types.find(t => t.id === this.currentType)?.label || 'QR',
        data: this.currentData
      });
      this.toast('Saqlandi 💾', 'success');
      await this.loadHistory();
      if (this.me) {
        this.me.qr_count = res.total_qr;
        document.getElementById('statQR').textContent = res.total_qr;
      }
      if (res.show_ad) {
        this.showLoading(false);
        if (confirm('🎬 Reklama ko\'rish?')) {
          this.showLoading(true);
          const watched = await AdManager.show();
          this.showLoading(false);
          if (watched) {
            await this.api('/api/qr/ad_complete', 'POST', {});
            this.toast('🎁 Rahmat!', 'success');
          }
        }
      }
    } catch (e) { this.toast(e.message, 'error'); }
    finally { this.showLoading(false); }
  },

  async loadHistory() {
    try {
      const list = await this.api('/api/qr/history');
      this.renderHistory(list); this.renderRecent(list);
    } catch (e) { console.warn(e); }
  },

  renderRecent(list) {
    const el = document.getElementById('recentList');
    const r = list.slice(0, 3);
    if (!r.length) { el.innerHTML = `<div class="empty"><span class="ico">🎯</span>Bo'sh</div>`; return; }
    el.innerHTML = r.map(h => `<div class="hist-item"><div class="hist-info">
      <h4>${h.name}</h4><p>${h.qr_type} · ${new Date(h.created_at).toLocaleString('uz')}</p>
    </div></div>`).join('');
  },

  renderHistory(list) {
    const el = document.getElementById('historyList');
    if (!list.length) { el.innerHTML = `<div class="empty"><span class="ico">🕐</span>Bo'sh</div>`; return; }
    el.innerHTML = list.map(h => `<div class="hist-item">
      <div class="hist-info">
        <h4>${h.name}</h4>
        <p>${h.qr_type} · ${new Date(h.created_at).toLocaleString('uz')}</p>
      </div>
      <button class="icon-btn" onclick="App.delQr(${h.id})">🗑</button>
    </div>`).join('');
  },

  async delQr(id) {
    if (!confirm("O'chirilsinmi?")) return;
    try {
      await this.api('/api/qr/' + id, 'DELETE');
      this.toast("O'chirildi", 'info');
      await this.loadHistory();
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async loadRefs() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (!u) return;
    const link = `https://t.me/${this.me?.bot_username || 'SizningBotUsername'}?start=ref_${u.id}`;
    document.getElementById('refLink').textContent = link;
    try {
      const data = await this.api('/api/ref/list');
      const el = document.getElementById('refList');
      if (!data.refs || !data.refs.length) {
        el.innerHTML = `<div class="empty"><span class="ico">👥</span>Referal yo'q</div>`;
      } else {
        el.innerHTML = data.refs.map(r => `<div class="hist-item">
          <div class="hist-info">
            <h4>${r.first_name || 'Foydalanuvchi'}</h4>
            <p>@${r.username || '—'} · ${(r.created_at||'').slice(0,10)}</p>
          </div>
        </div>`).join('');
      }
    } catch (e) { console.warn(e); }
  },

  bindRef() {
    document.getElementById('copyRef').onclick = async () => {
      const link = document.getElementById('refLink').textContent;
      try { await navigator.clipboard.writeText(link); this.toast('Nusxalandi 📋', 'success'); }
      catch { this.toast('Xato', 'error'); }
    };
    document.getElementById('shareRef').onclick = () => {
      const link = document.getElementById('refLink').textContent;
      window.open(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=QR Master`, '_blank');
    };
  },

  bindProfile() {
    document.getElementById('themeBtn').onclick = () => {
      const cur = document.documentElement.getAttribute('data-theme');
      document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
    };
  },

  bindForm() {
    document.getElementById('genBtn').onclick = () => this.generate();
    document.getElementById('backBtn').onclick = () => this.goPage('home');
    document.getElementById('dlBtn').onclick = () => this.download();
    document.getElementById('saveHistBtn').onclick = () => this.saveToHistory();
  },

  bindNav() {
    document.querySelectorAll('.nav-btn').forEach(b => {
      b.onclick = () => this.goPage(b.dataset.page);
    });
  },

  goPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById('page-' + name)?.classList.add('active');
    document.querySelectorAll('.nav-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.page === name));
    window.scrollTo({ top: 0 });
  },

  toast(msg, type = 'info') {
    const w = document.getElementById('toastWrap');
    const el = document.createElement('div');
    el.className = 'toast ' + type; el.textContent = msg;
    w.appendChild(el); setTimeout(() => el.remove(), 2500);
  },

  showLoading(on) { document.getElementById('loading').classList.toggle('on', on); }
};

window.addEventListener('DOMContentLoaded', () => App.init());
</script>
</body>
</html>'''


# ═══════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════
@app.route("/", methods=["GET", "HEAD"])
def index():
    return Response(HTML_PAGE, mimetype="text/html")


@app.route("/health", methods=["GET", "HEAD"])
def health():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat()})


@app.route("/api/auth/me", methods=["POST", "GET", "OPTIONS"])
@auth
def api_me(tg):
    upsert_user(tg)
    u = get_user(tg["id"])
    return jsonify({
        "id": u["telegram_id"], "username": u["username"],
        "first_name": u["first_name"], "last_name": u["last_name"],
        "qr_count": u["qr_count"], "ad_count": u["ad_count"],
        "is_admin": is_admin(tg["id"]),
        "referrals": count_refs(tg["id"]),
        "bot_username": BOT_USERNAME,
    })


@app.route("/api/qr/create", methods=["POST", "OPTIONS"])
@auth
def api_create_qr(tg):
    body = request.get_json(silent=True) or {}
    data = (body.get("data") or "").strip()
    if not data: return jsonify({"detail": "Bo'sh"}), 400
    if len(data) > 2953: return jsonify({"detail": "Uzun"}), 400

    upsert_user(tg)
    add_qr(tg["id"], body.get("qr_type") or "universal",
           (body.get("name") or "QR")[:255], data)

    u = get_user(tg["id"])
    total = u["qr_count"]
    free = int(get_setting("free_qr_count", "3"))
    per_ad = int(get_setting("qr_per_ad", "5"))
    show_ad = False
    if get_setting("monetag_enabled") == "1" and per_ad > 0 and total > free:
        if (total - free) % per_ad == 0: show_ad = True

    return jsonify({"ok": True, "total_qr": total, "show_ad": show_ad})


@app.route("/api/qr/ad_complete", methods=["POST", "OPTIONS"])
@auth
def api_ad_done(tg):
    conn = db()
    conn.execute("INSERT INTO ad_events(user_id,format,event_type,created_at) VALUES(?,?,?,?)",
                 (tg["id"], "rewarded", "completed", datetime.utcnow().isoformat()))
    conn.execute("UPDATE users SET ad_count=ad_count+1 WHERE telegram_id=?", (tg["id"],))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/qr/history", methods=["GET", "OPTIONS"])
@auth
def api_history(tg):
    qrs = get_qrs(tg["id"], 50, 0)
    return jsonify([{"id": q["id"], "name": q["name"], "qr_type": q["qr_type"],
                     "qr_data": q["qr_data"], "created_at": q["created_at"]} for q in qrs])


@app.route("/api/qr/<int:qr_id>", methods=["DELETE", "OPTIONS"])
@auth
def api_del_qr(tg, qr_id):
    if del_qr(qr_id, tg["id"]): return jsonify({"ok": True})
    return jsonify({"detail": "Topilmadi"}), 404


@app.route("/api/ref/list", methods=["GET", "OPTIONS"])
@auth
def api_ref_list(tg):
    return jsonify({"total": count_refs(tg["id"]),
                    "refs": get_refs(tg["id"], 50, 0)})


# ═══════════════════════════════════════════════════════════
def run_bot():
    while True:
        try:
            bot.remove_webhook()
            bot.set_my_commands([
                BotCommand("start", "Bosh menyu"),
                BotCommand("help", "Yordam"),
                BotCommand("id", "Telegram ID"),
            ])
            print("✅ Bot ishga tushdi")
            bot.infinity_polling(skip_pending=True, timeout=30)
        except KeyboardInterrupt: break
        except Exception as e:
            print(f"⚠️ Bot xato: {e}"); time.sleep(5)


if __name__ == "__main__":
    print("=" * 55)
    print("🚀 QR MASTER")
    print("=" * 55)
    print(f"🌐 Server:    http://0.0.0.0:{PORT}")
    print(f"🔗 Mini App:  {WEBAPP_URL}")
    print(f"👤 Admin:     {ADMIN_IDS}")
    print(f"💰 Monetag:   {MONETAG_ZONE}")
    print("=" * 55)
    threading.Thread(target=run_bot, daemon=True).start()
    time.sleep(2)
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
