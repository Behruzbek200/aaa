# -*- coding: utf-8 -*-
"""
QR MASTER — Universal QR kod generator
Ishga tushirish: python bot.py

Tuzilma (4 qism):
  1-QISM: Sozlamalar + Database + DB funksiyalar
  2-QISM: Bot + Obuna + Handlers + Admin panel
  3-QISM: Flask + Auth + HTML Mini App
  4-QISM: JavaScript + API routes + Ishga tushirish
"""
import os, sys, hmac, hashlib, json, threading, time, sqlite3, io
from datetime import datetime
from functools import wraps
from urllib.parse import parse_qsl


# ═══════════════════════════════════════════════════════════════
# KUTUBXONALARNI AVTOMATIK O'RNATISH
# ═══════════════════════════════════════════════════════════════
def install_packages():
    import importlib, subprocess
    packages = {
        "telebot": "pyTelegramBotAPI",
        "flask": "Flask",
        "flask_cors": "Flask-Cors",
        "qrcode": "qrcode[pil]",
        "PIL": "Pillow",
    }
    missing = []
    for mod, pkg in packages.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"📦 O'rnatilmoqda: {', '.join(missing)}")
        for pkg in missing:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        print("✅ Qayta ishga tushirish...")
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    print("✅ Kutubxonalar tayyor")


install_packages()

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand, InputFile,
    MenuButtonWebApp, ChatMemberLeft, ChatMemberBanned,
    ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner,
    ChatMemberRestricted,
)
import qrcode


# ═══════════════════════════════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
WEBAPP_URL   = os.getenv("WEBAPP_URL", "http://localhost:8000")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
MONETAG_ZONE = os.getenv("MONETAG_ZONE", "11990967")
PORT         = int(os.getenv("PORT", 8000))
DB_FILE      = os.getenv("DB_FILE", "qr_master.db")

BOT_USERNAME = ""

# Data papkasini yaratish
os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)

print("=" * 55)
print("🚀 QR MASTER")
print("=" * 55)
print(f"📁 DB:        {DB_FILE}")
print(f"🌐 WebApp:    {WEBAPP_URL}")
print(f"👤 Admin:     {ADMIN_IDS}")
print(f"💰 Monetag:   {MONETAG_ZONE}")
print("=" * 55)


# ═══════════════════════════════════════════════════════════════
# DATABASE SCHEMA
# ═══════════════════════════════════════════════════════════════
def init_database():
    """Barcha jadvallarni yaratish."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        telegram_id  INTEGER PRIMARY KEY,
        username     TEXT,
        first_name   TEXT,
        last_name    TEXT,
        language     TEXT DEFAULT 'uz',
        status       TEXT DEFAULT 'active',
        qr_count     INTEGER DEFAULT 0,
        ad_count     INTEGER DEFAULT 0,
        unlock_count INTEGER DEFAULT 0,
        created_at   TEXT,
        last_active  TEXT
    );
    CREATE TABLE IF NOT EXISTS qr_history(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER,
        qr_type      TEXT,
        name         TEXT,
        qr_data      TEXT,
        payload_hash TEXT,
        created_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS channels(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id      TEXT,
        name         TEXT,
        username     TEXT,
        invite_link  TEXT,
        check_mode   TEXT DEFAULT 'member',
        is_active    INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS settings(
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS referrals(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id  INTEGER,
        referred_id  INTEGER UNIQUE,
        created_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS support_messages(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER,
        message      TEXT,
        admin_reply  TEXT,
        status       TEXT DEFAULT 'open',
        created_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS ad_events(
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER,
        format       TEXT,
        event_type   TEXT,
        created_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS admins(
        telegram_id INTEGER PRIMARY KEY
    );
    CREATE TABLE IF NOT EXISTS pending_subs(
        user_id      INTEGER,
        channel_id   INTEGER,
        requested_at TEXT,
        PRIMARY KEY(user_id, channel_id)
    );
    CREATE INDEX IF NOT EXISTS idx_qr_user ON qr_history(user_id);
    CREATE INDEX IF NOT EXISTS idx_ref ON referrals(referrer_id);
    """)

    # Standart sozlamalar
    defaults = {
        "force_sub_enabled": "0",   # Majburiy obuna (0=o'chiq, 1=yoqiq)
        "referral_enabled":  "1",   # Referal tizimi
        "monetag_enabled":   "1",   # Monetag reklama
        "free_qr_count":     "5",   # Boshida N ta bepul
        "qr_per_ad":         "2",   # Keyin har M ta bepul + 1 reklama
        "invite_bonus_qr":   "10",  # Har referal uchun bonus QR
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))

    conn.commit()
    conn.close()
    print("✅ Database tayyor")


init_database()


