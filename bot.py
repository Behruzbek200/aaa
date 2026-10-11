# -*- coding: utf-8 -*-
"""QR MASTER — Bot + Backend (Render uchun)"""
import os, hmac, hashlib, json, threading, time, sqlite3, io
from datetime import datetime
from functools import wraps
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand, InputFile
)
import qrcode


# ═══════════════════════════════════════════════════════════
# SOZLAMALAR — Render Environment Variables orqali
# ═══════════════════════════════════════════════════════════
BOT_TOKEN    = os.getenv("BOT_TOKEN", "SIZNING_TOKENINGIZ")
BOT_USERNAME = os.getenv("BOT_USERNAME", "SizningBotUsername")
WEBAPP_URL   = os.getenv("WEBAPP_URL", "https://behruzbek200.github.io/aaa")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "8261542613").split(",")]
MONETAG_ZONE = os.getenv("MONETAG_ZONE", "11990967")
PORT         = int(os.getenv("PORT", 8000))
DB_FILE      = os.getenv("DB_FILE", "qr_master.db")
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_user ON qr_history(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ref ON referrals(referrer_id)")

    defaults = {
        "force_sub_enabled":"1","referral_enabled":"0","referral_reward":"0",
        "min_referrals":"3","monetag_enabled":"1","free_qr_count":"3",
        "qr_per_ad":"5","interstitial_enabled":"1","rewarded_enabled":"1",
        "popup_enabled":"0",
    }
    for k,v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
    conn.commit(); conn.close()


def db():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; return conn


def get_setting(key, default=""):
    conn = db()
    r = conn.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
    conn.close()
    return r["value"] if r else default


def set_setting(key, value):
    conn = db()
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(key,str(value)))
    conn.commit(); conn.close()


def is_admin(uid):
    if uid in ADMIN_IDS: return True
    conn = db()
    r = conn.execute("SELECT telegram_id FROM admins WHERE telegram_id=?",(uid,)).fetchone()
    conn.close()
    return bool(r)


def get_all_admins():
    conn = db()
    rows = conn.execute("SELECT telegram_id FROM admins").fetchall()
    conn.close()
    return list(ADMIN_IDS) + [r["telegram_id"] for r in rows]


db_init()


