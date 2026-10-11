# -*- coding: utf-8 -*-
"""
QR MASTER — To'liq versiya (hamma muammolar tuzatildi)
Ishga tushirish: python bot.py
"""
import os, sys, hmac, hashlib, json, threading, time, sqlite3, io, base64
from datetime import datetime
from functools import wraps
from urllib.parse import parse_qsl


def ensure_pkgs():
    pkgs = {"telebot": "pyTelegramBotAPI", "flask": "Flask",
            "flask_cors": "Flask-Cors", "qrcode": "qrcode[pil]", "PIL": "Pillow"}
    import importlib
    missing = []
    for mod, pkg in pkgs.items():
        try: importlib.import_module(mod)
        except ImportError: missing.append(pkg)
    if missing:
        import subprocess
        print(f"📦 O'rnatilmoqda: {', '.join(missing)}")
        for pkg in missing:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        print("✅ O'rnatildi! Qayta ishga tushirish...")
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)


ensure_pkgs()

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand, InputFile
)
import qrcode
from PIL import Image


# ═══════════════════════════════════════════════════════════
BOT_TOKEN    = os.getenv("BOT_TOKEN", "8894647397:AAHpIC0PyVsjQ_XgDZOZGAVdOemN9YSBnMA")
BOT_USERNAME = ""  # Avtomatik olinadi
WEBAPP_URL   = os.getenv("WEBAPP_URL", "http://localhost:8000")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "8261542613").split(",")]
MONETAG_ZONE = os.getenv("MONETAG_ZONE", "11990967")
PORT         = int(os.getenv("PORT", 8000))
DB_FILE      = os.getenv("DB_FILE", "qr_master.db")
# ═══════════════════════════════════════════════════════════