# ═══════════════════════════════════════════════════════════════
# DATABASE YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════════════════════════════
def q(sql, args=(), one=False):
    """SELECT — ro'yxat yoki bitta natija."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, args)
        rows = cur.fetchall()
        conn.commit()
        if one:
            return dict(rows[0]) if rows else None
        return [dict(r) for r in rows]
    finally:
        conn.close()


def qx(sql, args=()):
    """INSERT/UPDATE/DELETE — lastrowid qaytaradi."""
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ─── SOZLAMALAR ───
def gs(key, default=""):
    """Get setting."""
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


def ss(key, value):
    """Set setting."""
    qx("INSERT OR REPLACE INTO settings VALUES(?, ?)", (key, str(value)))


def gi(key, default=0):
    """Get int setting."""
    try:
        return int(gs(key, str(default)))
    except (ValueError, TypeError):
        return default


# ─── ADMINLAR ───
def is_admin(uid):
    if uid in ADMIN_IDS:
        return True
    return bool(q("SELECT 1 FROM admins WHERE telegram_id=?", (uid,), one=True))


def add_admin(uid):
    qx("INSERT OR IGNORE INTO admins VALUES(?)", (uid,))


def remove_admin(uid):
    qx("DELETE FROM admins WHERE telegram_id=?", (uid,))


def all_admins():
    extras = q("SELECT telegram_id FROM admins")
    return list(ADMIN_IDS) + [r["telegram_id"] for r in extras]


# ─── FOYDALANUVCHILAR ───
def get_user(uid):
    return q("SELECT * FROM users WHERE telegram_id=?", (uid,), one=True)


def upsert_user(tg):
    uid = tg["id"]
    now = datetime.utcnow().isoformat()
    if not q("SELECT 1 FROM users WHERE telegram_id=?", (uid,), one=True):
        qx("""INSERT INTO users(telegram_id, username, first_name, last_name,
            language, created_at, last_active) VALUES(?,?,?,?,?,?,?)""",
           (uid, tg.get("username"), tg.get("first_name"), tg.get("last_name"),
            tg.get("language_code", "uz"), now, now))
        return True
    qx("""UPDATE users SET username=?, first_name=?, last_name=?, last_active=?
        WHERE telegram_id=?""",
       (tg.get("username"), tg.get("first_name"), tg.get("last_name"), now, uid))
    return False


def cnt_users():
    return q("SELECT COUNT(*) c FROM users", one=True)["c"]


def cnt_users_today():
    return q("SELECT COUNT(*) c FROM users WHERE date(created_at)=date('now')", one=True)["c"]


def users_page(off=0, lim=10):
    return q("SELECT * FROM users ORDER BY last_active DESC LIMIT ? OFFSET ?", (lim, off))


# ─── QR KODLAR ───
def add_qr(uid, qr_type, name, data):
    qx("""INSERT INTO qr_history(user_id, qr_type, name, qr_data, payload_hash, created_at)
        VALUES(?,?,?,?,?,?)""",
       (uid, qr_type, name, data,
        hashlib.sha256(data.encode()).hexdigest(),
        datetime.utcnow().isoformat()))
    qx("UPDATE users SET qr_count=qr_count+1 WHERE telegram_id=?", (uid,))


def get_qrs(uid, lim=50, off=0):
    return q("""SELECT id, qr_type, name, qr_data, created_at
        FROM qr_history WHERE user_id=?
        ORDER BY id DESC LIMIT ? OFFSET ?""", (uid, lim, off))


def get_qr(qid, uid):
    return q("SELECT * FROM qr_history WHERE id=? AND user_id=?", (qid, uid), one=True)


def cnt_qrs(uid):
    return q("SELECT COUNT(*) c FROM qr_history WHERE user_id=?", (uid,), one=True)["c"]


def cnt_all_qrs():
    return q("SELECT COUNT(*) c FROM qr_history", one=True)["c"]


def del_qr(qid, uid):
    if q("SELECT 1 FROM qr_history WHERE id=? AND user_id=?", (qid, uid), one=True):
        qx("DELETE FROM qr_history WHERE id=?", (qid,))
        qx("UPDATE users SET qr_count=MAX(0,qr_count-1) WHERE telegram_id=?", (uid,))
        return True
    return False


# ─── REFERALLAR ───
def add_ref(referrer_id, referred_id):
    if referrer_id == referred_id:
        return False
    try:
        qx("INSERT INTO referrals(referrer_id, referred_id, created_at) VALUES(?,?,?)",
           (referrer_id, referred_id, datetime.utcnow().isoformat()))
        bonus = gi("invite_bonus_qr", 10)
        qx("UPDATE users SET unlock_count=unlock_count+? WHERE telegram_id=?",
           (bonus, referrer_id))
        return True
    except sqlite3.IntegrityError:
        return False


def cnt_refs(uid):
    return q("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (uid,), one=True)["c"]


def get_refs(uid, lim=50, off=0):
    return q("""SELECT r.*, u.first_name, u.username
        FROM referrals r LEFT JOIN users u ON u.telegram_id=r.referred_id
        WHERE r.referrer_id=? ORDER BY r.id DESC LIMIT ? OFFSET ?""", (uid, lim, off))


# ─── KANALLAR ───
def get_channels():
    return q("SELECT * FROM channels WHERE is_active=1 ORDER BY id")


def all_channels():
    return q("SELECT * FROM channels ORDER BY id")


def add_channel(chat_id, name, username=None, invite_link=None, check_mode="member"):
    return qx("""INSERT INTO channels(chat_id, name, username, invite_link, check_mode)
        VALUES(?,?,?,?,?)""", (str(chat_id), name, username, invite_link, check_mode))


def del_channel(ch_id):
    qx("DELETE FROM channels WHERE id=?", (ch_id,))


# ─── PENDING SUBS ───
def save_pending(uid, ch_id):
    qx("INSERT OR REPLACE INTO pending_subs VALUES(?,?,?)",
       (uid, ch_id, datetime.utcnow().isoformat()))


def has_pending(uid, ch_id):
    return bool(q("SELECT 1 FROM pending_subs WHERE user_id=? AND channel_id=?",
                  (uid, ch_id), one=True))


# ─── REKLAMA ───
def log_ad(uid, fmt="rewarded", event="completed"):
    qx("INSERT INTO ad_events(user_id, format, event_type, created_at) VALUES(?,?,?,?)",
       (uid, fmt, event, datetime.utcnow().isoformat()))
    if event == "completed":
        qx("UPDATE users SET ad_count=ad_count+1 WHERE telegram_id=?", (uid,))


def cnt_ads():
    return q("SELECT COUNT(*) c FROM ad_events WHERE event_type='completed'", one=True)["c"]


# ─── SUPPORT ───
def save_support(uid, msg):
    return qx("INSERT INTO support_messages(user_id, message, created_at) VALUES(?,?,?)",
              (uid, msg, datetime.utcnow().isoformat()))


def open_supports(lim=10):
    return q("""SELECT * FROM support_messages WHERE status='open'
        ORDER BY created_at DESC LIMIT ?""", (lim,))


def get_support(mid):
    return q("SELECT * FROM support_messages WHERE id=?", (mid,), one=True)


def reply_support(mid, reply):
    qx("UPDATE support_messages SET admin_reply=?, status='answered' WHERE id=?",
       (reply, mid))


# ─── QR RASM YARATISH ───
def make_qr_png(data):
    """Bot uchun — QR kodni PNG bytes qilib qaytarish."""
    qr = qrcode.QRCode(
        box_size=10,
        border=4,
        error_correction=qrcode.constants.ERROR_CORRECT_H
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


# ─── STATISTIKA ───
def global_stats():
    return {
        "users_total":  cnt_users(),
        "users_today":  cnt_users_today(),
        "qr_total":     cnt_all_qrs(),
        "ads_total":    cnt_ads(),
    }


# ───────────────────────────────────────────────────────────────
# KEYINGI: 2-QISM (Bot + handlers + admin panel)
# ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════
# TELEGRAM BOT YARATISH
# ═══════════════════════════════════════════════════════════════
if not BOT_TOKEN:
    print("❌ BOT_TOKEN bo'sh! Environment variable qo'shing")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def setup_bot():
    """Bot menu button va username ni sozlash."""
    global BOT_USERNAME
    try:
        me = bot.get_me()
        BOT_USERNAME = me.username
        print(f"✅ Bot: @{BOT_USERNAME}")

        # Menu button
        try:
            bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                text="🚀 QR Master",
                web_app=WebAppInfo(url=WEBAPP_URL)
            ))
            print(f"✅ Menu: {WEBAPP_URL}")
        except Exception as e:
            print(f"⚠️ Menu: {e}")

        # Commands
        bot.set_my_commands([
            BotCommand("start", "🏠 Bosh menyu"),
            BotCommand("admin", "👑 Admin panel"),
            BotCommand("id", "🆔 Telegram ID"),
        ])
    except Exception as e:
        print(f"⚠️ Setup: {e}")


# ═══════════════════════════════════════════════════════════════
# MAJBURIY OBUNA
# ═══════════════════════════════════════════════════════════════
def check_member_status(chat_id, user_id):
    """
    True  — a'zo
    False — a'zo emas
    None  — tekshirib bo'lmadi
    """
    try:
        m = bot.get_chat_member(chat_id, user_id)
        if isinstance(m, (ChatMemberLeft, ChatMemberBanned)):
            return False
        if isinstance(m, (ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner)):
            return True
        if isinstance(m, ChatMemberRestricted):
            return m.is_member
        return False
    except Exception as e:
        print(f"⚠️ check_member({chat_id},{user_id}): {e}")
        return None


def check_subscription(uid):
    """Barcha kanallar bo'yicha tekshirish."""
    if is_admin(uid):
        return True
    if gs("force_sub_enabled") != "1":
        return True

    channels = get_channels()
    if not channels:
        return True

    for ch in channels:
        st = check_member_status(ch["chat_id"], uid)
        if st is True:
            continue
        if st is False:
            return False
        # None — tekshirib bo'lmadi
        if ch["check_mode"] == "request":
            if has_pending(uid, ch["id"]):
                continue
            return False
        continue
    return True