def get_user(tg_id):
    conn = db()
    r = conn.execute("SELECT * FROM users WHERE telegram_id=?",(tg_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def create_or_update_user(tg):
    conn = db()
    e = conn.execute("SELECT telegram_id FROM users WHERE telegram_id=?",(tg["id"],)).fetchone()
    now = datetime.utcnow().isoformat()
    if not e:
        conn.execute("""INSERT INTO users(telegram_id,username,first_name,last_name,
            language,created_at,last_active) VALUES(?,?,?,?,?,?,?)""",
            (tg["id"],tg.get("username"),tg.get("first_name"),tg.get("last_name"),
             tg.get("language_code","uz"),now,now))
        is_new = True
    else:
        conn.execute("""UPDATE users SET username=?,first_name=?,last_name=?,
            last_active=? WHERE telegram_id=?""",
            (tg.get("username"),tg.get("first_name"),tg.get("last_name"),now,tg["id"]))
        is_new = False
    conn.commit(); conn.close()
    return is_new


def add_qr_record(user_id, qr_type, name, qr_data, payload_hash):
    conn = db()
    conn.execute("""INSERT INTO qr_history(user_id,qr_type,name,qr_data,
        payload_hash,created_at) VALUES(?,?,?,?,?,?)""",
        (user_id,qr_type,name,qr_data,payload_hash,datetime.utcnow().isoformat()))
    conn.execute("UPDATE users SET qr_count=qr_count+1 WHERE telegram_id=?",(user_id,))
    conn.commit(); conn.close()


def get_user_qrs(user_id, limit=20, offset=0):
    conn = db()
    rows = conn.execute("""SELECT id,qr_type,name,qr_data,created_at FROM qr_history
        WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (user_id,limit,offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_user_qrs(user_id):
    conn = db()
    r = conn.execute("SELECT COUNT(*) FROM qr_history WHERE user_id=?",(user_id,)).fetchone()[0]
    conn.close()
    return r


def delete_qr(qr_id, user_id):
    conn = db()
    r = conn.execute("SELECT id FROM qr_history WHERE id=? AND user_id=?",
                     (qr_id,user_id)).fetchone()
    if r:
        conn.execute("DELETE FROM qr_history WHERE id=?",(qr_id,))
        conn.execute("UPDATE users SET qr_count=MAX(0,qr_count-1) WHERE telegram_id=?",
                     (user_id,))
        conn.commit(); conn.close()
        return True
    conn.close()
    return False


def add_referral(referrer_id, referred_id):
    if referrer_id == referred_id: return False
    conn = db()
    try:
        conn.execute("""INSERT INTO referrals(referrer_id,referred_id,created_at)
            VALUES(?,?,?)""",(referrer_id,referred_id,datetime.utcnow().isoformat()))
        conn.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def count_referrals(user_id):
    conn = db()
    t = conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?",(user_id,)).fetchone()[0]
    conn.close()
    return t


def get_referrals(user_id, limit=10, offset=0):
    conn = db()
    rows = conn.execute("""SELECT r.*, u.first_name, u.username
        FROM referrals r LEFT JOIN users u ON u.telegram_id=r.referred_id
        WHERE r.referrer_id=? ORDER BY r.created_at DESC LIMIT ? OFFSET ?""",
        (user_id,limit,offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_active_channels():
    conn = db()
    rows = conn.execute("SELECT * FROM channels WHERE is_active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def make_qr_image(data, fill="#000000", back="#FFFFFF"):
    qr = qrcode.QRCode(box_size=10, border=4,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color=fill, back_color=back)
    bio = io.BytesIO(); img.save(bio, "PNG"); bio.seek(0)
    return bio


# ═══════════════════════════════════════════════════════════
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def check_subscription(uid):
    if get_setting("force_sub_enabled") != "1": return True
    channels = get_active_channels()
    if not channels: return True
    for ch in channels:
        try:
            member = bot.get_chat_member(ch["chat_id"], uid)
            if member.status in ("left","kicked"): return False
        except: pass
    return True


def send_subscription_prompt(chat_id):
    channels = get_active_channels()
    if not channels: return
    text = "🔒 <b>Botdan foydalanish uchun obuna bo'ling:</b>\n\n"
    kb = InlineKeyboardMarkup()
    for i,ch in enumerate(channels,1):
        text += f"{i}. <b>{ch['name']}</b>\n"
        link = ch["invite_link"] or f"https://t.me/{ch['username']}"
        if link: kb.add(InlineKeyboardButton(f"📢 {ch['name']}", url=link))
    kb.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    bot.send_message(chat_id, text, reply_markup=kb)


def main_reply_kb(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("🧩 QR kod yaratish", web_app=WebAppInfo(url=WEBAPP_URL)),
        KeyboardButton("📜 Mening QR larim"),
    )
    kb.add(
        KeyboardButton("👥 Referal tizimi"),
        KeyboardButton("📊 Mening statistikam"),
    )
    kb.add(
        KeyboardButton("✉️ Adminga xabar"),
        KeyboardButton("🌐 Til"),
    )
    return kb


@bot.message_handler(commands=["start"])
def cmd_start(m):
    uid = m.from_user.id
    is_new = create_or_update_user({
        "id":uid,"username":m.from_user.username,
        "first_name":m.from_user.first_name,"last_name":m.from_user.last_name,
        "language_code":m.from_user.language_code})

    args = m.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
            if is_new and ref_id != uid and add_referral(ref_id, uid):
                try: bot.send_message(ref_id, "🎉 Yangi referal!")
                except: pass
        except: pass

    if not check_subscription(uid):
        send_subscription_prompt(m.chat.id); return

    bot.send_message(m.chat.id,
        f"👋 Salom, <b>{m.from_user.first_name or 'do\'stim'}</b>!\n\n"
        "🎯 <b>QR Master</b> — universal QR kod generator.\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=main_reply_kb(uid))

    if is_admin(uid):
        bot.send_message(m.chat.id, "👑 Admin panel: /admin")


@bot.message_handler(commands=["admin"])
def cmd_admin(m):
    if not is_admin(m.from_user.id):
        bot.reply_to(m, "🚫 Admin emas"); return
    show_admin_menu(m.chat.id)


def show_admin_menu(chat_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Statistika", callback_data="adm_stats:0"),
        InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm_users:0"),
    )
    kb.add(
        InlineKeyboardButton("📣 Broadcast", callback_data="adm_bc"),
        InlineKeyboardButton("🔒 Majburiy obuna", callback_data="adm_subs"),
    )
    kb.add(
        InlineKeyboardButton("📢 Reklama", callback_data="adm_ads"),
        InlineKeyboardButton("👑 Adminlar", callback_data="adm_admins:0"),
    )
    kb.add(
        InlineKeyboardButton("📋 Xabarlar", callback_data="adm_msgs"),
        InlineKeyboardButton("⚙️ Sozlamalar", callback_data="adm_settings"),
    )
    bot.send_message(chat_id, "👑 <b>ADMIN PANEL</b>", reply_markup=kb)


@bot.message_handler(commands=["id"])
def cmd_id(m):
    bot.reply_to(m, f"🆔 ID: <code>{m.from_user.id}</code>")


@bot.message_handler(func=lambda m: m.text == "📜 Mening QR larim")
def my_qrs(m):
    uid = m.from_user.id
    if not check_subscription(uid):
        send_subscription_prompt(m.chat.id); return
    show_user_qrs(m.chat.id, uid, 0)


def show_user_qrs(chat_id, uid, offset):
    total = count_user_qrs(uid)
    if total == 0:
        bot.send_message(chat_id,
            "📜 Sizda hali QR kodlar yo'q.\n\n"
            "🧩 Mini App orqali yarating va saqlang!",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🚀 QR yaratish",
                    web_app=WebAppInfo(url=WEBAPP_URL))))
        return

    qrs = get_user_qrs(uid, 5, offset)
    text = f"📜 <b>Sizning QR kodlaringiz</b> ({offset+1}-{offset+len(qrs)}/{total})\n\n"
    for i,q in enumerate(qrs,1):
        text += f"{offset+i}. <b>{q['name']}</b> ({q['qr_type']})\n"
        text += f"   <code>{q['qr_data'][:40]}...</code>\n"
        text += f"   📅 {q['created_at'][:10]}\n\n"

    kb = InlineKeyboardMarkup(row_width=5)
    for q in qrs:
        kb.add(InlineKeyboardButton(f"📥 #{q['id']}", callback_data=f"qr_dl:{q['id']}"),
               InlineKeyboardButton(f"🗑 #{q['id']}", callback_data=f"qr_del:{q['id']}"))

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"qr_page:{offset-5}"))
    if offset + 5 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"qr_page:{offset+5}"))
    if nav: kb.row(*nav)

    bot.send_message(chat_id, text, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "👥 Referal tizimi")
def ref_menu(m):
    uid = m.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    total = count_referrals(uid)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📋 Havolani nusxalash", callback_data="copy_ref"))
    kb.add(InlineKeyboardButton("📤 Ulashish",
        url=f"https://t.me/share/url?url={link}&text=QR Master"))
    if total > 0:
        kb.add(InlineKeyboardButton(f"👥 Ro'yxat ({total})", callback_data="ref_list:0"))
    bot.send_message(m.chat.id,
        f"👥 <b>Referal tizimi</b>\n\n"
        f"🔗 <code>{link}</code>\n\n"
        f"📊 Jami: <b>{total}</b>",
        reply_markup=kb)


def show_ref_list(chat_id, uid, offset, msg_id=None):
    total = count_referrals(uid)
    refs = get_referrals(uid, 10, offset)

    text = f"👥 <b>Referallaringiz</b> ({offset+1}-{offset+len(refs)}/{total})\n\n"
    for i,r in enumerate(refs, 1):
        name = r.get("first_name") or "Foydalanuvchi"
        uname = f"@{r['username']}" if r.get("username") else "—"
        text += f"{offset+i}. {name} ({uname})\n"
        text += f"   📅 {r['created_at'][:10]}\n"

    kb = InlineKeyboardMarkup()
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"ref_list:{offset-10}"))
    nav.append(InlineKeyboardButton("🔙 Orqaga", callback_data="ref_back"))
    if offset + 10 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"ref_list:{offset+10}"))
    kb.row(*nav)

    if msg_id:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "📊 Mening statistikam")
def my_stats(m):
    uid = m.from_user.id
    u = get_user(uid)
    total_ref = count_referrals(uid)
    bot.send_message(m.chat.id,
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Ism: {u['first_name'] or '—'}\n"
        f"🧩 Yaratilgan QR: <b>{u['qr_count']}</b>\n"
        f"📢 Reklama: <b>{u['ad_count']}</b>\n"
        f"👥 Referallar: <b>{total_ref}</b>\n"
        f"📅 Ro'yxatdan: {u['created_at'][:10]}")


@bot.message_handler(func=lambda m: m.text == "✉️ Adminga xabar")
def support(m):
    msg = bot.send_message(m.chat.id,
        "✉️ <b>Adminga xabar</b>\n\nXabaringizni yozing:")
    bot.register_next_step_handler(msg, save_support)


def save_support(message):
    if message.content_type != "text":
        bot.reply_to(message, "❌ Faqat matn"); return
    uid = message.from_user.id
    conn = db()
    conn.execute("INSERT INTO support_messages(user_id,message,created_at) VALUES(?,?,?)",
                 (uid,message.text,datetime.utcnow().isoformat()))
    mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit(); conn.close()
    bot.reply_to(message, "✅ Yuborildi!")
    for admin_id in get_all_admins():
        try:
            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("💬 Javob", callback_data=f"reply:{mid}"))
            bot.send_message(admin_id,
                f"✉️ <b>Xabar #{mid}</b>\n\n👤 @{message.from_user.username or '—'} (ID: {uid})\n\n💬 {message.text}",
                reply_markup=kb)
        except: pass


@bot.message_handler(func=lambda m: m.text == "🌐 Til")
def lang_menu(m):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang:uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"))
    bot.send_message(m.chat.id, "🌐 Tilni tanlang:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    uid = call.from_user.id
    data = call.data
    bot.answer_callback_query(call.id)

    if data.startswith("lang:"):
        lang = data[5:]
        conn = db()
        conn.execute("UPDATE users SET language=? WHERE telegram_id=?",(lang,uid))
        conn.commit(); conn.close()
        bot.send_message(uid, f"✅ Til: {lang.upper()}", reply_markup=main_reply_kb(uid))

    elif data == "check_sub":
        if check_subscription(uid):
            bot.edit_message_text("✅ Obuna tasdiqlandi!", uid, call.message.message_id)
            bot.send_message(uid, "🏠 Bosh menyu:", reply_markup=main_reply_kb(uid))
        else:
            bot.answer_callback_query(call.id, "❌ Obuna bo'lmadingiz!", show_alert=True)

    elif data == "copy_ref":
        link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
        bot.send_message(uid, f"<code>{link}</code>")

    elif data.startswith("ref_list:"):
        offset = int(data.split(":")[1])
        show_ref_list(uid, uid, offset, call.message.message_id)

    elif data == "ref_back":
        bot.delete_message(uid, call.message.message_id)
        ref_menu(call.message)

    elif data.startswith("qr_page:"):
        offset = int(data.split(":")[1])
        bot.delete_message(uid, call.message.message_id)
        show_user_qrs(uid, uid, offset)

    elif data.startswith("qr_dl:"):
        qr_id = int(data.split(":")[1])
        conn = db()
        r = conn.execute("SELECT qr_data,name FROM qr_history WHERE id=? AND user_id=?",
                         (qr_id,uid)).fetchone()
        conn.close()
        if r:
            try:
                img = make_qr_image(r["qr_data"])
                bot.send_photo(uid, InputFile(img, f"qr_{qr_id}.png"),
                    caption=f"📥 <b>{r['name']}</b>\n\n<code>{r['qr_data'][:100]}</code>")
            except Exception as e:
                bot.send_message(uid, f"❌ Xato: {e}")
        else:
            bot.send_message(uid, "❌ Topilmadi")

    elif data.startswith("qr_del:"):
        qr_id = int(data.split(":")[1])
        if delete_qr(qr_id, uid):
            bot.answer_callback_query(call.id, "✅ O'chirildi")
            bot.delete_message(uid, call.message.message_id)
            show_user_qrs(uid, uid, 0)
        else:
            bot.answer_callback_query(call.id, "❌ Topilmadi", show_alert=True)

    elif not is_admin(uid):
        return

    elif data.startswith("adm_stats"):
        conn = db()
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = conn.execute("SELECT COUNT(*) FROM users WHERE date(created_at)=date('now')").fetchone()[0]
        qr_total = conn.execute("SELECT COUNT(*) FROM qr_history").fetchone()[0]
        qr_today = conn.execute("SELECT COUNT(*) FROM qr_history WHERE date(created_at)=date('now')").fetchone()[0]
        ads = conn.execute("SELECT COUNT(*) FROM ad_events WHERE event_type='completed'").fetchone()[0]
        conn.close()
        text = (f"📊 <b>STATISTIKA</b>\n\n"
                f"👥 Jami: <b>{total}</b> | Bugun: <b>{today}</b>\n"
                f"🧩 QR: <b>{qr_total}</b> | Bugun: <b>{qr_today}</b>\n"
                f"📢 Reklama: <b>{ads}</b>")
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("adm_users:"):
        offset = int(data.split(":")[1])
        show_admin_users(uid, offset, call.message.message_id)

    elif data.startswith("adm_admins:"):
        show_admin_admins(uid, 0, call.message.message_id)

    elif data == "adm_add_admin":
        msg = bot.send_message(uid, "👑 Yangi admin ID sini kiriting:")
        bot.register_next_step_handler(msg, add_admin_step)

    elif data.startswith("adm_rm_admin:"):
        aid = int(data.split(":")[1])
        if aid in ADMIN_IDS:
            bot.answer_callback_query(call.id, "❌ Asosiy adminni o'chirib bo'lmaydi", show_alert=True)
        else:
            conn = db()
            conn.execute("DELETE FROM admins WHERE telegram_id=?",(aid,))
            conn.commit(); conn.close()
            bot.answer_callback_query(call.id, "✅ O'chirildi")
            show_admin_admins(uid, 0, call.message.message_id)

    elif data == "adm_bc":
        msg = bot.send_message(uid, "📣 Broadcast xabarini kiriting:")
        bot.register_next_step_handler(msg, bc_confirm)

    elif data == "adm_bc_confirm":
        text = bot._bc_text
        conn = db()
        users = conn.execute("SELECT telegram_id FROM users WHERE status='active'").fetchall()
        conn.close()
        sent = failed = 0
        for u in users:
            try:
                bot.send_message(u["telegram_id"], text)
                sent += 1; time.sleep(0.05)
            except: failed += 1
        bot.send_message(uid, f"✅ Yuborildi: {sent} | ❌ Xato: {failed}")

    elif data == "adm_subs":
        conn = db()
        chans = conn.execute("SELECT * FROM channels").fetchall()
        conn.close()
        text = f"🔒 <b>Obuna</b>: {'✅' if get_setting('force_sub_enabled')=='1' else '❌'}\n\n"
        for ch in chans: text += f"• {ch['name']}\n"
        if not chans: text += "Kanallar yo'q\n"
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("➕ Kanal qo'shish", callback_data="adm_add_ch"))
        kb.add(InlineKeyboardButton("🔄 Yoqish/O'chirish", callback_data="adm_tog_sub"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_add_ch":
        msg = bot.send_message(uid, "Format: <code>@username|Nomi</code>")
        bot.register_next_step_handler(msg, add_ch)

    elif data == "adm_tog_sub":
        cur = get_setting("force_sub_enabled","1")
        set_setting("force_sub_enabled", "0" if cur=="1" else "1")
        bot.answer_callback_query(call.id, "✅")
        cb(call)

    elif data == "adm_ads":
        text = (f"📢 <b>Reklama</b>\n\n"
                f"Tekin QR: <b>{get_setting('free_qr_count')}</b>\n"
                f"Har N QR da: <b>{get_setting('qr_per_ad')}</b>")
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🧩 Tekin", callback_data="adm_set_free"),
            InlineKeyboardButton("📢 Har N", callback_data="adm_set_perad"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_set_free":
        msg = bot.send_message(uid, "Nechta tekin QR?")
        bot.register_next_step_handler(msg, set_free)

    elif data == "adm_set_perad":
        msg = bot.send_message(uid, "Har nechta QR da reklama?")
        bot.register_next_step_handler(msg, set_perad)

    elif data == "adm_msgs":
        conn = db()
        msgs = conn.execute("SELECT * FROM support_messages WHERE status='open' ORDER BY created_at DESC LIMIT 10").fetchall()
        conn.close()
        text = "📋 <b>Xabarlar</b>\n\n"
        if not msgs: text += "Yo'q"
        else:
            for m in msgs: text += f"#{m['id']} | {m['message'][:40]}\n"
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_settings":
        text = f"⚙️ @{BOT_USERNAME}\n🔗 {WEBAPP_URL}"
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_back":
        bot.delete_message(uid, call.message.message_id)
        show_admin_menu(uid)

    elif data.startswith("reply:"):
        mid = int(data.split(":")[1])
        msg = bot.send_message(uid, f"💬 Javob #{mid}:")
        bot.register_next_step_handler(msg, send_reply, mid)


def show_admin_users(chat_id, offset, msg_id=None):
    conn = db()
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    users = conn.execute("""SELECT * FROM users ORDER BY last_active DESC LIMIT 10 OFFSET ?""",
                         (offset,)).fetchall()
    conn.close()
    text = f"👥 <b>Foydalanuvchilar</b> ({offset+1}-{offset+len(users)}/{total})\n\n"
    for i,u in enumerate(users,1):
        text += f"{offset+i}. {u['first_name'] or '—'} (ID: <code>{u['telegram_id']}</code>)\n"
        text += f"   QR: {u['qr_count']} | @{u['username'] or '—'}\n"

    kb = InlineKeyboardMarkup()
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_users:{offset-10}"))
    nav.append(InlineKeyboardButton(f"📄 {offset//10+1}/{(total-1)//10+1}", callback_data="none"))
    if offset + 10 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_users:{offset+10}"))
    kb.row(*nav)
    kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))

    if msg_id:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)


def show_admin_admins(chat_id, offset, msg_id=None):
    admins = get_all_admins()
    text = "👑 <b>Adminlar</b>\n\n"
    for i,a in enumerate(admins,1):
        text += f"{i}. <code>{a}</code>"
        if a in ADMIN_IDS: text += " (asosiy)"
        text += "\n"

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Admin qo'shish", callback_data="adm_add_admin"))
    for a in admins:
        if a not in ADMIN_IDS:
            kb.add(InlineKeyboardButton(f"🗑 {a}", callback_data=f"adm_rm_admin:{a}"))
    kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))

    if msg_id:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
    else:
        bot.send_message(chat_id, text, reply_markup=kb)


def add_admin_step(message):
    try:
        aid = int(message.text.strip())
        if aid in get_all_admins():
            bot.send_message(message.chat.id, "❌ Allaqachon admin")
            return
        conn = db()
        conn.execute("INSERT INTO admins(telegram_id,added_by,created_at) VALUES(?,?,?)",
                     (aid,message.from_user.id,datetime.utcnow().isoformat()))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, f"✅ Admin qo'shildi: {aid}")
        try: bot.send_message(aid, "🎉 Siz admin bo'ldingiz!")
        except: pass
    except:
        bot.send_message(message.chat.id, "❌ Raqam kiriting")


def bc_confirm(message):
    if message.content_type != "text":
        bot.reply_to(message, "❌ Faqat matn"); return
    bot._bc_text = message.text
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Yuborish", callback_data="adm_bc_confirm"),
        InlineKeyboardButton("❌ Bekor", callback_data="adm_back"))
    bot.send_message(message.chat.id,
        f"📣 <b>Xabar:</b>\n\n{message.text}\n\n<b>Tasdiq?</b>", reply_markup=kb)


def add_ch(message):
    try:
        parts = message.text.split("|")
        if len(parts) < 2: raise ValueError("Format xato")
        username = parts[0].strip()
        name = parts[1].strip()
        chat_id = username
        try:
            chat = bot.get_chat(username); chat_id = chat.id
        except: pass
        conn = db()
        conn.execute("""INSERT INTO channels(chat_id,name,username,invite_link,check_mode)
            VALUES(?,?,?,?,?)""",
            (str(chat_id),name,username,f"https://t.me/{username.lstrip('@')}","member"))
        conn.commit(); conn.close()
        bot.send_message(message.chat.id, "✅ Kanal qo'shildi")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ {e}")


def set_free(message):
    try:
        set_setting("free_qr_count", str(int(message.text.strip())))
        bot.send_message(message.chat.id, "✅")
    except: bot.send_message(message.chat.id, "❌ Raqam")


def set_perad(message):
    try:
        set_setting("qr_per_ad", str(int(message.text.strip())))
        bot.send_message(message.chat.id, "✅")
    except: bot.send_message(message.chat.id, "❌ Raqam")


def send_reply(message, mid):
    if message.content_type != "text":
        bot.reply_to(message, "❌ Faqat matn"); return
    conn = db()
    r = conn.execute("SELECT user_id FROM support_messages WHERE id=?",(mid,)).fetchone()
    if r:
        conn.execute("UPDATE support_messages SET admin_reply=?,status='answered' WHERE id=?",
                     (message.text,mid))
        conn.commit()
        try:
            bot.send_message(r["user_id"], f"📬 <b>Admin:</b>\n\n{message.text}")
            bot.send_message(message.chat.id, "✅ Yuborildi")
        except: bot.send_message(message.chat.id, "❌ Yuborib bo'lmadi")
    conn.close()


# ═══════════════════════════════════════════════════════════
# FLASK API
# ═══════════════════════════════════════════════════════════
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


def validate_init(init_data):
    if not init_data: raise ValueError("initData yo'q")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    h = parsed.pop("hash", None)
    if not h: raise ValueError("hash yo'q")
    check = "\n".join(f"{k}={v}" for k,v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, h): raise ValueError("Imzo xato")
    user = parsed.get("user")
    if not user: raise ValueError("User yo'q")
    return json.loads(user)


def auth_required(f):
    @wraps(f)
    def w(*a, **k):
        try:
            tg = validate_init(request.headers.get("X-Telegram-Init-Data",""))
        except ValueError as e:
            return jsonify({"detail":str(e)}), 401
        return f(tg, *a, **k)
    return w


@app.route("/health")
def health(): return jsonify({"ok":True,"time":datetime.utcnow().isoformat()})


@app.route("/api/auth/me", methods=["POST","GET","OPTIONS"])
@auth_required
def api_me(tg):
    create_or_update_user(tg)
    u = get_user(tg["id"])
    return jsonify({
        "id":u["telegram_id"],"username":u["username"],
        "first_name":u["first_name"],"last_name":u["last_name"],
        "qr_count":u["qr_count"],"ad_count":u["ad_count"],
        "is_admin":is_admin(tg["id"]),
        "referrals":count_referrals(tg["id"]),
        "created_at":u["created_at"],
    })


@app.route("/api/qr/create", methods=["POST","OPTIONS"])
@auth_required
def api_create_qr(tg):
    body = request.get_json(silent=True) or {}
    data = (body.get("data") or "").strip()
    if not data: return jsonify({"detail":"Bo'sh"}),400
    if len(data) > 2953: return jsonify({"detail":"Juda uzun"}),400

    create_or_update_user(tg)
    add_qr_record(tg["id"], body.get("qr_type") or "universal",
                  (body.get("name") or "QR")[:255], data,
                  hashlib.sha256(data.encode()).hexdigest())

    u = get_user(tg["id"])
    total = u["qr_count"]
    free = int(get_setting("free_qr_count","3"))
    per_ad = int(get_setting("qr_per_ad","5"))
    show_ad = False
    if get_setting("monetag_enabled")=="1" and per_ad>0 and total>free:
        if (total-free) % per_ad == 0: show_ad = True

    return jsonify({"ok":True,"total_qr":total,"free_qr":free,
        "qr_per_ad":per_ad,"show_ad":show_ad,"monetag_zone":MONETAG_ZONE})


@app.route("/api/qr/ad_complete", methods=["POST","OPTIONS"])
@auth_required
def api_ad_complete(tg):
    conn = db()
    conn.execute("INSERT INTO ad_events(user_id,format,event_type,created_at) VALUES(?,?,?,?)",
                 (tg["id"],"rewarded","completed",datetime.utcnow().isoformat()))
    conn.execute("UPDATE users SET ad_count=ad_count+1 WHERE telegram_id=?",(tg["id"],))
    conn.commit(); conn.close()
    return jsonify({"ok":True})


@app.route("/api/qr/history", methods=["GET","OPTIONS"])
@auth_required
def api_history(tg):
    qrs = get_user_qrs(tg["id"], 50, 0)
    return jsonify([{"id":q["id"],"name":q["name"],"qr_type":q["qr_type"],
                     "qr_data":q["qr_data"],"created_at":q["created_at"]} for q in qrs])


@app.route("/api/qr/<int:qr_id>", methods=["DELETE","OPTIONS"])
@auth_required
def api_del_qr(tg, qr_id):
    if delete_qr(qr_id, tg["id"]): return jsonify({"ok":True})
    return jsonify({"detail":"Topilmadi"}),404


# ═══════════════════════════════════════════════════════════
def run_bot():
    while True:
        try:
            bot.remove_webhook()
            bot.set_my_commands([
                BotCommand("start","Bosh menyu"),
                BotCommand("help","Yordam"),
                BotCommand("id","Telegram ID"),
            ])
            print("✅ Bot ishga tushdi")
            bot.infinity_polling(skip_pending=True, timeout=30)
        except KeyboardInterrupt: break
        except Exception as e:
            print(f"⚠️ {e}"); time.sleep(5)


if __name__ == "__main__":
    print("="*55)
    print("🚀 QR MASTER")
    print("="*55)
    print(f"🌐 http://0.0.0.0:{PORT}")
    print(f"🔗 {WEBAPP_URL}")
    print(f"👤 Admin: {ADMIN_IDS}")
    print("="*55)
    threading.Thread(target=run_bot, daemon=True).start()
    time.sleep(2)
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