# ═══ DATABASE ═══
def db_init():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        telegram_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        last_name TEXT, language TEXT DEFAULT 'uz', referrer_id INTEGER,
        status TEXT DEFAULT 'active', qr_count INTEGER DEFAULT 0,
        ad_count INTEGER DEFAULT 0, unlock_count INTEGER DEFAULT 0,
        created_at TEXT, last_active TEXT)""")
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
        "monetag_enabled": "1", "free_qr_count": "5",
        "qr_per_ad": "3", "invite_per_unlock": "3",
        "invite_bonus_qr": "10", "max_qr_per_day": "100",
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    conn.commit(); conn.close()


def db():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; return conn


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
            (tg.get("username"), tg.get("first_name"), tg.get("last_name"), now, tg["id"]))
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
        conn.execute("UPDATE users SET unlock_count=unlock_count+? WHERE telegram_id=?",
                     (int(get_setting("invite_bonus_qr", "10")), referrer))
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


def get_refs(user_id, limit=50, offset=0):
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


def make_qr_png(data, logo_data=None):
    qr = qrcode.QRCode(box_size=10, border=4,
                       error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    if logo_data:
        try:
            logo_bytes = base64.b64decode(logo_data.split(",")[-1])
            logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
            qr_w, qr_h = img.size
            logo_size = int(min(qr_w, qr_h) * 0.22)
            logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
            pad = 8
            bg = Image.new("RGBA", (logo_size+pad*2, logo_size+pad*2), (255,255,255,255))
            bg.paste(logo, (pad, pad), logo)
            pos = ((qr_w - bg.width)//2, (qr_h - bg.height)//2)
            img.paste(bg, pos, bg)
        except Exception as e:
            print(f"⚠️ Logo xato: {e}")

    bio = io.BytesIO(); img.save(bio, "PNG"); bio.seek(0)
    return bio


db_init()


# ═══ BOT ═══
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def get_bot_username():
    """Bot username ni avtomatik olish."""
    global BOT_USERNAME
    try:
        me = bot.get_me()
        BOT_USERNAME = me.username
        print(f"✅ Bot username: @{BOT_USERNAME}")
    except Exception as e:
        print(f"⚠️ Username olib bo'lmadi: {e}")
        BOT_USERNAME = "SizningBotUsername"


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
        KeyboardButton("🎬 Reklama / Unlock", web_app=WebAppInfo(url=WEBAPP_URL + "#ads")),
    )
    kb.add(
        KeyboardButton("📜 Mening QR larim"),
        KeyboardButton("👥 Referal tizimi"),
    )
    kb.add(
        KeyboardButton("📊 Statistika"),
        KeyboardButton("✉️ Adminga xabar"),
    )
    return kb


@bot.message_handler(commands=["start"])
def cmd_start(m):
    uid = m.from_user.id
    is_new = upsert_user({
        "id": uid, "username": m.from_user.username,
        "first_name": m.from_user.first_name, "last_name": m.from_user.last_name,
        "language_code": m.from_user.language_code})

    args = m.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
            if is_new and add_ref(ref_id, uid):
                try: bot.send_message(ref_id, "🎉 Yangi referal! +10 bonus QR")
                except: pass
        except: pass

    if not check_sub(uid):
        sub_prompt(m.chat.id); return

    u = get_user(uid)
    unlock = u.get("unlock_count", 0) if u else 0
    bot.send_message(m.chat.id,
        f"👋 Salom, <b>{m.from_user.first_name or 'do\'stim'}</b>!\n\n"
        f"🎯 <b>QR Master</b> — universal QR kod generator.\n\n"
        f"🎁 Bepul limit: <b>{get_setting('free_qr_count')} ta</b>\n"
        f"🔓 Qo'shimcha unlock: <b>{unlock} ta</b>\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=reply_kb())

    if is_admin(uid):
        bot.send_message(m.chat.id, "👑 Admin: /admin")


@bot.message_handler(commands=["admin"])
def cmd_admin(m):
    if not is_admin(m.from_user.id):
        bot.reply_to(m, "🚫 Admin emas"); return
    admin_menu(m.chat.id)


def admin_menu(chat_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Statistika", callback_data="adm_stats"),
        InlineKeyboardButton("👥 Users", callback_data="adm_users:0"),
    )
    kb.add(
        InlineKeyboardButton("📣 Broadcast", callback_data="adm_bc"),
        InlineKeyboardButton("🔒 Obuna", callback_data="adm_subs"),
    )
    kb.add(
        InlineKeyboardButton("👑 Adminlar", callback_data="adm_admins"),
        InlineKeyboardButton("📋 Xabarlar", callback_data="adm_msgs"),
    )
    kb.add(InlineKeyboardButton("📢 Reklama sozlamalari", callback_data="adm_ads"))
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
                InlineKeyboardButton("🚀 QR yaratish", web_app=WebAppInfo(url=WEBAPP_URL))))
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
    bonus = int(get_setting("invite_bonus_qr", "10"))
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📋 Nusxalash", callback_data="copy_ref"))
    kb.add(InlineKeyboardButton("📤 Ulashish",
        url=f"https://t.me/share/url?url={link}&text=QR Master"))
    if total > 0:
        kb.add(InlineKeyboardButton(f"👥 Ro'yxat ({total})", callback_data="ref_list:0"))
    bot.send_message(m.chat.id,
        f"👥 <b>Referal tizimi</b>\n\n"
        f"🔗 <code>{link}</code>\n\n"
        f"👥 Taklif qilganlar: <b>{total}</b>\n"
        f"🎁 Har bir referal uchun: <b>+{bonus} bonus QR</b>",
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
        f"🧩 QR kodlar: <b>{u['qr_count']}</b>\n"
        f"📢 Reklama: <b>{u['ad_count']}</b>\n"
        f"🔓 Unlock: <b>{u.get('unlock_count', 0)}</b>\n"
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


@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    uid = call.from_user.id
    data = call.data
    bot.answer_callback_query(call.id)

    if data == "check_sub":
        if check_sub(uid):
            bot.edit_message_text("✅ Tasdiqlandi!", uid, call.message.message_id)
            bot.send_message(uid, "🏠 Bosh menyu:", reply_markup=reply_kb())
        else:
            bot.answer_callback_query(call.id, "❌ Obuna emas", show_alert=True)

    elif data == "copy_ref":
        bot.send_message(uid, f"<code>https://t.me/{BOT_USERNAME}?start=ref_{uid}</code>")

    elif data.startswith("ref_list:"):
        show_refs(uid, uid, int(data.split(":")[1]), call.message.message_id)

    elif data == "ref_back":
        bot.delete_message(uid, call.message.message_id)
        ref_menu(call.message)

    elif data.startswith("qr_pg:"):
        bot.delete_message(uid, call.message.message_id)
        show_qrs(uid, uid, int(data.split(":")[1]))

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
                f"👥 Jami: <b>{total}</b> | Bugun: <b>{today}</b>\n"
                f"🧩 QR: <b>{qr_total}</b>\n"
                f"📢 Reklama: <b>{ads}</b>")
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
        kb.add(InlineKeyboardButton("➕ Kanal qo'shish", callback_data="adm_add_ch"))
        kb.add(InlineKeyboardButton("🔄 Yoq/O'chir", callback_data="adm_tog_sub"))
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
        conn = db()
        extras = conn.execute("SELECT telegram_id FROM admins").fetchall()
        conn.close()
        all_admins = ADMIN_IDS + [r["telegram_id"] for r in extras]
        text = "👑 <b>Adminlar</b>\n\n" + "\n".join(f"• <code>{a}</code>" for a in all_admins)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("➕ Qo'shish", callback_data="adm_add_adm"))
        for a in extras:
            kb.add(InlineKeyboardButton(f"🗑 {a['telegram_id']}",
                                        callback_data=f"adm_rm_adm:{a['telegram_id']}"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_add_adm":
        msg = bot.send_message(uid, "Yangi admin Telegram ID:")
        bot.register_next_step_handler(msg, add_adm)

    elif data.startswith("adm_rm_adm:"):
        aid = int(data.split(":")[1])
        conn = db()
        conn.execute("DELETE FROM admins WHERE telegram_id=?", (aid,))
        conn.commit(); conn.close()
        bot.answer_callback_query(call.id, "✅")

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
                f"Bepul QR: {get_setting('free_qr_count')}\n"
                f"Har N QR da reklama: {get_setting('qr_per_ad')}\n"
                f"Referal bonus: +{get_setting('invite_bonus_qr')} QR")
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🧩 Bepul", callback_data="adm_set:free_qr_count"),
            InlineKeyboardButton("📢 Har N", callback_data="adm_set:qr_per_ad"))
        kb.add(
            InlineKeyboardButton("🎁 Referal bonus", callback_data="adm_set:invite_bonus_qr"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("adm_set:"):
        key = data.split(":")[1]
        msg = bot.send_message(uid, f"<b>{key}</b> uchun yangi qiymat:")
        bot.register_next_step_handler(msg, set_val, key)

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
        if len(p) < 2: raise ValueError("Format: @username|Nomi")
        u = p[0].strip(); n = p[1].strip()
        chat_id = u
        try: chat_id = bot.get_chat(u).id
        except: pass
        conn = db()
        conn.execute("""INSERT INTO channels(chat_id,name,username,invite_link,check_mode)
            VALUES(?,?,?,?,?)""",
            (str(chat_id), n, u, f"https://t.me/{u.lstrip('@')}", "member"))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, "✅ Kanal qo'shildi")
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
        bot.send_message(message.chat.id, f"✅ {key} = {message.text.strip()}")
    except: bot.send_message(message.chat.id, "❌ Raqam kiriting")


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


# ═══ FLASK ═══
app = Flask(__name__)
CORS(app, origins="*")


@app.after_request
def cors_h(r):
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
            return jsonify({"detail": str(e)}), 401
        return f(tg, *a, **k)
    return w


# ═══ HTML (katta HTML, alohida beriladi) ═══
from html_page import HTML_PAGE  # yoki quyida inline


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
        "first_name": u["first_name"],
        "qr_count": u["qr_count"], "ad_count": u["ad_count"],
        "unlock_count": u.get("unlock_count", 0),
        "is_admin": is_admin(tg["id"]),
        "referrals": count_refs(tg["id"]),
        "bot_username": BOT_USERNAME,
        "free_qr": get_setting("free_qr_count"),
        "qr_per_ad": get_setting("qr_per_ad"),
    })


@app.route("/api/qr/create", methods=["POST", "OPTIONS"])
@auth
def api_create_qr(tg):
    body = request.get_json(silent=True) or {}
    data = (body.get("data") or "").strip()
    if not data: return jsonify({"detail": "Bo'sh"}), 400
    if len(data) > 5000: return jsonify({"detail": "Juda uzun"}), 400

    upsert_user(tg)
    add_qr(tg["id"], body.get("qr_type") or "universal",
           (body.get("name") or "QR")[:255], data)

    u = get_user(tg["id"])
    total = u["qr_count"]
    free = int(get_setting("free_qr_count", "5"))
    unlock = u.get("unlock_count", 0)
    per_ad = int(get_setting("qr_per_ad", "3"))
    limit = free + unlock

    show_ad = False
    if total > limit and per_ad > 0:
        if (total - limit) % per_ad == 0:
            show_ad = True

    return jsonify({"ok": True, "total_qr": total, "limit": limit,
                    "unlock": unlock, "show_ad": show_ad})


@app.route("/api/qr/ad_complete", methods=["POST", "OPTIONS"])
@auth
def api_ad_done(tg):
    conn = db()
    conn.execute("INSERT INTO ad_events(user_id,format,event_type,created_at) VALUES(?,?,?,?)",
                 (tg["id"], "rewarded", "completed", datetime.utcnow().isoformat()))
    conn.execute("UPDATE users SET ad_count=ad_count+1, unlock_count=unlock_count+? WHERE telegram_id=?",
                 (int(get_setting("qr_per_ad", "3")), tg["id"]))
    conn.commit(); conn.close()
    u = get_user(tg["id"])
    return jsonify({"ok": True, "unlock": u.get("unlock_count", 0)})


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


def run_bot():
    while True:
        try:
            bot.remove_webhook()
            get_bot_username()
            bot.set_my_commands([
                BotCommand("start", "Bosh menyu"),
                BotCommand("help", "Yordam"),
                BotCommand("id", "Telegram ID"),
            ])
            print("✅ Bot tayyor")
            bot.infinity_polling(skip_pending=True, timeout=30)
        except KeyboardInterrupt: break
        except Exception as e:
            print(f"⚠️ {e}"); time.sleep(5)


if __name__ == "__main__":
    print("=" * 55)
    print("🚀 QR MASTER")
    print("=" * 55)
    print(f"🌐 {WEBAPP_URL}")
    print(f"👤 Admin: {ADMIN_IDS}")
    print("=" * 55)
    threading.Thread(target=run_bot, daemon=True).start()
    time.sleep(3)
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