def sub_prompt(chat_id, uid):
    """Obuna xabari."""
    channels = get_channels()
    if not channels:
        return

    text = "🔒 <b>Botdan foydalanish uchun obuna bo'ling:</b>\n\n"
    kb = InlineKeyboardMarkup()

    for i, ch in enumerate(channels, 1):
        st = check_member_status(ch["chat_id"], uid)
        if st is True:
            icon = "✅"
        elif ch["check_mode"] == "request" and has_pending(uid, ch["id"]):
            icon = "⏳"
        else:
            icon = "❌"

        text += f"{icon} {i}. <b>{ch['name']}</b>\n"

        if st is True:
            continue

        if ch["username"]:
            uname = ch["username"].replace("@", "")
            kb.add(InlineKeyboardButton(f"📢 {ch['name']}",
                   url=f"https://t.me/{uname}"))
        elif ch["invite_link"]:
            btn = "📨 So'rov yuborish" if ch["check_mode"] == "request" else f"📢 {ch['name']}"
            kb.add(InlineKeyboardButton(btn, url=ch["invite_link"]))

    kb.add(InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub"))
    bot.send_message(chat_id, text, reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
# REPLY MENYU
# ═══════════════════════════════════════════════════════════════
def main_menu():
    """Asosiy reply keyboard (oddiy matn)."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("🧩 QR yaratish"),
        KeyboardButton("🎬 Reklama / Unlock"),
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


# ═══════════════════════════════════════════════════════════════
# BOT BUYRUQLARI
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(m):
    uid = m.from_user.id
    is_new = upsert_user({
        "id": uid,
        "username": m.from_user.username,
        "first_name": m.from_user.first_name,
        "last_name": m.from_user.last_name,
        "language_code": m.from_user.language_code,
    })

    # Referal tekshirish
    args = m.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
            if is_new and add_ref(ref_id, uid):
                try:
                    bot.send_message(ref_id, "🎉 Yangi referal! +10 bonus QR")
                except Exception:
                    pass
        except (ValueError, IndexError):
            pass

    # Obuna tekshirish
    if not check_subscription(uid):
        sub_prompt(m.chat.id, uid)
        return

    u = get_user(uid)
    unlock = u.get("unlock_count", 0) if u else 0

    bot.send_message(
        m.chat.id,
        f"👋 Salom, <b>{m.from_user.first_name or 'do\'stim'}</b>!\n\n"
        f"🎯 <b>QR Master</b> — universal QR kod generator\n\n"
        f"🎁 Bepul limit: <b>{gs('free_qr_count')} ta</b>\n"
        f"🔓 Qo'shimcha: <b>{unlock} ta</b>\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=main_menu()
    )

    if is_admin(uid):
        bot.send_message(m.chat.id, "👑 Admin panel: /admin")


@bot.message_handler(commands=["admin"])
def cmd_admin(m):
    if not is_admin(m.from_user.id):
        bot.reply_to(m, "🚫 Siz admin emassiz")
        return
    show_admin_menu(m.chat.id)


@bot.message_handler(commands=["id"])
def cmd_id(m):
    bot.reply_to(m, f"🆔 <code>{m.from_user.id}</code>")


# ═══════════════════════════════════════════════════════════════
# QR YARATISH — INLINE WEBAPP
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🧩 QR yaratish")
def open_qr_app(m):
    if not check_subscription(m.from_user.id):
        sub_prompt(m.chat.id, m.from_user.id)
        return

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🚀 QR Master ilovasini ochish",
           web_app=WebAppInfo(url=WEBAPP_URL)))

    bot.send_message(
        m.chat.id,
        "🎯 <b>QR kod yaratish</b>\n\n"
        "Quyidagi tugma orqali Mini App'ni oching.\n"
        "QR avtomatik saqlanadi! ✅",
        reply_markup=kb
    )


@bot.message_handler(func=lambda m: m.text == "🎬 Reklama / Unlock")
def open_ads_app(m):
    if not check_subscription(m.from_user.id):
        sub_prompt(m.chat.id, m.from_user.id)
        return

    u = get_user(m.from_user.id)
    unlock = u.get("unlock_count", 0) if u else 0

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎬 Reklama sahifasini ochish",
           web_app=WebAppInfo(url=WEBAPP_URL)))

    bot.send_message(
        m.chat.id,
        f"🎬 <b>Reklama / Unlock</b>\n\n"
        f"🎁 Bepul limit: <b>{gs('free_qr_count')} ta</b>\n"
        f"🔓 Unlock: <b>{unlock} ta</b>\n\n"
        "Reklama ko'rib <b>+3 QR</b> unlock oling!",
        reply_markup=kb
    )


# ═══════════════════════════════════════════════════════════════
# MENING QR LARIM
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📜 Mening QR larim")
def my_qrs(m):
    uid = m.from_user.id
    if not check_subscription(uid):
        sub_prompt(m.chat.id, uid)
        return
    show_user_qrs(m.chat.id, uid, 0)


def show_user_qrs(chat_id, uid, offset):
    total = cnt_qrs(uid)
    if total == 0:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🚀 QR yaratish",
               web_app=WebAppInfo(url=WEBAPP_URL)))
        bot.send_message(chat_id,
            "📜 Sizda hali QR kodlar yo'q.\n\n🧩 Mini App orqali yarating!",
            reply_markup=kb)
        return

    qrs = get_qrs(uid, 5, offset)
    text = f"📜 <b>Sizning QR kodlaringiz</b> ({offset+1}-{offset+len(qrs)}/{total})\n\n"

    for i, qr in enumerate(qrs, 1):
        text += f"{offset+i}. <b>{qr['name']}</b>\n"
        text += f"   <code>{qr['qr_data'][:40]}...</code>\n\n"

    kb = InlineKeyboardMarkup(row_width=4)
    for qr in qrs:
        kb.add(
            InlineKeyboardButton(f"📥 #{qr['id']}", callback_data=f"qr_dl:{qr['id']}"),
            InlineKeyboardButton(f"🗑 #{qr['id']}", callback_data=f"qr_del:{qr['id']}")
        )

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"qr_pg:{offset-5}"))
    if offset + 5 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"qr_pg:{offset+5}"))
    if nav:
        kb.row(*nav)

    bot.send_message(chat_id, text, reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
# REFERAL TIZIMI
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "👥 Referal tizimi")
def ref_menu(m):
    uid = m.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    total = cnt_refs(uid)
    bonus = gi("invite_bonus_qr", 10)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📋 Havolani nusxalash", callback_data="copy_ref"))
    kb.add(InlineKeyboardButton("📤 Ulashish",
           url=f"https://t.me/share/url?url={link}&text=QR Master"))
    if total > 0:
        kb.add(InlineKeyboardButton(f"👥 Ro'yxat ({total})", callback_data="ref_list:0"))

    bot.send_message(
        m.chat.id,
        f"👥 <b>Referal tizimi</b>\n\n"
        f"🔗 Sizning havolangiz:\n<code>{link}</code>\n\n"
        f"👥 Taklif qilganlar: <b>{total}</b>\n"
        f"🎁 Har bir referal uchun: <b>+{bonus} bonus QR</b>",
        reply_markup=kb
    )


def show_referrals(chat_id, uid, offset, msg_id=None):
    total = cnt_refs(uid)
    refs = get_refs(uid, 10, offset)

    text = f"👥 <b>Referallaringiz</b> ({offset+1}-{offset+len(refs)}/{total})\n\n"
    for i, r in enumerate(refs, 1):
        name = r.get("first_name") or "Foydalanuvchi"
        uname = f"@{r['username']}" if r.get("username") else "—"
        text += f"{offset+i}. {name} ({uname})\n"

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


# ═══════════════════════════════════════════════════════════════
# STATISTIKA
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def user_stats(m):
    uid = m.from_user.id
    u = get_user(uid)
    if not u:
        return
    refs = cnt_refs(uid)

    bot.send_message(
        m.chat.id,
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Ism: {u['first_name'] or '—'}\n"
        f"🧩 Yaratilgan QR: <b>{u['qr_count']}</b>\n"
        f"📢 Reklama ko'rilgan: <b>{u['ad_count']}</b>\n"
        f"🔓 Unlock: <b>{u.get('unlock_count', 0)}</b>\n"
        f"👥 Referallar: <b>{refs}</b>"
    )


# ═══════════════════════════════════════════════════════════════
# SUPPORT
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "✉️ Adminga xabar")
def support_start(m):
    msg = bot.send_message(m.chat.id, "✉️ <b>Adminga xabar</b>\n\nXabaringizni yozing:")
    bot.register_next_step_handler(msg, save_support_msg)


def save_support_msg(message):
    if message.content_type != "text":
        bot.reply_to(message, "❌ Faqat matn yuborish mumkin")
        return

    uid = message.from_user.id
    mid = save_support(uid, message.text)
    bot.reply_to(message, "✅ Xabaringiz adminga yuborildi!")

    for admin_id in all_admins():
        try:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💬 Javob berish", callback_data=f"reply:{mid}"))
            bot.send_message(
                admin_id,
                f"✉️ <b>Yangi xabar</b> (#{mid})\n\n"
                f"👤 @{message.from_user.username or '—'}\n"
                f"🆔 <code>{uid}</code>\n\n"
                f"💬 {message.text}",
                reply_markup=kb
            )
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════════════
def show_admin_menu(chat_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Statistika", callback_data="adm_stats"),
        InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="adm_users:0"),
    )
    kb.add(
        InlineKeyboardButton("📣 Broadcast", callback_data="adm_bc"),
        InlineKeyboardButton("🔒 Majburiy obuna", callback_data="adm_subs"),
    )
    kb.add(
        InlineKeyboardButton("👑 Adminlar", callback_data="adm_admins"),
        InlineKeyboardButton("📋 Xabarlar", callback_data="adm_msgs"),
    )
    kb.add(InlineKeyboardButton("📢 Reklama sozlamalari", callback_data="adm_ads"))
    bot.send_message(chat_id, "👑 <b>ADMIN PANEL</b>", reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    uid = call.from_user.id
    data = call.data
    bot.answer_callback_query(call.id)

    # ─── FOYDALANUVCHI ───
    if data == "check_sub":
        if check_subscription(uid):
            try:
                bot.edit_message_text("✅ <b>Obuna tasdiqlandi!</b>",
                                     uid, call.message.message_id)
            except Exception:
                pass
            bot.send_message(uid, "🏠 Bosh menyu:", reply_markup=main_menu())
        else:
            marked = False
            for ch in get_channels():
                if check_member_status(ch["chat_id"], uid) is None and ch["check_mode"] == "request":
                    save_pending(uid, ch["id"])
                    marked = True
            if marked:
                bot.answer_callback_query(call.id, "⏳ So'rov qayd etildi!", show_alert=True)
                if check_subscription(uid):
                    bot.send_message(uid, "✅ Endi mumkin:", reply_markup=main_menu())
            else:
                bot.answer_callback_query(call.id, "❌ Obuna emas!", show_alert=True)

    elif data == "copy_ref":
        bot.send_message(uid, f"<code>https://t.me/{BOT_USERNAME}?start=ref_{uid}</code>")

    elif data.startswith("ref_list:"):
        show_referrals(uid, uid, int(data.split(":")[1]), call.message.message_id)

    elif data == "ref_back":
        bot.delete_message(uid, call.message.message_id)
        ref_menu(call.message)

    elif data.startswith("qr_pg:"):
        bot.delete_message(uid, call.message.message_id)
        show_user_qrs(uid, uid, int(data.split(":")[1]))

    elif data.startswith("qr_dl:"):
        qid = int(data.split(":")[1])
        qr = get_qr(qid, uid)
        if qr:
            try:
                img = make_qr_png(qr["qr_data"])
                bot.send_photo(uid, InputFile(img, f"qr_{qid}.png"),
                    caption=f"📥 <b>{qr['name']}</b>\n\n<code>{qr['qr_data'][:100]}</code>")
            except Exception as e:
                bot.send_message(uid, f"❌ {e}")

    elif data.startswith("qr_del:"):
        qid = int(data.split(":")[1])
        if del_qr(qid, uid):
            bot.delete_message(uid, call.message.message_id)
            show_user_qrs(uid, uid, 0)

    # ─── ADMIN ───
    elif not is_admin(uid):
        return

    elif data == "adm_stats":
        s = global_stats()
        text = (
            f"📊 <b>UMUMIY STATISTIKA</b>\n\n"
            f"👥 Jami foydalanuvchilar: <b>{s['users_total']}</b>\n"
            f"📅 Bugun yangi: <b>{s['users_today']}</b>\n"
            f"🧩 Jami QR kodlar: <b>{s['qr_total']}</b>\n"
            f"📢 Reklama ko'rilgan: <b>{s['ads_total']}</b>"
        )
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("adm_users:"):
        offset = int(data.split(":")[1])
        total = cnt_users()
        users = users_page(offset, 10)
        text = f"👥 <b>Foydalanuvchilar</b> ({offset+1}-{offset+len(users)}/{total})\n\n"
        for i, u in enumerate(users, 1):
            text += f"{offset+i}. {u['first_name'] or '—'} | <code>{u['telegram_id']}</code>\n"
        kb = InlineKeyboardMarkup()
        nav = []
        if offset > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_users:{offset-10}"))
        nav.append(InlineKeyboardButton(f"{offset//10+1}/{(total-1)//10+1}",
                                        callback_data="none"))
        if offset + 10 < total:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_users:{offset+10}"))
        kb.row(*nav)
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_bc":
        msg = bot.send_message(uid, "📣 Barcha foydalanuvchilarga xabar:")
        bot.register_next_step_handler(msg, confirm_broadcast)

    elif data == "adm_bc_ok":
        text = getattr(bot, "_bc_text", "")
        users = q("SELECT telegram_id FROM users WHERE status='active'")
        sent = failed = 0
        st = bot.send_message(uid, f"⏳ 0/{len(users)}")
        for i, u in enumerate(users, 1):
            try:
                bot.send_message(u["telegram_id"], text)
                sent += 1
                time.sleep(0.05)
            except Exception:
                failed += 1
        bot.edit_message_text(f"✅ {sent} | ❌ {failed}", uid, st.message_id)

    elif data == "adm_subs":
        show_subscription_menu(uid, call.message.message_id)

    elif data == "adm_toggle_sub":
        cur = gs("force_sub_enabled", "0")
        ss("force_sub_enabled", "0" if cur == "1" else "1")
        show_subscription_menu(uid, call.message.message_id)

    elif data == "adm_add_ch":
        msg = bot.send_message(
            uid,
            "📢 <b>Kanal qo'shish</b>\n\n"
            "3 xil usul:\n\n"
            "1️⃣ <b>Public</b> — <code>@username</code>\n"
            "2️⃣ <b>Yopiq</b> — <code>https://t.me/+XXX</code>\n"
            "3️⃣ <b>Forward</b> — kanaldagi xabarni forward qiling\n\n"
            "⚠️ Bot kanalga <b>admin</b> qilingan bo'lsin!"
        )
        bot.register_next_step_handler(msg, add_channel_step)

    elif data.startswith("adm_del_ch:"):
        del_channel(int(data.split(":")[1]))
        bot.answer_callback_query(call.id, "✅")
        show_subscription_menu(uid, call.message.message_id)

    elif data == "adm_admins":
        admins = all_admins()
        text = "👑 <b>Adminlar</b>\n\n"
        for a in admins:
            marker = " (asosiy)" if a in ADMIN_IDS else ""
            text += f"• <code>{a}</code>{marker}\n"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("➕ Qo'shish", callback_data="adm_add_admin"))
        for e in q("SELECT telegram_id FROM admins"):
            kb.add(InlineKeyboardButton(f"🗑 {e['telegram_id']}",
                   callback_data=f"adm_rm_admin:{e['telegram_id']}"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_add_admin":
        msg = bot.send_message(uid, "👑 Yangi admin Telegram ID:")
        bot.register_next_step_handler(msg, add_admin_step)

    elif data.startswith("adm_rm_admin:"):
        aid = int(data.split(":")[1])
        if aid in ADMIN_IDS:
            bot.answer_callback_query(call.id, "❌ Asosiy adminni o'chirib bo'lmaydi", show_alert=True)
        else:
            remove_admin(aid)
            bot.answer_callback_query(call.id, "✅")

    elif data == "adm_msgs":
        msgs = open_supports(10)
        text = "📋 <b>Ochiq xabarlar</b>\n\n"
        if msgs:
            for m in msgs:
                text += f"#{m['id']}: {m['message'][:50]}\n"
        else:
            text += "Yo'q"
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_ads":
        text = (
            f"📢 <b>Reklama sozlamalari</b>\n\n"
            f"🧩 Bepul QR: <b>{gs('free_qr_count')}</b>\n"
            f"📢 Har N QR da: <b>{gs('qr_per_ad')}</b>\n"
            f"🎁 Referal bonus: <b>+{gs('invite_bonus_qr')}</b>"
        )
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🧩 Bepul QR", callback_data="adm_set:free_qr_count"),
            InlineKeyboardButton("📢 Har N", callback_data="adm_set:qr_per_ad"),
        )
        kb.add(InlineKeyboardButton("🎁 Referal bonus", callback_data="adm_set:invite_bonus_qr"))
        kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("adm_set:"):
        key = data.split(":")[1]
        msg = bot.send_message(uid, f"<b>{key}</b> uchun yangi qiymat (raqam):")
        bot.register_next_step_handler(msg, set_setting_step, key)

    elif data == "adm_back":
        bot.delete_message(uid, call.message.message_id)
        show_admin_menu(uid)

    elif data.startswith("reply:"):
        mid = int(data.split(":")[1])
        msg = bot.send_message(uid, f"💬 Xabar #{mid} uchun javob:")
        bot.register_next_step_handler(msg, send_admin_reply, mid)

    elif data == "none":
        pass


# ═══════════════════════════════════════════════════════════════
# ADMIN YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════════════════════════════
def show_subscription_menu(uid, msg_id):
    channels = all_channels()
    enabled = gs("force_sub_enabled") == "1"
    text = f"🔒 <b>Majburiy obuna</b>\n\nHolat: {'✅ Yoqilgan' if enabled else '❌ O\'chirilgan'}\n\n"
    if channels:
        text += "<b>Kanallar:</b>\n"
        for i, ch in enumerate(channels, 1):
            mode = "📢 Ommaviy" if ch["check_mode"] == "member" else "📨 So'rov"
            text += f"{i}. {ch['name']} ({mode})\n   <code>{ch['chat_id']}</code>\n"
    else:
        text += "Kanallar yo'q\n"

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Kanal qo'shish", callback_data="adm_add_ch"))
    kb.add(InlineKeyboardButton(
        f"{'🔴 O\'chirish' if enabled else '🟢 Yoqish'}",
        callback_data="adm_toggle_sub"))
    for ch in channels:
        kb.add(InlineKeyboardButton(f"🗑 {ch['name']}",
               callback_data=f"adm_del_ch:{ch['id']}"))
    kb.add(InlineKeyboardButton("🔙", callback_data="adm_back"))

    try:
        bot.edit_message_text(text, uid, msg_id, reply_markup=kb)
    except Exception:
        bot.send_message(uid, text, reply_markup=kb)


def confirm_broadcast(message):
    if message.content_type != "text":
        bot.reply_to(message, "❌ Faqat matn")
        return
    bot._bc_text = message.text
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Yuborish", callback_data="adm_bc_ok"),
        InlineKeyboardButton("❌ Bekor", callback_data="adm_back"),
    )
    bot.send_message(
        message.chat.id,
        f"📣 <b>Xabar:</b>\n\n{message.text}\n\n<b>Tasdiqlaysizmi?</b>",
        reply_markup=kb
    )


def add_channel_step(message):
    """Kanal qo'shish — 3 usul."""
    try:
        username = invite_link = chat_id = name = None
        mode = "member"

        # 1-USUL: Forward
        if message.forward_from_chat:
            chat = message.forward_from_chat
            chat_id = str(chat.id)
            name = chat.title or "Kanal"
            username = f"@{chat.username}" if chat.username else None
            if username:
                invite_link = f"https://t.me/{chat.username}"
            else:
                try:
                    invite_link = bot.export_chat_invite_link(chat.id)
                    mode = "request"
                except Exception:
                    pass

        # 2,3-USUL: Matn
        elif message.content_type == "text":
            text = message.text.strip()

            if text.startswith("@") or (not text.startswith("http") and "/" not in text):
                username = text if text.startswith("@") else f"@{text}"
                try:
                    chat = bot.get_chat(username)
                    chat_id = str(chat.id)
                    name = chat.title or username
                    invite_link = f"https://t.me/{username.replace('@','')}"
                except Exception as e:
                    bot.send_message(message.chat.id,
                        f"❌ Botni kanalga admin qiling!\n<code>{e}</code>")
                    return

            elif "t.me/+" in text or "t.me/joinchat/" in text:
                invite_link = text
                try:
                    chat = bot.get_chat(text)
                    chat_id = str(chat.id)
                    name = chat.title or "Yopiq kanal"
                    username = chat.username
                    mode = "request"
                except Exception as e:
                    bot.send_message(message.chat.id, f"❌ <code>{e}</code>")
                    return

            elif "t.me/" in text:
                username = "@" + text.split("t.me/")[-1].split("/")[0].split("?")[0]
                try:
                    chat = bot.get_chat(username)
                    chat_id = str(chat.id)
                    name = chat.title or username
                    invite_link = f"https://t.me/{username.replace('@','')}"
                except Exception as e:
                    bot.send_message(message.chat.id, f"❌ <code>{e}</code>")
                    return
            else:
                bot.send_message(message.chat.id,
                    "❌ Format xato.\n\n"
                    "Yuboring:\n"
                    "• <code>@username</code>\n"
                    "• <code>https://t.me/+XXX</code>\n"
                    "• <b>forward</b>")
                return
        else:
            bot.send_message(message.chat.id, "❌ Faqat matn yoki forward")
            return

        if not chat_id:
            bot.send_message(message.chat.id, "❌ Chat ID olinmadi")
            return

        add_channel(chat_id, name, username, invite_link, mode)

        admin_status = "⚠️ Bot admin emas!"
        try:
            ba = bot.get_chat_member(chat_id, bot.get_me().id)
            if ba.status in ("administrator", "creator"):
                admin_status = "✅ Bot admin"
        except Exception:
            pass

        bot.send_message(message.chat.id,
            f"✅ <b>Kanal qo'shildi!</b>\n\n"
            f"📌 {name}\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"🔗 {username or '—'}\n"
            f"🔐 {'📨 So\'rov' if mode == 'request' else '📢 Ommaviy'}\n"
            f"{admin_status}")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xato: {e}")


def add_admin_step(message):
    try:
        aid = int(message.text.strip())
        if aid in all_admins():
            bot.send_message(message.chat.id, "❌ Allaqachon admin")
            return
        add_admin(aid)
        bot.send_message(message.chat.id, f"✅ Admin qo'shildi: <code>{aid}</code>")
        try:
            bot.send_message(aid, "🎉 Siz admin bo'ldingiz! /admin buyrug'ini bering")
        except Exception:
            pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ Noto'g'ri ID")


def set_setting_step(message, key):
    try:
        val = int(message.text.strip())
        ss(key, str(val))
        bot.send_message(message.chat.id, f"✅ <b>{key}</b> = {val}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Faqat raqam")


def send_admin_reply(message, mid):
    if message.content_type != "text":
        bot.reply_to(message, "❌")
        return
    support = get_support(mid)
    if not support:
        return
    reply_support(mid, message.text)
    try:
        bot.send_message(support["user_id"], f"📬 <b>Admin javobi:</b>\n\n{message.text}")
        bot.send_message(message.chat.id, "✅ Yuborildi")
    except Exception:
        bot.send_message(message.chat.id, "❌ Yuborib bo'lmadi")


# ═══════════════════════════════════════════════════════════════
# JOIN REQUEST HANDLER
# ═══════════════════════════════════════════════════════════════
@bot.chat_join_request_handler(func=lambda r: True)
def on_join_request(req):
    uid = req.from_user.id
    save_pending(uid, req.chat.id)

    for admin_id in all_admins():
        try:
            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("✅ Tasdiqlash",
                                     callback_data=f"jr_ok:{req.chat.id}:{uid}"),
                InlineKeyboardButton("❌ Rad etish",
                                     callback_data=f"jr_no:{req.chat.id}:{uid}"),
            )
            bot.send_message(
                admin_id,
                f"📨 <b>Yangi so'rov</b>\n\n"
                f"👤 {req.from_user.full_name} (@{req.from_user.username or '—'})\n"
                f"🆔 <code>{uid}</code>\n"
                f"📢 <b>{req.chat.title}</b>",
                reply_markup=kb
            )
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("jr_"))
def on_join_action(call):
    if call.from_user.id not in all_admins():
        bot.answer_callback_query(call.id, "🚫")
        return
    p = call.data.split(":")
    try:
        if p[0] == "jr_ok":
            bot.approve_chat_join_request(int(p[1]), int(p[2]))
            bot.answer_callback_query(call.id, "✅ Tasdiqlandi")
            try:
                bot.send_message(int(p[2]), "✅ Kanaldagi so'rovingiz tasdiqlandi!")
            except Exception:
                pass
        else:
            bot.decline_chat_join_request(int(p[1]), int(p[2]))
            bot.answer_callback_query(call.id, "❌ Rad etildi")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                     reply_markup=None)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ {e}", show_alert=True)


# ───────────────────────────────────────────────────────────────
# KEYINGI: 3-QISM (Flask + Auth + HTML Mini App)
# ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════
# FLASK APP
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
CORS(app, origins="*")


@app.after_request
def cors_headers(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Telegram-Init-Data'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return r


# ═══════════════════════════════════════════════════════════════
# TELEGRAM AUTH
# ═══════════════════════════════════════════════════════════════
def validate_init_data(init_data):
    """
    Telegram WebApp initData imzosini tekshiradi.
    Rasmiy algoritm: HMAC_SHA256("WebAppData", bot_token)
    """
    if not init_data:
        raise ValueError("initData yo'q")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)

    if not received_hash:
        raise ValueError("hash parametri yo'q")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc, received_hash):
        raise ValueError("Imzo noto'g'ri")

    auth_date = int(parsed.get("auth_date", 0))
    if time.time() - auth_date > 86400:
        raise ValueError("initData muddati o'tgan")

    user_json = parsed.get("user")
    if not user_json:
        raise ValueError("Foydalanuvchi ma'lumotlari yo'q")

    return json.loads(user_json)


def auth_required(f):
    """Decorator — Telegram + obuna tekshirish."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        try:
            tg = validate_init_data(init_data)
        except ValueError as e:
            print(f"❌ Auth: {e}")
            return jsonify({"detail": str(e)}), 401

        if not check_subscription(tg["id"]):
            return jsonify({"detail": "Obuna kerak", "need_sub": True}), 403

        return f(tg, *args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════════
# HTML — MINI APP
# ═══════════════════════════════════════════════════════════════
HTML_PAGE = r'''<!DOCTYPE html>
<html lang="uz" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>QR Master</title>

<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script src="//libtl.com/sdk.js" data-zone="11990967" data-sdk="show_11990967"></script>

<style>
:root {
  --bg: #ffffff;
  --fg: #0f172a;
  --muted: #64748b;
  --card: #f1f5f9;
  --primary: #6366f1;
  --primary-2: #8b5cf6;
  --border: #e2e8f0;
  --success: #22c55e;
  --danger: #ef4444;
  --warning: #f59e0b;
  --radius: 16px;
}
[data-theme="dark"] {
  --bg: #0f172a;
  --fg: #f1f5f9;
  --muted: #94a3b8;
  --card: #1e293b;
  --border: #334155;
}
* { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--fg);
  padding-bottom: 80px;
  min-height: 100dvh;
  overflow-x: hidden;
}

/* HEADER */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 800;
  font-size: 19px;
}
.logo-mark {
  width: 34px; height: 34px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 900; font-size: 15px;
  box-shadow: 0 4px 12px rgba(99,102,241,.3);
}
.avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #06b6d4, var(--primary));
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 700; font-size: 14px;
}

/* MAIN */
.main { padding: 0 16px; }

/* HERO */
.hero {
  margin: 16px 0;
  padding: 22px;
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #fff;
  box-shadow: 0 10px 30px rgba(99,102,241,.35);
}
.hero h2 { font-size: 20px; margin-bottom: 6px; font-weight: 800; }
.hero p { font-size: 13px; opacity: .9; }

/* SECTION TITLE */
.st {
  font-size: 15px;
  font-weight: 700;
  margin: 22px 0 12px;
}

/* GRID */
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.tc {
  background: var(--card);
  border: none;
  border-radius: 14px;
  padding: 14px 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: var(--fg);
  font-family: inherit;
  transition: transform .15s;
}
.tc:active { transform: scale(.94); }
.ti { font-size: 24px; }
.tl { font-size: 11px; text-align: center; font-weight: 600; line-height: 1.2; }

/* BOTTOM NAV */
.nav {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  display: flex;
  background: var(--bg);
  border-top: 1px solid var(--border);
  padding: 8px 0 calc(8px + env(safe-area-inset-bottom));
  z-index: 100;
}
.nb {
  flex: 1;
  background: none;
  border: none;
  color: var(--muted);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 4px;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: color .2s;
}
.nb.active { color: var(--primary); }
.nb .ico { font-size: 20px; }

/* PAGE */
.page { display: none; animation: fade .25s ease; }
.page.active { display: block; }
@keyframes fade {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}

/* FORM */
.field { margin-bottom: 14px; }
.field label {
  display: block;
  font-size: 13px;
  color: var(--muted);
  margin-bottom: 6px;
  font-weight: 600;
}
.input, .select, .textarea {
  width: 100%;
  padding: 14px 16px;
  background: var(--card);
  border: 1.5px solid transparent;
  border-radius: 14px;
  font-size: 15px;
  color: var(--fg);
  outline: none;
  font-family: inherit;
  transition: border-color .2s;
}
.input:focus, .textarea:focus, .select:focus { border-color: var(--primary); }
.textarea { resize: vertical; min-height: 80px; }

/* BUTTONS */
.btn {
  width: 100%;
  padding: 16px;
  border: none;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;
  transition: transform .15s;
}
.btn:active { transform: scale(.97); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.bp {
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #fff;
  box-shadow: 0 6px 20px rgba(99,102,241,.35);
}
.bg { background: var(--card); color: var(--fg); }
.bw {
  background: linear-gradient(135deg, var(--warning), var(--danger));
  color: #fff;
}
.bs {
  background: linear-gradient(135deg, #22c55e, #16a34a);
  color: #fff;
}

/* QR RESULT */
.qr-r {
  margin-top: 20px;
  padding: 20px;
  border-radius: var(--radius);
  background: var(--card);
  text-align: center;
}
.qr-r canvas { border-radius: 12px; max-width: 100%; height: auto; }
.qa { display: flex; gap: 8px; margin-top: 14px; }
.qa .btn { padding: 12px; font-size: 13px; }

/* TOAST */
.tw {
  position: fixed;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
  max-width: 90vw;
}
.toast {
  padding: 12px 20px;
  border-radius: 12px;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  text-align: center;
  animation: tin .3s ease;
  box-shadow: 0 4px 12px rgba(0,0,0,.15);
}
.toast.success { background: var(--success); }
.toast.error { background: var(--danger); }
.toast.info { background: var(--primary); }
@keyframes tin {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: none; }
}

/* EMPTY */
.empty {
  text-align: center;
  padding: 40px 20px;
  color: var(--muted);
  font-size: 14px;
}
.empty .ico { font-size: 44px; display: block; margin-bottom: 10px; opacity: .5; }

/* HISTORY ITEM */
.hi {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: var(--card);
  border-radius: 14px;
  margin-bottom: 8px;
}
.hi-i { flex: 1; min-width: 0; }
.hi-i h4 {
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hi-i p {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ic {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  border: none;
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* PROFILE CARD */
.pc {
  padding: 20px;
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #fff;
  text-align: center;
  margin-bottom: 16px;
  box-shadow: 0 10px 30px rgba(99,102,241,.35);
}
.pc .av {
  width: 70px;
  height: 70px;
  border-radius: 50%;
  background: rgba(255,255,255,.2);
  margin: 0 auto 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 800;
}
.pc h3 { font-size: 17px; margin-bottom: 4px; }
.pc p { font-size: 13px; opacity: .85; }
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 16px;
}
.stat {
  background: rgba(255,255,255,.15);
  padding: 10px;
  border-radius: 12px;
}
.stat b { display: block; font-size: 18px; font-weight: 800; }
.stat span { font-size: 10px; opacity: .85; }

/* LOADING */
.loading {
  position: fixed;
  inset: 0;
  background: rgba(15,23,42,.55);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.loading.on { display: flex; }
.spin {
  width: 42px;
  height: 42px;
  border: 3px solid rgba(255,255,255,.25);
  border-top-color: #fff;
  border-radius: 50%;
  animation: sp .8s linear infinite;
}
@keyframes sp { to { transform: rotate(360deg); } }

/* REF LINK */
.rl {
  background: var(--card);
  padding: 12px;
  border-radius: 10px;
  font-family: 'Courier New', monospace;
  font-size: 11px;
  word-break: break-all;
  margin: 10px 0;
  border: 1px solid var(--border);
  color: var(--primary);
}

/* LOGO UPLOAD */
.lu {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  background: var(--card);
  border-radius: 14px;
  border: 2px dashed var(--border);
  cursor: pointer;
  margin-bottom: 10px;
}
.lu img {
  width: 50px;
  height: 50px;
  object-fit: contain;
  border-radius: 8px;
  background: var(--bg);
}

/* ERROR PAGE */
.ep {
  padding: 60px 20px;
  text-align: center;
}
.ep .ico { font-size: 64px; margin-bottom: 20px; }
.ep h2 {
  color: var(--primary);
  margin-bottom: 10px;
  font-size: 20px;
}
.ep p { color: var(--muted); line-height: 1.6; font-size: 14px; }

/* BADGE */
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
}
.badge.ok { background: rgba(34,197,94,.15); color: var(--success); }
.badge.warn { background: rgba(245,158,11,.15); color: var(--warning); }
.badge.err { background: rgba(239,68,68,.15); color: var(--danger); }
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="logo">
    <div class="logo-mark">QR</div>
    <span>QR Master</span>
  </div>
  <div class="avatar" id="av">U</div>
</div>

<!-- MAIN -->
<div class="main" id="mainC">

  <!-- HOME -->
  <div class="page active" id="p-home">
    <div class="hero">
      <h2>🎯 QR Master</h2>
      <p>20+ turdagi QR kod yaratish va dizayn</p>
    </div>
    <div class="st">QR Turlari</div>
    <div class="grid" id="tg"></div>
    <div class="st">So'nggi QR kodlar</div>
    <div id="rl"></div>
  </div>

  <!-- CREATE -->
  <div class="page" id="p-create">
    <div class="st" id="ct">QR kod</div>
    <div id="df"></div>

    <div class="st">🎨 Dizayn</div>
    <div class="field">
      <label>QR rangi</label>
      <input type="color" id="fc" value="#6366f1"
             style="width:100%;height:50px;border:none;border-radius:12px">
    </div>
    <div class="field">
      <label>Fon rangi</label>
      <input type="color" id="bc" value="#ffffff"
             style="width:100%;height:50px;border:none;border-radius:12px">
    </div>
    <div class="field">
      <label>📷 Logo (ixtiyoriy)</label>
      <div class="lu" id="lb" onclick="document.getElementById('lf').click()">
        <img id="lp" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='50' height='50'%3E%3Ctext x='50%25' y='55%25' text-anchor='middle' font-size='24' fill='%2364748b'%3E%2B%3C/text%3E%3C/svg%3E">
        <div style="flex:1">
          <div style="font-weight:700;font-size:14px">Logo yuklash</div>
          <div style="font-size:11px;color:var(--muted)">PNG, JPG - 500 KB</div>
        </div>
      </div>
      <input type="file" id="lf" accept="image/*" hidden>
      <button class="btn bg" id="cl" style="display:none;padding:8px;font-size:12px">
        🗑 O'chirish
      </button>
    </div>
    <div class="field">
      <label>O'lcham</label>
      <select class="select" id="qs">
        <option value="256">256 × 256</option>
        <option value="512" selected>512 × 512</option>
        <option value="1024">1024 × 1024</option>
      </select>
    </div>

    <button class="btn bp" id="gb">✨ QR kod yaratish</button>
    <button class="btn bg" id="bb" style="margin-top:8px">← Orqaga</button>

    <div class="qr-r" id="qr" style="display:none">
      <div id="qc"></div>
      <div class="qa">
        <button class="btn bp" id="dlb">⬇️ Yuklab olish</button>
      </div>
    </div>
  </div>

  <!-- ADS -->
  <div class="page" id="p-ads">
    <div class="st">🎬 Reklama / Unlock</div>
    <div class="hero">
      <h2>🔓 Qo'shimcha QR limit</h2>
      <p>Reklama ko'ring yoki do'st taklif qiling</p>
    </div>

    <div class="hi">
      <div class="hi-i">
        <h4>🎁 Bepul limit</h4>
        <p id="fc2">5 ta</p>
      </div>
      <span class="badge ok">FREE</span>
    </div>

    <div class="hi">
      <div class="hi-i">
        <h4>🔓 Unlock qilingan</h4>
        <p id="uc">0 ta</p>
      </div>
      <span class="badge warn">UNLOCK</span>
    </div>

    <button class="btn bw" id="wab" style="margin-top:14px">
      ▶️ Reklama ko'rish (+3 QR)
    </button>
    <button class="btn bp" id="ib" style="margin-top:8px">
      👥 Do'st taklif qilish (+10 QR)
    </button>

    <div class="st">📊 Statistika</div>
    <div class="hi">
      <div class="hi-i">
        <h4>Ko'rilgan reklamalar</h4>
        <p id="at">0</p>
      </div>
      <span class="badge ok" id="ab">+0</span>
    </div>
  </div>

  <!-- HISTORY -->
  <div class="page" id="p-hist">
    <div class="st">🕐 Tarix</div>
    <div id="hl"></div>
  </div>

  <!-- REFERRAL -->
  <div class="page" id="p-ref">
    <div class="st">👥 Referal tizimi</div>
    <div class="hero">
      <h2>🎁 Har referal +10 QR</h2>
      <p>Do'stni taklif qiling va bonus oling</p>
    </div>

    <div class="field">
      <label>🔗 Sizning havolangiz:</label>
      <div class="rl" id="rlink">—</div>
    </div>

    <button class="btn bp" id="cr">📋 Nusxalash</button>
    <button class="btn bg" id="sr" style="margin-top:8px">📤 Ulashish</button>

    <div class="st">Referallaringiz (<span id="rc">0</span>)</div>
    <div id="rlist"></div>
  </div>

  <!-- PROFILE -->
  <div class="page" id="p-prof">
    <div class="pc">
      <div class="av" id="pav">U</div>
      <h3 id="pn">Foydalanuvchi</h3>
      <p id="pu">@username</p>
      <div class="stats">
        <div class="stat"><b id="s1">0</b><span>QR</span></div>
        <div class="stat"><b id="s2">0</b><span>Reklama</span></div>
        <div class="stat"><b id="s3">0</b><span>Unlock</span></div>
        <div class="stat"><b id="s4">0</b><span>Referal</span></div>
      </div>
    </div>

    <button class="btn bg" id="tb">🌗 Mavzuni almashtirish</button>
    <button class="btn bg" id="rl2" style="margin-top:8px">🔄 Ma'lumotlarni yangilash</button>
  </div>

</div>

<!-- NAV -->
<nav class="nav">
  <button class="nb active" data-page="home"><span class="ico">🏠</span>Asosiy</button>
  <button class="nb" data-page="ads"><span class="ico">🎬</span>Reklama</button>
  <button class="nb" data-page="ref"><span class="ico">👥</span>Referal</button>
  <button class="nb" data-page="hist"><span class="ico">🕐</span>Tarix</button>
  <button class="nb" data-page="prof"><span class="ico">👤</span>Profil</button>
</nav>

<div class="tw" id="tw"></div>
<div class="loading" id="ld"><div class="spin"></div></div>

<script>
// JavaScript kodi 4-qismda
</script>
</body>
</html>
'''

# ───────────────────────────────────────────────────────────────
# KEYINGI: 4-QISM (JavaScript + API + Ishga tushirish)
# ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/", methods=["GET", "HEAD"])
def index():
    return Response(HTML_PAGE, mimetype="text/html")


@app.route("/health", methods=["GET", "HEAD"])
def health():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat()})


@app.route("/api/me", methods=["POST", "GET", "OPTIONS"])
def api_me():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    try:
        tg = validate_init_data(init_data)
    except ValueError as e:
        print(f"❌ Auth: {e}")
        return jsonify({"detail": str(e)}), 401

    upsert_user(tg)
    u = get_user(tg["id"])
    if not u:
        return jsonify({"detail": "Topilmadi"}), 404

    return jsonify({
        "id": u["telegram_id"],
        "username": u["username"],
        "first_name": u["first_name"],
        "qr_count": u["qr_count"],
        "ad_count": u["ad_count"],
        "unlock_count": u.get("unlock_count", 0),
        "is_admin": is_admin(tg["id"]),
        "referrals": cnt_refs(tg["id"]),
        "bot_username": BOT_USERNAME,
        "free_qr": gs("free_qr_count", "5"),
        "qr_per_ad": gs("qr_per_ad", "2"),
        "need_sub": not check_subscription(tg["id"]),
    })


@app.route("/api/qr/save", methods=["POST", "OPTIONS"])
@auth_required
def api_qr_save(tg):
    body = request.get_json(silent=True) or {}
    data = (body.get("data") or "").strip()

    if not data:
        return jsonify({"detail": "Bo'sh"}), 400
    if len(data) > 5000:
        return jsonify({"detail": "Juda uzun"}), 400

    upsert_user(tg)
    qr_type = body.get("qr_type") or "universal"
    name = (body.get("name") or "QR")[:255]
    add_qr(tg["id"], qr_type, name, data)

    u = get_user(tg["id"])
    total = u["qr_count"]
    N = gi("free_qr_count", 5)   # 5 ta bepul
    M = gi("qr_per_ad", 2)       # keyin har 2 tada reklama

    # ═══════════════════════════════════════════════════════════
    # REKLAMA MANTIG'I — N bepul, keyin (M bepul + 1 AD)
    # ═══════════════════════════════════════════════════════════
    # Pattern (N=5, M=2):
    #   total 1-5    ❌ Bepul
    #   total 6      🎬 AD
    #   total 7-8    ❌ Bepul
    #   total 9      🎬 AD
    #   total 10-11  ❌ Bepul
    #   total 12     🎬 AD
    #   ...
    # ═══════════════════════════════════════════════════════════
    show_ad = False
    if total > N and M >= 0:
        if (total - N - 1) % (M + 1) == 0:
            show_ad = True

    # ═══ BOTGA XABAR ═══
    try:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(
            "📜 Mening QR larim",
            web_app=WebAppInfo(url=WEBAPP_URL)
        ))
        if show_ad:
            kb.add(InlineKeyboardButton(
                "🎬 Reklama ko'rish (+3 QR)",
                web_app=WebAppInfo(url=WEBAPP_URL)
            ))

        text = (f"✅ <b>Yangi QR kod saqlandi!</b>\n\n"
                f"📌 <b>{name}</b>\n"
                f"🔧 Turi: <code>{qr_type}</code>\n"
                f"📊 Jami: <b>{total}</b> ta\n")
        if show_ad:
            text += f"\n🎬 <b>Bepul limit tugadi!</b>\nReklama ko'rib +3 QR unlock oling."

        bot.send_message(tg["id"], text, reply_markup=kb)
    except Exception as e:
        print(f"⚠️ Bot xabar: {e}")

    return jsonify({
        "ok": True,
        "total": total,
        "show_ad": show_ad,
    })


@app.route("/api/qr/ad", methods=["POST", "OPTIONS"])
@auth_required
def api_qr_ad(tg):
    log_ad(tg["id"], "rewarded", "completed")

    bonus = gi("qr_per_ad", 2)
    qx("UPDATE users SET unlock_count=unlock_count+? WHERE telegram_id=?",
       (bonus, tg["id"]))

    u = get_user(tg["id"])
    return jsonify({
        "unlock": u.get("unlock_count", 0),
        "ad_count": u["ad_count"],
    })


@app.route("/api/qr/list", methods=["GET", "OPTIONS"])
@auth_required
def api_qr_list(tg):
    qrs = get_qrs(tg["id"], 50, 0)
    return jsonify([
        {
            "id": q["id"],
            "name": q["name"],
            "qr_type": q["qr_type"],
            "qr_data": q["qr_data"],
            "created_at": q["created_at"],
        }
        for q in qrs
    ])


@app.route("/api/qr/<int:qid>", methods=["DELETE", "OPTIONS"])
@auth_required
def api_qr_delete(tg, qid):
    if del_qr(qid, tg["id"]):
        return jsonify({"ok": True})
    return jsonify({"detail": "Topilmadi"}), 404


@app.route("/api/ref/list", methods=["GET", "OPTIONS"])
@auth_required
def api_ref_list(tg):
    refs = get_refs(tg["id"], 50, 0)
    return jsonify({
        "total": cnt_refs(tg["id"]),
        "refs": [
            {
                "first_name": r.get("first_name"),
                "username": r.get("username"),
                "created_at": r.get("created_at"),
            }
            for r in refs
        ]
    })


# ═══════════════════════════════════════════════════════════════
# ISHGA TUSHIRISH
# ═══════════════════════════════════════════════════════════════
def run_bot():
    """Botni alohida thread'da."""
    while True:
        try:
            bot.remove_webhook()
            setup_bot()
            print("✅ Bot tayyor")
            print("=" * 55)
            print("🚀 Telegram'da /start bosing")
            print("=" * 55)
            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30,
            )
        except KeyboardInterrupt:
            print("\n⏹ Bot to'xtatildi")
            break
        except Exception as e:
            print(f"⚠️ Bot xatosi: {e}")
            print("5 sekunddan keyin qayta urinish...")
            time.sleep(5)


if __name__ == "__main__":
    # Bot thread
    threading.Thread(target=run_bot, daemon=True).start()

    time.sleep(3)

    print("=" * 55)
    print(f"🌐 Server: http://0.0.0.0:{PORT}")
    print(f"🔗 Mini App: {WEBAPP_URL}")
    print(f"👤 Admin: {ADMIN_IDS}")
    print(f"💰 Monetag: {MONETAG_ZONE}")
    print("=" * 55)

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        threaded=True,
    )
