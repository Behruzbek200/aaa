# -*- coding: utf-8 -*-
"""
QR MASTER — 20+ turdagi QR kod yaratish
Ishga tushirish: python bot.py
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
        "PIL": "Pillow"
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
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
            except subprocess.CalledProcessError as e:
                print(f"❌ {pkg} o'rnatilmadi: {e}")
                sys.exit(1)
        print("✅ O'rnatildi! Qayta ishga tushirish...")
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    print("✅ Barcha kutubxonalar tayyor")


install_packages()

# Import asosiy kutubxonalar
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand, InputFile,
    MenuButtonWebApp, ChatMemberLeft, ChatMemberBanned,
    ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner,
    ChatMemberRestricted
)
import qrcode


# ═══════════════════════════════════════════════════════════════
# SOZLAMALAR — RENDER ENVIRONMENT VARIABLES ORQALI
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = ""
WEBAPP_URL   = os.getenv("WEBAPP_URL", "http://localhost:8000")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
MONETAG_ZONE = os.getenv("MONETAG_ZONE", "11990967")
PORT         = int(os.getenv("PORT", 8000))
DB_FILE      = os.getenv("DB_FILE", "qr_master.db")
UPLOAD_DIR   = os.getenv(
    "UPLOAD_DIR",
    "/data/uploads" if os.path.exists("/data") else "uploads"
)

# Papkalarni yaratish
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)

print("=" * 55)
print("🚀 QR MASTER")
print("=" * 55)
print(f"📁 DB: {DB_FILE}")
print(f"📁 Upload: {UPLOAD_DIR}")
print(f"🌐 URL: {WEBAPP_URL}")
print(f"👤 Admin: {ADMIN_IDS}")
print("=" * 55)


# ═══════════════════════════════════════════════════════════════
# DATABASE SCHEMA
# ═══════════════════════════════════════════════════════════════
def init_database():
    """Barcha jadvallarni yaratish."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Foydalanuvchilar
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        language TEXT DEFAULT 'uz',
        status TEXT DEFAULT 'active',
        qr_count INTEGER DEFAULT 0,
        ad_count INTEGER DEFAULT 0,
        unlock_count INTEGER DEFAULT 0,
        created_at TEXT,
        last_active TEXT
    )""")

    # QR tarixi
    c.execute("""CREATE TABLE IF NOT EXISTS qr_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        qr_type TEXT,
        name TEXT,
        qr_data TEXT,
        payload_hash TEXT,
        created_at TEXT
    )""")

    # Majburiy obuna kanallari
    c.execute("""CREATE TABLE IF NOT EXISTS channels(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        name TEXT,
        username TEXT,
        invite_link TEXT,
        check_mode TEXT DEFAULT 'member',
        is_active INTEGER DEFAULT 1
    )""")

    # Sozlamalar
    c.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT
    )""")

    # Referallar
    c.execute("""CREATE TABLE IF NOT EXISTS referrals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER UNIQUE,
        status TEXT DEFAULT 'active',
        created_at TEXT
    )""")

    # Yordam xabarlari
    c.execute("""CREATE TABLE IF NOT EXISTS support_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        admin_reply TEXT,
        status TEXT DEFAULT 'open',
        created_at TEXT
    )""")

    # Reklama hodisalari
    c.execute("""CREATE TABLE IF NOT EXISTS ad_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        format TEXT,
        event_type TEXT,
        created_at TEXT
    )""")

    # Adminlar
    c.execute("""CREATE TABLE IF NOT EXISTS admins(
        telegram_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        created_at TEXT
    )""")

    # Kutilayotgan obunalar (yopiq kanallar uchun)
    c.execute("""CREATE TABLE IF NOT EXISTS pending_subs(
        user_id INTEGER,
        channel_id INTEGER,
        requested_at TEXT,
        PRIMARY KEY(user_id, channel_id)
    )""")

    # Indekslar
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_user ON qr_history(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ref_referrer ON referrals(referrer_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ad_created ON ad_events(created_at)")

    # Standart sozlamalar
    defaults = {
        "force_sub_enabled": "0",
        "referral_enabled": "1",
        "monetag_enabled": "1",
        "free_qr_count": "1",
        "qr_per_ad": "3",
        "invite_bonus_qr": "10",
    }
    for key, val in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, val))

    conn.commit()
    conn.close()
    print("✅ Database tayyor")


init_database()

# ───────────────────────────────────────────────────────────────
# KEYINGI QISM: 2-QISM (Database funksiyalari)
# ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════
# DATABASE YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════════════════════════════

def db():
    """Yangi database ulanish."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def q(sql, args=(), one=False):
    """Query bajarish."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql, args)
        rows = cursor.fetchall()
        conn.commit()
        if one:
            return dict(rows[0]) if rows else None
        return [dict(r) for r in rows]
    finally:
        conn.close()


def q_exec(sql, args=()):
    """Execute (INSERT/UPDATE/DELETE) — ID qaytaradi."""
    conn = sqlite3.connect(DB_FILE)
    try:
        cursor = conn.execute(sql, args)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────
# SOZLAMALAR
# ───────────────────────────────────────────────────────────────
def get_setting(key, default=""):
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


def set_setting(key, value):
    q_exec("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, str(value)))


def get_int_setting(key, default=0):
    """Raqamli sozlamalar uchun."""
    try:
        return int(get_setting(key, str(default)))
    except (ValueError, TypeError):
        return default


# ───────────────────────────────────────────────────────────────
# ADMINLAR
# ───────────────────────────────────────────────────────────────
def is_admin(uid):
    """Admin ekanligini tekshirish."""
    if uid in ADMIN_IDS:
        return True
    r = q("SELECT 1 FROM admins WHERE telegram_id=?", (uid,), one=True)
    return bool(r)


def add_admin(uid, added_by=0):
    """Yangi admin qo'shish."""
    q_exec(
        "INSERT OR IGNORE INTO admins(telegram_id, added_by, created_at) VALUES(?, ?, ?)",
        (uid, added_by, datetime.utcnow().isoformat())
    )


def remove_admin(uid):
    """Adminni o'chirish."""
    q_exec("DELETE FROM admins WHERE telegram_id=?", (uid,))


def get_all_admins():
    """Barcha adminlar ro'yxati."""
    extras = q("SELECT telegram_id FROM admins")
    return list(ADMIN_IDS) + [r["telegram_id"] for r in extras]


# ───────────────────────────────────────────────────────────────
# FOYDALANUVCHILAR
# ───────────────────────────────────────────────────────────────
def get_user(uid):
    """Foydalanuvchini olish."""
    return q("SELECT * FROM users WHERE telegram_id=?", (uid,), one=True)


def upsert_user(tg_data):
    """Foydalanuvchi yaratish yoki yangilash."""
    uid = tg_data["id"]
    now = datetime.utcnow().isoformat()

    existing = q("SELECT 1 FROM users WHERE telegram_id=?", (uid,), one=True)
    if not existing:
        q_exec(
            """INSERT INTO users(telegram_id, username, first_name, last_name,
                language, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                uid,
                tg_data.get("username"),
                tg_data.get("first_name"),
                tg_data.get("last_name"),
                tg_data.get("language_code", "uz"),
                now,
                now
            )
        )
        return True  # yangi
    else:
        q_exec(
            """UPDATE users SET username=?, first_name=?, last_name=?, last_active=?
                WHERE telegram_id=?""",
            (
                tg_data.get("username"),
                tg_data.get("first_name"),
                tg_data.get("last_name"),
                now,
                uid
            )
        )
        return False  # mavjud


def update_user_status(uid, status):
    """Foydalanuvchi statusini o'zgartirish."""
    q_exec("UPDATE users SET status=? WHERE telegram_id=?", (status, uid))


def update_user_language(uid, lang):
    """Tilni o'zgartirish."""
    q_exec("UPDATE users SET language=? WHERE telegram_id=?", (lang, uid))


def get_users_paginated(offset=0, limit=10):
    """Foydalanuvchilar ro'yxati (sahifalar)."""
    return q(
        "SELECT * FROM users ORDER BY last_active DESC LIMIT ? OFFSET ?",
        (limit, offset)
    )


def count_users():
    """Jami foydalanuvchilar soni."""
    r = q("SELECT COUNT(*) as c FROM users", one=True)
    return r["c"] if r else 0


def count_users_today():
    """Bugun ro'yxatdan o'tganlar."""
    r = q(
        "SELECT COUNT(*) as c FROM users WHERE date(created_at)=date('now')",
        one=True
    )
    return r["c"] if r else 0


def search_users(query):
    """Foydalanuvchilarni qidirish."""
    like = f"%{query}%"
    if query.isdigit():
        return q(
            """SELECT * FROM users WHERE telegram_id = ?
                OR username LIKE ? OR first_name LIKE ?
                ORDER BY last_active DESC LIMIT 20""",
            (int(query), like, like)
        )
    return q(
        "SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ? LIMIT 20",
        (like, like)
    )


# ───────────────────────────────────────────────────────────────
# QR KODLAR
# ───────────────────────────────────────────────────────────────
def add_qr(uid, qr_type, name, qr_data):
    """QR yozuvini qo'shish."""
    q_exec(
        """INSERT INTO qr_history(user_id, qr_type, name, qr_data, payload_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
        (
            uid,
            qr_type,
            name,
            qr_data,
            hashlib.sha256(qr_data.encode()).hexdigest(),
            datetime.utcnow().isoformat()
        )
    )
    q_exec("UPDATE users SET qr_count = qr_count + 1 WHERE telegram_id=?", (uid,))


def get_qrs(uid, limit=50, offset=0):
    """Foydalanuvchi QR kodlari."""
    return q(
        """SELECT id, qr_type, name, qr_data, created_at
            FROM qr_history WHERE user_id=?
            ORDER BY id DESC LIMIT ? OFFSET ?""",
        (uid, limit, offset)
    )


def get_qr(qid, uid):
    """Bitta QR olish."""
    return q(
        "SELECT * FROM qr_history WHERE id=? AND user_id=?",
        (qid, uid),
        one=True
    )


def count_qrs(uid):
    """Jami QR soni."""
    r = q("SELECT COUNT(*) as c FROM qr_history WHERE user_id=?", (uid,), one=True)
    return r["c"] if r else 0


def delete_qr(qid, uid):
    """QR o'chirish."""
    existing = q(
        "SELECT 1 FROM qr_history WHERE id=? AND user_id=?",
        (qid, uid),
        one=True
    )
    if existing:
        q_exec("DELETE FROM qr_history WHERE id=?", (qid,))
        q_exec(
            "UPDATE users SET qr_count = MAX(0, qr_count - 1) WHERE telegram_id=?",
            (uid,)
        )
        return True
    return False


def count_all_qrs():
    """Umumiy QR soni (admin uchun)."""
    r = q("SELECT COUNT(*) as c FROM qr_history", one=True)
    return r["c"] if r else 0


# ───────────────────────────────────────────────────────────────
# REFERALLAR
# ───────────────────────────────────────────────────────────────
def add_referral(referrer_id, referred_id):
    """Referal qo'shish."""
    if referrer_id == referred_id:
        return False
    try:
        q_exec(
            "INSERT INTO referrals(referrer_id, referred_id, created_at) VALUES(?, ?, ?)",
            (referrer_id, referred_id, datetime.utcnow().isoformat())
        )
        bonus = get_int_setting("invite_bonus_qr", 10)
        q_exec(
            "UPDATE users SET unlock_count = unlock_count + ? WHERE telegram_id=?",
            (bonus, referrer_id)
        )
        return True
    except sqlite3.IntegrityError:
        return False


def count_referrals(uid):
    """Referallar soni."""
    r = q(
        "SELECT COUNT(*) as c FROM referrals WHERE referrer_id=?",
        (uid,),
        one=True
    )
    return r["c"] if r else 0


def get_referrals(uid, limit=50, offset=0):
    """Referallar ro'yxati."""
    return q(
        """SELECT r.*, u.first_name, u.username
            FROM referrals r
            LEFT JOIN users u ON u.telegram_id = r.referred_id
            WHERE r.referrer_id=?
            ORDER BY r.id DESC LIMIT ? OFFSET ?""",
        (uid, limit, offset)
    )


# ───────────────────────────────────────────────────────────────
# MAJBURIY OBUNA KANALLARI
# ───────────────────────────────────────────────────────────────
def get_channels():
    """Faol kanallar."""
    return q("SELECT * FROM channels WHERE is_active=1 ORDER BY id")


def get_all_channels():
    """Barcha kanallar (admin uchun)."""
    return q("SELECT * FROM channels ORDER BY id")


def add_channel(chat_id, name, username=None, invite_link=None, check_mode="member"):
    """Kanal qo'shish."""
    return q_exec(
        """INSERT INTO channels(chat_id, name, username, invite_link, check_mode)
            VALUES (?, ?, ?, ?, ?)""",
        (str(chat_id), name, username, invite_link, check_mode)
    )


def delete_channel(ch_id):
    """Kanal o'chirish."""
    q_exec("DELETE FROM channels WHERE id=?", (ch_id,))


def get_channel(ch_id):
    """Bitta kanal."""
    return q("SELECT * FROM channels WHERE id=?", (ch_id,), one=True)


# ───────────────────────────────────────────────────────────────
# PENDING (kutilayotgan obunalar — yopiq kanallar)
# ───────────────────────────────────────────────────────────────
def save_pending_sub(uid, ch_id):
    """So'rov yuborilganini qayd etish."""
    q_exec(
        """INSERT OR REPLACE INTO pending_subs(user_id, channel_id, requested_at)
            VALUES (?, ?, ?)""",
        (uid, ch_id, datetime.utcnow().isoformat())
    )


def has_pending_sub(uid, ch_id):
    """So'rov allaqachon yuborilganmi."""
    r = q(
        "SELECT 1 FROM pending_subs WHERE user_id=? AND channel_id=?",
        (uid, ch_id),
        one=True
    )
    return bool(r)


# ───────────────────────────────────────────────────────────────
# REKLAMA HODISALARI
# ───────────────────────────────────────────────────────────────
def log_ad_event(uid, ad_format="rewarded", event_type="completed"):
    """Reklama hodisasini qayd etish."""
    q_exec(
        """INSERT INTO ad_events(user_id, format, event_type, created_at)
            VALUES (?, ?, ?, ?)""",
        (uid, ad_format, event_type, datetime.utcnow().isoformat())
    )
    # Foydalanuvchi statistikasi
    if event_type == "completed":
        q_exec("UPDATE users SET ad_count = ad_count + 1 WHERE telegram_id=?", (uid,))


def count_ad_events(event_type="completed"):
    """Reklama hodisalari soni."""
    r = q(
        "SELECT COUNT(*) as c FROM ad_events WHERE event_type=?",
        (event_type,),
        one=True
    )
    return r["c"] if r else 0


# ───────────────────────────────────────────────────────────────
# YORDAM XABARLARI
# ───────────────────────────────────────────────────────────────
def save_support_message(uid, message):
    """Yordam xabari saqlash."""
    return q_exec(
        "INSERT INTO support_messages(user_id, message, created_at) VALUES (?, ?, ?)",
        (uid, message, datetime.utcnow().isoformat())
    )


def get_open_support_messages(limit=10):
    """Ochiq yordam xabarlari."""
    return q(
        """SELECT * FROM support_messages WHERE status='open'
            ORDER BY created_at DESC LIMIT ?""",
        (limit,)
    )


def get_support_message(mid):
    """Bitta xabar."""
    return q("SELECT * FROM support_messages WHERE id=?", (mid,), one=True)


def reply_support_message(mid, reply):
    """Javob yozish."""
    q_exec(
        "UPDATE support_messages SET admin_reply=?, status='answered' WHERE id=?",
        (reply, mid)
    )


# ───────────────────────────────────────────────────────────────
# QR RASM YARATISH (Bot uchun)
# ───────────────────────────────────────────────────────────────
def make_qr_png(data):
    """QR kodni PNG bytes sifatida qaytarish."""
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


# ───────────────────────────────────────────────────────────────
# STATISTIKA (Admin uchun)
# ───────────────────────────────────────────────────────────────
def get_global_stats():
    """Umumiy statistika."""
    return {
        "users_total": count_users(),
        "users_today": count_users_today(),
        "qr_total": count_all_qrs(),
        "ads_total": count_ad_events("completed"),
    }


# ───────────────────────────────────────────────────────────────
# KEYINGI QISM: 3-QISM (Telegram bot handlers)
# ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════
# TELEGRAM BOT YARATISH
# ═══════════════════════════════════════════════════════════════
if not BOT_TOKEN:
    print("❌ BOT_TOKEN bo'sh! Environment variable'ga qo'shing")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def setup_bot():
    """Bot menu button va username ni sozlash."""
    global BOT_USERNAME
    try:
        me = bot.get_me()
        BOT_USERNAME = me.username
        print(f"✅ Bot: @{BOT_USERNAME}")

        # Menu button (asosiy "🚀 QR Master" tugma)
        try:
            bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🚀 QR Master",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            )
            print(f"✅ Menu button: {WEBAPP_URL}")
        except Exception as e:
            print(f"⚠️ Menu button xato: {e}")

        # Bot description
        try:
            bot.set_my_description(
                "QR Master — 20+ turdagi QR kod yaratish va saqlash boti.\n\n"
                "URL, matn, Wi-Fi, kontakt, video, audio, PDF va boshqa turlar."
            )
            bot.set_my_short_description("Universal QR kod generator")
        except Exception as e:
            print(f"⚠️ Description xato: {e}")

        # Komandalar
        bot.set_my_commands([
            BotCommand("start", "🏠 Bosh menyu"),
            BotCommand("admin", "👑 Admin panel"),
            BotCommand("id", "🆔 Telegram ID"),
        ])
    except Exception as e:
        print(f"⚠️ Setup xato: {e}")


# ═══════════════════════════════════════════════════════════════
# MAJBURIY OBUNA TEKSHIRISH
# ═══════════════════════════════════════════════════════════════
def check_member_status(chat_id, user_id):
    """
    Kanal a'zoligini tekshiradi.
    True  — a'zo
    False — a'zo emas
    None  — tekshirib bo'lmadi (bot admin emas)
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
    """Barcha kanallar bo'yicha obunani tekshirish."""
    # Admin uchun har doim True
    if is_admin(uid):
        return True

    # O'chirilgan bo'lsa — True
    if get_setting("force_sub_enabled") != "1":
        return True

    channels = get_channels()
    if not channels:
        return True

    for ch in channels:
        status = check_member_status(ch["chat_id"], uid)

        if status is True:
            continue

        if status is False:
            return False

        # status is None — bot admin emas yoki xato
        if ch["check_mode"] == "request":
            if has_pending_sub(uid, ch["id"]):
                continue
            return False

        # "member" rejimi lekin bot admin emas — o'tkazib yuboramiz
        continue

    return True


def sub_prompt(chat_id, uid):
    """Obuna talab qiluvchi xabar."""
    channels = get_channels()
    if not channels:
        return

    text = "🔒 <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>\n\n"
    kb = InlineKeyboardMarkup()

    for i, ch in enumerate(channels, 1):
        status = check_member_status(ch["chat_id"], uid)

        if status is True:
            icon = "✅"
        elif ch["check_mode"] == "request" and has_pending_sub(uid, ch["id"]):
            icon = "⏳"
        else:
            icon = "❌"

        text += f"{icon} {i}. <b>{ch['name']}</b>\n"

        if status is True:
            continue

        # Public kanal (username bor)
        if ch["username"]:
            uname = ch["username"].replace("@", "")
            kb.add(InlineKeyboardButton(f"📢 {ch['name']}", url=f"https://t.me/{uname}"))

        # Private kanal (invite link)
        elif ch["invite_link"]:
            btn_text = "📨 So'rov yuborish" if ch["check_mode"] == "request" else f"📢 {ch['name']}"
            kb.add(InlineKeyboardButton(btn_text, url=ch["invite_link"]))

    kb.add(InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub"))

    bot.send_message(chat_id, text, reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
# REPLY KEYBOARD
# ═══════════════════════════════════════════════════════════════
def main_menu():
    """Asosiy menyu tugmalari."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("🧩 QR yaratish", web_app=WebAppInfo(url=WEBAPP_URL)),
        KeyboardButton("🎬 Reklama / Unlock", web_app=WebAppInfo(url=WEBAPP_URL)),
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
            if is_new and add_referral(ref_id, uid):
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
        f"🎁 Bepul limit: <b>{get_setting('free_qr_count')} ta</b>\n"
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
    """Foydalanuvchi QR ro'yxati."""
    total = count_qrs(uid)
    if total == 0:
        bot.send_message(
            chat_id,
            "📜 Sizda hali QR kodlar yo'q.\n\n🧩 Mini App orqali yarating!",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🚀 QR yaratish", web_app=WebAppInfo(url=WEBAPP_URL))
            )
        )
        return

    qrs = get_qrs(uid, 5, offset)
    text = f"📜 <b>Sizning QR kodlaringiz</b> ({offset+1}-{offset+len(qrs)}/{total})\n\n"

    for i, qr in enumerate(qrs, 1):
        data_preview = qr["qr_data"][:40]
        text += f"{offset+i}. <b>{qr['name']}</b>\n"
        text += f"   <code>{data_preview}...</code>\n\n"

    kb = InlineKeyboardMarkup(row_width=4)
    for qr in qrs:
        kb.add(
            InlineKeyboardButton(f"📥 #{qr['id']}", callback_data=f"qr_dl:{qr['id']}"),
            InlineKeyboardButton(f"🗑 #{qr['id']}", callback_data=f"qr_del:{qr['id']}")
        )

    # Sahifalash
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
    total = count_referrals(uid)
    bonus = get_int_setting("invite_bonus_qr", 10)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📋 Havolani nusxalash", callback_data="copy_ref"))
    kb.add(InlineKeyboardButton(
        "📤 Ulashish",
        url=f"https://t.me/share/url?url={link}&text=QR Master - zo'r bot!"
    ))
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
    """Referallar ro'yxati."""
    total = count_referrals(uid)
    refs = get_referrals(uid, 10, offset)

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
    refs = count_referrals(uid)

    bot.send_message(
        m.chat.id,
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Ism: {u['first_name'] or '—'}\n"
        f"🧩 Yaratilgan QR: <b>{u['qr_count']}</b>\n"
        f"📢 Reklama ko'rilgan: <b>{u['ad_count']}</b>\n"
        f"🔓 Unlock: <b>{u.get('unlock_count', 0)}</b>\n"
        f"👥 Referallar: <b>{refs}</b>\n"
        f"📅 Ro'yxatdan: {u['created_at'][:10] if u.get('created_at') else '—'}"
    )


# ═══════════════════════════════════════════════════════════════
# YORDAM XABARI
# ═══════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "✉️ Adminga xabar")
def support_start(m):
    msg = bot.send_message(m.chat.id, "✉️ <b>Adminga xabar</b>\n\nXabaringizni yozing:")
    bot.register_next_step_handler(msg, save_support)


def save_support(message):
    if message.content_type != "text":
        bot.reply_to(message, "❌ Faqat matn yuborish mumkin")
        return

    uid = message.from_user.id
    mid = save_support_message(uid, message.text)
    bot.reply_to(message, "✅ Xabaringiz adminga yuborildi!")

    # Adminlarga yuborish
    for admin_id in get_all_admins():
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
# ADMIN PANEL MENYUSI
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
    kb.add(
        InlineKeyboardButton("📢 Reklama sozlamalari", callback_data="adm_ads"),
    )
    bot.send_message(chat_id, "👑 <b>ADMIN PANEL</b>", reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    uid = call.from_user.id
    data = call.data
    bot.answer_callback_query(call.id)

    # ─────────── FOYDALANUVCHI ───────────
    if data == "check_sub":
        if check_subscription(uid):
            try:
                bot.edit_message_text(
                    "✅ <b>Obuna tasdiqlandi!</b>",
                    uid, call.message.message_id
                )
            except Exception:
                pass
            bot.send_message(uid, "🏠 Bosh menyu:", reply_markup=main_menu())
        else:
            # Yopiq kanal uchun "so'rov yubordim" belgilash
            marked = False
            for ch in get_channels():
                if check_member_status(ch["chat_id"], uid) is None and ch["check_mode"] == "request":
                    save_pending_sub(uid, ch["id"])
                    marked = True

            if marked:
                bot.answer_callback_query(
                    call.id,
                    "⏳ So'rov qayd etildi! Tasdiq kutilmoqda.",
                    show_alert=True
                )
                if check_subscription(uid):
                    bot.send_message(uid, "✅ Endi foydalanishingiz mumkin:",
                                     reply_markup=main_menu())
            else:
                bot.answer_callback_query(call.id, "❌ Hali obuna emas!", show_alert=True)

    elif data == "copy_ref":
        bot.send_message(uid, f"<code>https://t.me/{BOT_USERNAME}?start=ref_{uid}</code>")

    elif data.startswith("ref_list:"):
        offset = int(data.split(":")[1])
        show_referrals(uid, uid, offset, call.message.message_id)

    elif data == "ref_back":
        bot.delete_message(uid, call.message.message_id)
        ref_menu(call.message)

    elif data.startswith("qr_pg:"):
        offset = int(data.split(":")[1])
        bot.delete_message(uid, call.message.message_id)
        show_user_qrs(uid, uid, offset)

    elif data.startswith("qr_dl:"):
        qid = int(data.split(":")[1])
        qr = get_qr(qid, uid)
        if qr:
            try:
                img = make_qr_png(qr["qr_data"])
                bot.send_photo(
                    uid,
                    InputFile(img, f"qr_{qid}.png"),
                    caption=f"📥 <b>{qr['name']}</b>\n\n<code>{qr['qr_data'][:100]}</code>"
                )
            except Exception as e:
                bot.send_message(uid, f"❌ Xato: {e}")
        else:
            bot.send_message(uid, "❌ Topilmadi")

    elif data.startswith("qr_del:"):
        qid = int(data.split(":")[1])
        if delete_qr(qid, uid):
            bot.answer_callback_query(call.id, "✅ O'chirildi")
            bot.delete_message(uid, call.message.message_id)
            show_user_qrs(uid, uid, 0)
        else:
            bot.answer_callback_query(call.id, "❌ Topilmadi", show_alert=True)

    # ─────────── ADMIN ───────────
    elif not is_admin(uid):
        return

    elif data == "adm_stats":
        s = get_global_stats()
        text = (
            f"📊 <b>UMUMIY STATISTIKA</b>\n\n"
            f"👥 Jami foydalanuvchilar: <b>{s['users_total']}</b>\n"
            f"📅 Bugun yangi: <b>{s['users_today']}</b>\n"
            f"🧩 Jami QR kodlar: <b>{s['qr_total']}</b>\n"
            f"📢 Reklama ko'rilgan: <b>{s['ads_total']}</b>"
        )
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("adm_users:"):
        offset = int(data.split(":")[1])
        total = count_users()
        users = get_users_paginated(offset, 10)

        text = f"👥 <b>Foydalanuvchilar</b> ({offset+1}-{offset+len(users)}/{total})\n\n"
        for i, u in enumerate(users, 1):
            name = u["first_name"] or "—"
            text += f"{offset+i}. {name} | <code>{u['telegram_id']}</code>\n"
            text += f"     QR: {u['qr_count']} | @{u['username'] or '—'}\n"

        kb = InlineKeyboardMarkup()
        nav = []
        if offset > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_users:{offset-10}"))
        nav.append(InlineKeyboardButton(
            f"{offset//10+1}/{(total-1)//10+1}",
            callback_data="none"
        ))
        if offset + 10 < total:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_users:{offset+10}"))
        kb.row(*nav)
        kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_bc":
        msg = bot.send_message(uid, "📣 Barcha foydalanuvchilarga yuboriladigan xabar:")
        bot.register_next_step_handler(msg, confirm_broadcast)

    elif data == "adm_bc_ok":
        text = getattr(bot, "_broadcast_text", "")
        users = q("SELECT telegram_id FROM users WHERE status='active'")
        sent, failed = 0, 0
        status_msg = bot.send_message(uid, f"⏳ Yuborilmoqda: 0/{len(users)}")
        for i, u in enumerate(users, 1):
            try:
                bot.send_message(u["telegram_id"], text)
                sent += 1
                time.sleep(0.05)
            except Exception:
                failed += 1
        bot.edit_message_text(
            f"✅ Yuborildi: {sent}\n❌ Xato: {failed}",
            uid, status_msg.message_id
        )

    elif data == "adm_subs":
        show_subscription_menu(uid, call.message.message_id)

    elif data == "adm_toggle_sub":
        cur = get_setting("force_sub_enabled", "0")
        set_setting("force_sub_enabled", "0" if cur == "1" else "1")
        show_subscription_menu(uid, call.message.message_id)

    elif data == "adm_add_ch":
        msg = bot.send_message(
            uid,
            "📢 <b>Kanal qo'shish</b>\n\n"
            "Formatlar:\n"
            "<code>@username|Nomi|member</code> — Ommaviy kanal\n"
            "<code>https://t.me/+XXX|Nomi|request</code> — Yopiq kanal"
        )
        bot.register_next_step_handler(msg, add_channel_step)

    elif data.startswith("adm_del_ch:"):
        ch_id = int(data.split(":")[1])
        delete_channel(ch_id)
        bot.answer_callback_query(call.id, "✅ O'chirildi")
        show_subscription_menu(uid, call.message.message_id)

    elif data == "adm_admins":
        all_admins = get_all_admins()
        text = "👑 <b>Adminlar</b>\n\n"
        for a in all_admins:
            marker = " (asosiy)" if a in ADMIN_IDS else ""
            text += f"• <code>{a}</code>{marker}\n"

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("➕ Admin qo'shish", callback_data="adm_add_admin"))
        # O'chirish tugmalari (faqat qo'shilgan adminlar uchun)
        extras = q("SELECT telegram_id FROM admins")
        for e in extras:
            kb.add(InlineKeyboardButton(
                f"🗑 {e['telegram_id']}",
                callback_data=f"adm_rm_admin:{e['telegram_id']}"
            ))
        kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_add_admin":
        msg = bot.send_message(uid, "👑 Yangi admin Telegram ID:")
        bot.register_next_step_handler(msg, add_admin_step)

    elif data.startswith("adm_rm_admin:"):
        aid = int(data.split(":")[1])
        remove_admin(aid)
        bot.answer_callback_query(call.id, "✅ O'chirildi")

    elif data == "adm_msgs":
        msgs = get_open_support_messages(10)
        text = "📋 <b>Ochiq xabarlar</b>\n\n"
        if not msgs:
            text += "Yo'q"
        else:
            for m in msgs:
                text += f"#{m['id']}: {m['message'][:50]}\n"

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data == "adm_ads":
        text = (
            f"📢 <b>Reklama sozlamalari</b>\n\n"
            f"Bepul QR: <b>{get_setting('free_qr_count')}</b>\n"
            f"Har N QR da reklama: <b>{get_setting('qr_per_ad')}</b>\n"
            f"Referal bonus: <b>+{get_setting('invite_bonus_qr')}</b>"
        )
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🧩 Bepul QR", callback_data="adm_set:free_qr_count"),
            InlineKeyboardButton("📢 Har N", callback_data="adm_set:qr_per_ad"),
        )
        kb.add(
            InlineKeyboardButton("🎁 Referal bonus", callback_data="adm_set:invite_bonus_qr")
        )
        kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back"))
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
        msg = bot.send_message(uid, f"💬 Xabar #{mid} uchun javobingizni yozing:")
        bot.register_next_step_handler(msg, send_admin_reply, mid)


# ═══════════════════════════════════════════════════════════════
# ADMIN YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════════════════════════════
def show_subscription_menu(uid, msg_id):
    """Obuna boshqaruvi."""
    channels = get_all_channels()
    enabled = get_setting("force_sub_enabled") == "1"

    text = f"🔒 <b>Majburiy obuna</b>\n\n"
    text += f"Holat: {'✅ Yoqilgan' if enabled else '❌ O\'chirilgan'}\n\n"

    if channels:
        text += "<b>Kanallar:</b>\n"
        for i, ch in enumerate(channels, 1):
            mode = "📢 Ommaviy" if ch["check_mode"] == "member" else "📨 So'rov"
            text += f"{i}. {ch['name']} ({mode})\n"
            text += f"   <code>{ch['chat_id']}</code>\n"
    else:
        text += "Kanallar yo'q\n"

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("➕ Kanal qo'shish", callback_data="adm_add_ch"))
    kb.add(InlineKeyboardButton(
        f"{'🔴 O\'chirish' if enabled else '🟢 Yoqish'}",
        callback_data="adm_toggle_sub"
    ))
    for ch in channels:
        kb.add(InlineKeyboardButton(
            f"🗑 {ch['name']}",
            callback_data=f"adm_del_ch:{ch['id']}"
        ))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back"))

    try:
        bot.edit_message_text(text, uid, msg_id, reply_markup=kb)
    except Exception:
        bot.send_message(uid, text, reply_markup=kb)


def confirm_broadcast(message):
    """Broadcast tasdiqlash."""
    if message.content_type != "text":
        bot.reply_to(message, "❌ Faqat matn yuborish mumkin")
        return
    bot._broadcast_text = message.text
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
    """Kanal qo'shish."""
    try:
        parts = message.text.split("|")
        if len(parts) < 3:
            raise ValueError("Format: @username|Nomi|member")

        raw_id = parts[0].strip()
        name = parts[1].strip()
        mode = parts[2].strip().lower()

        if mode not in ("member", "request"):
            mode = "member"

        username = None
        invite_link = None
        chat_id = raw_id

        # @username
        if raw_id.startswith("@"):
            username = raw_id
            try:
                chat = bot.get_chat(raw_id)
                chat_id = str(chat.id)
            except Exception as e:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ Botni kanalga admin qiling!\n<code>{e}</code>"
                )
            invite_link = f"https://t.me/{raw_id.replace('@', '')}"

        # https://t.me/+XXX
        elif raw_id.startswith("https://t.me/+"):
            invite_link = raw_id
            try:
                chat = bot.get_chat(raw_id)
                chat_id = str(chat.id)
                username = chat.username
            except Exception as e:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ Invite linkdan chat_id olib bo'lmadi. "
                    f"Botni kanalga admin qiling!\n<code>{e}</code>"
                )

        # Chat ID (raqam)
        else:
            chat_id = raw_id
            try:
                chat = bot.get_chat(raw_id)
                username = chat.username
                invite_link = chat.invite_link
            except Exception:
                pass

        add_channel(chat_id, name, username, invite_link, mode)
        bot.send_message(
            message.chat.id,
            f"✅ <b>Kanal qo'shildi!</b>\n\n"
            f"📌 {name}\n"
            f"🆔 <code>{chat_id}</code>\n"
            f"🔧 Rejim: <b>{mode}</b>"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xato: {e}")


def add_admin_step(message):
    """Admin qo'shish."""
    try:
        aid = int(message.text.strip())
        if aid in get_all_admins():
            bot.send_message(message.chat.id, "❌ Allaqachon admin")
            return
        add_admin(aid, message.from_user.id)
        bot.send_message(message.chat.id, f"✅ Admin qo'shildi: <code>{aid}</code>")
        try:
            bot.send_message(aid, "🎉 Siz admin bo'ldingiz! /admin buyrug'ini bering")
        except Exception:
            pass
    except ValueError:
        bot.send_message(message.chat.id, "❌ Noto'g'ri ID")


def set_setting_step(message, key):
    """Sozlama o'zgartirish."""
    try:
        val = int(message.text.strip())
        set_setting(key, str(val))
        bot.send_message(message.chat.id, f"✅ <b>{key}</b> = {val}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Faqat raqam kiriting")


def send_admin_reply(message, mid):
    """Admin javob yuborish."""
    if message.content_type != "text":
        bot.reply_to(message, "❌ Faqat matn")
        return

    support = get_support_message(mid)
    if not support:
        bot.send_message(message.chat.id, "❌ Xabar topilmadi")
        return

    reply_support_message(mid, message.text)

    try:
        bot.send_message(
            support["user_id"],
            f"📬 <b>Admindan javob:</b>\n\n{message.text}"
        )
        bot.send_message(message.chat.id, "✅ Javob yuborildi")
    except Exception:
        bot.send_message(message.chat.id, "❌ Foydalanuvchiga yuborib bo'lmadi")


# ═══════════════════════════════════════════════════════════════
# JOIN REQUEST HANDLER (yopiq kanallar)
# ═══════════════════════════════════════════════════════════════
@bot.chat_join_request_handler(func=lambda r: True)
def on_join_request(req):
    """Yopiq kanalga so'rov kelganda."""
    uid = req.from_user.id
    uname = req.from_user.username or "—"
    name = req.from_user.full_name

    # Pending belgilash
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO pending_subs(user_id, channel_id, requested_at)
                VALUES (?, ?, ?)""",
            (uid, str(req.chat.id), datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        conn.close()

    # Adminlarga xabar
    for admin_id in get_all_admins():
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
                f"👤 {name} (@{uname})\n"
                f"🆔 <code>{uid}</code>\n"
                f"📢 Kanal: <b>{req.chat.title}</b>",
                reply_markup=kb
            )
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("jr_"))
def on_join_request_action(call):
    """Join request tasdiqlash/rad etish."""
    if call.from_user.id not in get_all_admins():
        bot.answer_callback_query(call.id, "🚫")
        return

    parts = call.data.split(":")
    action = parts[0]
    chat_id = int(parts[1])
    user_id = int(parts[2])

    try:
        if action == "jr_ok":
            bot.approve_chat_join_request(chat_id, user_id)
            bot.answer_callback_query(call.id, "✅ Tasdiqlandi")
            try:
                bot.send_message(user_id, "✅ Kanaldagi so'rovingiz tasdiqlandi!")
            except Exception:
                pass
        else:
            bot.decline_chat_join_request(chat_id, user_id)
            bot.answer_callback_query(call.id, "❌ Rad etildi")

        bot.edit_message_reply_markup(
            call.message.chat.id, call.message.message_id, reply_markup=None
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Xato: {e}", show_alert=True)


# ───────────────────────────────────────────────────────────────
# KEYINGI QISM: 4-QISM (Flask + HTML Mini App boshlanishi)
# ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════
# FLASK APP — BACKEND + MINI APP HTML
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
CORS(app, origins="*")


@app.after_request
def add_cors_headers(r):
    """Har bir javobga CORS header qo'shish."""
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Telegram-Init-Data'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return r


# ═══════════════════════════════════════════════════════════════
# TELEGRAM AUTH — initData tekshirish
# ═══════════════════════════════════════════════════════════════
def validate_init_data(init_data):
    """
    Telegram WebApp initData imzosini tekshiradi.
    Rasmiy hujjat: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        raise ValueError("initData yo'q")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)

    if not received_hash:
        raise ValueError("hash parametri yo'q")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Imzo noto'g'ri")

    # auth_date tekshirish (24 soat)
    auth_date = int(parsed.get("auth_date", 0))
    if time.time() - auth_date > 86400:
        raise ValueError("initData muddati o'tgan")

    user_json = parsed.get("user")
    if not user_json:
        raise ValueError("Foydalanuvchi ma'lumotlari yo'q")

    return json.loads(user_json)


def auth_required(f):
    """Decorator: Telegram autentifikatsiyasini talab qiladi."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        init_data = request.headers.get("X-Telegram-Init-Data", "")
        try:
            tg_user = validate_init_data(init_data)
        except ValueError as e:
            print(f"❌ Auth xato: {e}")
            return jsonify({"detail": str(e)}), 401

        # Obuna tekshirish
        if not check_subscription(tg_user["id"]):
            return jsonify({
                "detail": "Obuna kerak",
                "need_sub": True
            }), 403

        return f(tg_user, *args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════════
# HTML — MINI APP (birinchi yarmi: head + CSS)
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

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  -webkit-tap-highlight-color: transparent;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--fg);
  padding-bottom: 80px;
  min-height: 100dvh;
  overflow-x: hidden;
}

/* ═══ HEADER ═══ */
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
  backdrop-filter: blur(10px);
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 800;
  font-size: 19px;
}
.logo-mark {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 900;
  font-size: 15px;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #06b6d4, var(--primary));
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(6, 182, 212, 0.3);
}

/* ═══ MAIN ═══ */
.main {
  padding: 0 16px;
}

/* ═══ HERO ═══ */
.hero {
  margin: 16px 0;
  padding: 22px;
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #fff;
  box-shadow: 0 10px 30px rgba(99, 102, 241, 0.35);
}
.hero h2 {
  font-size: 20px;
  margin-bottom: 6px;
  font-weight: 800;
}
.hero p {
  font-size: 13px;
  opacity: 0.9;
}

/* ═══ SECTION TITLE ═══ */
.st {
  font-size: 15px;
  font-weight: 700;
  margin: 22px 0 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.st small {
  font-size: 12px;
  color: var(--muted);
  font-weight: 500;
}

/* ═══ TYPE GRID ═══ */
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
  transition: transform 0.15s, box-shadow 0.15s;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
}
.tc:active {
  transform: scale(0.94);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.ti {
  font-size: 24px;
}
.tl {
  font-size: 11px;
  text-align: center;
  font-weight: 600;
  line-height: 1.2;
}

/* ═══ BOTTOM NAV ═══ */
.nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
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
  transition: color 0.2s;
}
.nb.active {
  color: var(--primary);
}
.nb .ico {
  font-size: 20px;
}

/* ═══ PAGES ═══ */
.page {
  display: none;
  animation: fadeIn 0.25s ease;
}
.page.active {
  display: block;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ═══ FORM ═══ */
.field {
  margin-bottom: 14px;
}
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
  transition: border-color 0.2s;
}
.input:focus, .textarea:focus, .select:focus {
  border-color: var(--primary);
}
.textarea {
  resize: vertical;
  min-height: 80px;
}

/* ═══ BUTTONS ═══ */
.btn {
  width: 100%;
  padding: 16px;
  border: none;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  font-family: inherit;
  transition: transform 0.15s, opacity 0.15s;
}
.btn:active {
  transform: scale(0.97);
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.bp {
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #fff;
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);
}
.bg {
  background: var(--card);
  color: var(--fg);
}
.bw {
  background: linear-gradient(135deg, var(--warning), var(--danger));
  color: #fff;
  box-shadow: 0 6px 20px rgba(245, 158, 11, 0.3);
}
.bs {
  background: linear-gradient(135deg, #22c55e, #16a34a);
  color: #fff;
  box-shadow: 0 6px 20px rgba(34, 197, 94, 0.3);
}

/* ═══ QR RESULT ═══ */
.qr-r {
  margin-top: 20px;
  padding: 20px;
  border-radius: var(--radius);
  background: var(--card);
  text-align: center;
}
.qr-r canvas {
  border-radius: 12px;
  max-width: 100%;
  height: auto;
}
.qa {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}
.qa .btn {
  padding: 12px;
  font-size: 13px;
}

/* ═══ TOAST ═══ */
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
  animation: toastIn 0.3s ease;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.toast.success { background: var(--success); }
.toast.error { background: var(--danger); }
.toast.info { background: var(--primary); }
@keyframes toastIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ═══ EMPTY STATE ═══ */
.empty {
  text-align: center;
  padding: 40px 20px;
  color: var(--muted);
  font-size: 14px;
}
.empty .ico {
  font-size: 44px;
  display: block;
  margin-bottom: 10px;
  opacity: 0.5;
}

/* ═══ HISTORY ITEM ═══ */
.hi {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: var(--card);
  border-radius: 14px;
  margin-bottom: 8px;
  transition: transform 0.15s;
}
.hi-i {
  flex: 1;
  min-width: 0;
}
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
  transition: background 0.15s;
}
.ic:active {
  background: var(--border);
}

/* ═══ PROFILE CARD ═══ */
.pc {
  padding: 20px;
  border-radius: var(--radius);
  background: linear-gradient(135deg, var(--primary), var(--primary-2));
  color: #fff;
  text-align: center;
  margin-bottom: 16px;
  box-shadow: 0 10px 30px rgba(99, 102, 241, 0.35);
}
.pc .av {
  width: 70px;
  height: 70px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  margin: 0 auto 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 800;
  backdrop-filter: blur(10px);
}
.pc h3 {
  font-size: 17px;
  margin-bottom: 4px;
}
.pc p {
  font-size: 13px;
  opacity: 0.85;
}
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 16px;
}
.stat {
  background: rgba(255, 255, 255, 0.15);
  padding: 10px;
  border-radius: 12px;
  backdrop-filter: blur(10px);
}
.stat b {
  display: block;
  font-size: 18px;
  font-weight: 800;
}
.stat span {
  font-size: 10px;
  opacity: 0.85;
}

/* ═══ LOADING ═══ */
.loading {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  backdrop-filter: blur(2px);
}
.loading.on {
  display: flex;
}
.spin {
  width: 42px;
  height: 42px;
  border: 3px solid rgba(255, 255, 255, 0.25);
  border-top-color: #fff;
  border-radius: 50%;
  animation: sp 0.8s linear infinite;
}
@keyframes sp {
  to { transform: rotate(360deg); }
}

/* ═══ REF LINK ═══ */
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

/* ═══ LOGO UPLOAD ═══ */
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
  transition: border-color 0.2s;
}
.lu:hover {
  border-color: var(--primary);
}
.lu img {
  width: 50px;
  height: 50px;
  object-fit: contain;
  border-radius: 8px;
  background: var(--bg);
}

/* ═══ ERROR PAGE ═══ */
.ep {
  padding: 60px 20px;
  text-align: center;
}
.ep .ico {
  font-size: 64px;
  margin-bottom: 20px;
}
.ep h2 {
  color: var(--primary);
  margin-bottom: 10px;
  font-size: 20px;
}
.ep p {
  color: var(--muted);
  line-height: 1.6;
  font-size: 14px;
}

/* ═══ BADGE ═══ */
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
}
.badge.ok {
  background: rgba(34, 197, 94, 0.15);
  color: var(--success);
}
.badge.warn {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
}
.badge.err {
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
}

/* ═══ ANIMATIONS ═══ */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.pulse {
  animation: pulse 1.5s ease-in-out infinite;
}

/* ═══ SCROLL BAR ═══ */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 10px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--muted);
}
</style>
</head>
<body>

<!-- ═══ HEADER ═══ -->
<div class="header">
  <div class="logo">
    <div class="logo-mark">QR</div>
    <span>QR Master</span>
  </div>
  <div class="avatar" id="av">U</div>
</div>

<!-- ═══ MAIN ═══ -->
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
        🗑 Logoni o'chirish
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
        <button class="btn bs" id="sb">💾 Saqlash</button>
      </div>
    </div>
  </div>

  <!-- ADS -->
  <div class="page" id="p-ads">
    <div class="st">🎬 Reklama / Unlock</div>
    <div class="hero">
      <h2>🔓 Qo'shimcha QR limit</h2>
      <p>Reklama ko'ring yoki do'stlarni taklif qiling</p>
    </div>

    <div class="hi">
      <div class="hi-i">
        <h4>🎁 Bepul limit</h4>
        <p id="fc2">1 ta</p>
      </div>
      <span class="badge ok" id="fb">FREE</span>
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

    <div class="st">
      Referallaringiz (<span id="rc">0</span>)
    </div>
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

<!-- ═══ BOTTOM NAV ═══ -->
<nav class="nav">
  <button class="nb active" data-page="home">
    <span class="ico">🏠</span>Asosiy
  </button>
  <button class="nb" data-page="ads">
    <span class="ico">🎬</span>Reklama
  </button>
  <button class="nb" data-page="ref">
    <span class="ico">👥</span>Referal
  </button>
  <button class="nb" data-page="hist">
    <span class="ico">🕐</span>Tarix
  </button>
  <button class="nb" data-page="prof">
    <span class="ico">👤</span>Profil
  </button>
</nav>

<!-- ═══ TOAST + LOADING ═══ -->
<div class="tw" id="tw"></div>
<div class="loading" id="ld"><div class="spin"></div></div>

<script>

// MONETAG REKLAMA
// ═══════════════════════════════════════════════════════════════
const MONETAG_ZONE = "11990967";

const AdManager = {
  async show() {
    const fn = window['show_' + MONETAG_ZONE];
    if (typeof fn !== 'function') {
      console.warn('Monetag SDK yuklanmagan');
      return false;
    }
    try {
      await fn('pop');
      return true;
    } catch (e) {
      console.warn('Reklama xatosi:', e);
      return false;
    }
  }
};

// ═══════════════════════════════════════════════════════════════
// ASOSIY APP
// ═══════════════════════════════════════════════════════════════
const App = {
  currentType: 'universal',
  currentData: null,
  initData: '',
  me: null,
  logoData: null,

  // ═══ ISHGA TUSHIRISH ═══
  async start() {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      document.documentElement.setAttribute('data-theme',
        tg.colorScheme === 'dark' ? 'dark' : 'light');
    }
    this.initData = tg?.initData || '';

    if (!this.initData) {
      this.showError('⚠️', 'Telegram orqali oching',
        'Bu sahifa faqat Telegram bot orqali ishlaydi.<br><br>' +
        'Botga qaytib <b>🧩 QR yaratish</b> tugmasini bosing.');
      return;
    }

    this.renderTypes();
    this.bindNav();
    this.bindForm();
    this.bindProfile();
    this.bindRef();
    this.bindAds();
    this.loadProfile();

    try {
      this.me = await this.api('/api/me', 'POST');

      if (this.me.need_sub) {
        this.showError('🔒', 'Obuna kerak',
          'Botdan foydalanish uchun kanalga obuna bo\'ling.<br><br>' +
          'Telegram botga qaytib <b>✅ Obunani tekshirish</b> tugmasini bosing.');
        return;
      }

      this.updateStats();
      await this.loadHistory();
      await this.loadRefs();
    } catch (e) {
      console.warn('API xato:', e.message);
      if (e.message.includes('initData') || e.message.includes('Imzo')) {
        this.showError('⚠️', 'Telegram orqali oching',
          'Botga qaytib <b>🧩 QR yaratish</b> tugmasini bosing.');
      } else {
        this.toast('Xato: ' + e.message, 'error');
      }
    }
  },

  // ═══ XATO SAHIFASI ═══
  showError(icon, title, text) {
    document.getElementById('mainC').innerHTML =
      '<div class="ep">' +
        '<div class="ico">' + icon + '</div>' +
        '<h2>' + title + '</h2>' +
        '<p>' + text + '</p>' +
      '</div>';
    document.querySelector('.nav').style.display = 'none';
  },

  // ═══ API CHAQIRUV ═══
  async api(path, method = 'GET', body = null) {
    const opts = {
      method: method,
      headers: {
        'X-Telegram-Init-Data': this.initData,
        'Content-Type': 'application/json'
      }
    };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    if (!r.ok) {
      const e = await r.json().catch(() => ({ detail: 'Xatolik' }));
      throw new Error(e.detail || 'Xatolik');
    }
    return r.json();
  },

  // ═══ STATISTIKA YANGILASH ═══
  updateStats() {
    if (!this.me) return;
    document.getElementById('s1').textContent = this.me.qr_count || 0;
    document.getElementById('s2').textContent = this.me.ad_count || 0;
    document.getElementById('s3').textContent = this.me.unlock_count || 0;
    document.getElementById('s4').textContent = this.me.referrals || 0;
    document.getElementById('fc2').textContent = (this.me.free_qr || 1) + ' ta';
    document.getElementById('uc').textContent = (this.me.unlock_count || 0) + ' ta';
    document.getElementById('at').textContent = this.me.ad_count || 0;
    document.getElementById('ab').textContent = '+' + (this.me.ad_count || 0);
  },

  // ═══ PROFIL ═══
  loadProfile() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user || {};
    const f = (u.first_name || 'F').charAt(0).toUpperCase();
    document.getElementById('av').textContent = f;
    document.getElementById('pav').textContent = f;
    document.getElementById('pn').textContent =
      ((u.first_name || '') + ' ' + (u.last_name || '')).trim() || 'Foydalanuvchi';
    document.getElementById('pu').textContent =
      u.username ? '@' + u.username : 'Telegram';
  },

  // ═══ QR TURLARI (20+) ═══
  types: [
    { id:'universal', i:'✨', l:'Universal', f:[
      {k:'text', l:'Matn / URL', t:'textarea', p:'Istalgan matn yoki havola'}]},
    { id:'url', i:'🔗', l:'URL', f:[
      {k:'url', l:'Havola', t:'url', p:'https://example.com'}]},
    { id:'text', i:'📝', l:'Matn', f:[
      {k:'text', l:'Matn', t:'textarea', p:'Salom dunyo!'}]},
    { id:'wifi', i:'📶', l:'Wi-Fi', f:[
      {k:'ssid', l:'Tarmoq nomi', t:'text'},
      {k:'pass', l:'Parol', t:'text'},
      {k:'sec', l:'Xavfsizlik', t:'select', o:['WPA','WEP','nopass']}]},
    { id:'vcard', i:'👤', l:'Kontakt', f:[
      {k:'first', l:'Ism', t:'text'},
      {k:'last', l:'Familiya', t:'text'},
      {k:'phone', l:'Telefon', t:'tel'},
      {k:'email', l:'Email', t:'email'}]},
    { id:'phone', i:'📞', l:'Telefon', f:[
      {k:'phone', l:'Raqam', t:'tel', p:'+998901234567'}]},
    { id:'sms', i:'💬', l:'SMS', f:[
      {k:'phone', l:'Telefon', t:'tel'},
      {k:'msg', l:'Xabar', t:'textarea'}]},
    { id:'email', i:'✉️', l:'Email', f:[
      {k:'to', l:'Kimga', t:'email'},
      {k:'subject', l:'Mavzu', t:'text'}]},
    { id:'tg', i:'✈️', l:'Telegram', f:[
      {k:'username', l:'Username', t:'text', p:'durov'}]},
    { id:'instagram', i:'📸', l:'Instagram', f:[
      {k:'username', l:'Username', t:'text'}]},
    { id:'youtube', i:'▶️', l:'YouTube', f:[
      {k:'url', l:'URL', t:'url'}]},
    { id:'tiktok', i:'🎵', l:'TikTok', f:[
      {k:'username', l:'Username', t:'text'}]},
    { id:'geo', i:'📍', l:'Geo', f:[
      {k:'lat', l:'Kenglik', t:'text', p:'41.311081'},
      {k:'lng', l:'Uzunlik', t:'text', p:'69.240562'}]},
    { id:'event', i:'📅', l:'Tadbir', f:[
      {k:'title', l:'Nomi', t:'text'},
      {k:'start', l:'Boshlanish', t:'text', p:'2025-12-31 18:00'}]},
    { id:'video', i:'🎬', l:'Video', f:[
      {k:'url', l:'Video URL (MP4/YouTube)', t:'url'}]},
    { id:'audio', i:'🎧', l:'Audio', f:[
      {k:'url', l:'Audio URL (MP3)', t:'url'}]},
    { id:'pdf', i:'📄', l:'PDF', f:[
      {k:'url', l:'PDF URL', t:'url'}]},
    { id:'image', i:'🖼️', l:'Rasm', f:[
      {k:'url', l:'Rasm URL', t:'url'}]},
    { id:'app', i:'📱', l:'Ilova', f:[
      {k:'name', l:'Ilova nomi', t:'text'},
      {k:'url', l:'Yuklab olish URL', t:'url'}]},
    { id:'custom', i:'⚙️', l:'Maxsus', f:[
      {k:'raw', l:'Format', t:'textarea', p:'Istalgan format'}]},
  ],

  // ═══ TURLARNI RENDER QILISH ═══
  renderTypes() {
    const grid = document.getElementById('tg');
    grid.innerHTML = this.types.map(t =>
      '<button class="tc" data-t="' + t.id + '">' +
        '<span class="ti">' + t.i + '</span>' +
        '<span class="tl">' + t.l + '</span>' +
      '</button>'
    ).join('');
    document.querySelectorAll('.tc').forEach(b => {
      b.onclick = () => this.openCreate(b.dataset.t);
    });
  },

  // ═══ YARATISH SAHIFASINI OCHISH ═══
  openCreate(id) {
    const t = this.types.find(x => x.id === id);
    if (!t) return;
    this.currentType = id;
    document.getElementById('ct').textContent = t.i + ' ' + t.l;

    const fields = document.getElementById('df');
    fields.innerHTML = t.f.map(f => {
      let el;
      if (f.t === 'textarea') {
        el = '<textarea class="textarea" id="f_' + f.k + '" placeholder="' +
             (f.p || '') + '"></textarea>';
      } else if (f.t === 'select') {
        el = '<select class="select" id="f_' + f.k + '">' +
             f.o.map(o => '<option>' + o + '</option>').join('') +
             '</select>';
      } else {
        el = '<input class="input" type="' + f.t + '" id="f_' + f.k +
             '" placeholder="' + (f.p || '') + '">';
      }
      return '<div class="field"><label>' + f.l + '</label>' + el + '</div>';
    }).join('');

    document.getElementById('qr').style.display = 'none';
    this.go('create');
  },

  // ═══ QR MA'LUMOTINI YIG'ISH ═══
  buildPayload() {
    const v = id => (document.getElementById('f_' + id)?.value || '').trim();
    const enc = encodeURIComponent;

    const map = {
      universal: () => v('text'),
      text: () => v('text'),
      url: () => v('url'),
      wifi: () => 'WIFI:T:' + (v('sec') || 'WPA') + ';S:' + v('ssid') +
                  ';P:' + v('pass') + ';;',
      vcard: () => [
        'BEGIN:VCARD',
        'VERSION:3.0',
        'N:' + v('last') + ';' + v('first') + ';;;',
        ('FN:' + v('first') + ' ' + v('last')).trim(),
        v('phone') ? 'TEL:' + v('phone') : '',
        v('email') ? 'EMAIL:' + v('email') : '',
        'END:VCARD'
      ].filter(Boolean).join('\n'),
      phone: () => 'tel:' + v('phone'),
      sms: () => 'SMSTO:' + v('phone') + ':' + v('msg'),
      email: () => 'mailto:' + v('to') + '?subject=' + enc(v('subject')),
      tg: () => 'https://t.me/' + v('username').replace('@', ''),
      instagram: () => 'https://instagram.com/' + v('username').replace('@', ''),
      youtube: () => v('url'),
      tiktok: () => 'https://tiktok.com/@' + v('username').replace('@', ''),
      geo: () => 'geo:' + v('lat') + ',' + v('lng'),
      event: () => [
        'BEGIN:VEVENT',
        'SUMMARY:' + v('title'),
        'DTSTART:' + v('start').replace(/[-: ]/g, ''),
        'END:VEVENT'
      ].join('\n'),
      video: () => v('url'),
      audio: () => v('url'),
      pdf: () => v('url'),
      image: () => v('url'),
      app: () => 'APP:' + v('name') + '|URL:' + v('url'),
      custom: () => v('raw'),
    };

    return (map[this.currentType] || (() => ''))();
  },

  // ═══ QR KOD YARATISH ═══
  async generate() {
    const data = this.buildPayload();
    if (!data) return this.toast('Ma\'lumot kiriting', 'error');
    if (typeof QRCode === 'undefined') {
      return this.toast('QR kutubxona yuklanmagan', 'error');
    }

    const size = parseInt(document.getElementById('qs').value);
    const fill = document.getElementById('fc').value;
    const back = document.getElementById('bc').value;

    try {
      this.load(true);
      const container = document.getElementById('qc');
      container.innerHTML = '';

      // Chiroyli ramka
      const wrapper = document.createElement('div');
      wrapper.style.cssText =
        'display:inline-block;padding:24px;' +
        'background:linear-gradient(135deg,' + fill + '15,' + fill + '25);' +
        'border-radius:24px;' +
        'box-shadow:0 15px 40px ' + fill + '40;' +
        'border:1px solid ' + fill + '30;';
      container.appendChild(wrapper);

      // QR div
      const qrDiv = document.createElement('div');
      qrDiv.style.cssText =
        'padding:14px;background:' + back + ';' +
        'border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,.1);';
      wrapper.appendChild(qrDiv);

      // QR yaratish
      new QRCode(qrDiv, {
        text: data,
        width: size,
        height: size,
        colorDark: fill,
        colorLight: back,
        correctLevel: QRCode.CorrectLevel.H
      });

      // Logo qo'yish
      if (this.logoData) {
        setTimeout(() => {
          const canvas = qrDiv.querySelector('canvas');
          if (!canvas) return;
          const ctx = canvas.getContext('2d');
          const img = new Image();
          img.onload = () => {
            const s = canvas.width;
            const ls = s * 0.22;
            const p = s * 0.015;
            const x = (s - ls) / 2;
            const y = (s - ls) / 2;

            // Oq fon
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(x - p, y - p, ls + p * 2, ls + p * 2);

            // Logo
            ctx.drawImage(img, x, y, ls, ls);
          };
          img.src = this.logoData;
        }, 150);
      }

      this.currentData = data;
      document.getElementById('qr').style.display = 'block';
      document.getElementById('qr').scrollIntoView({ behavior: 'smooth' });
      this.toast('QR kod yaratildi ✅', 'success');
    } catch (e) {
      this.toast('Xato: ' + e.message, 'error');
    } finally {
      this.load(false);
    }
  },

  // ═══ YUKLAB OLISH ═══
  download() {
    const canvas = document.querySelector('#qc canvas');
    if (!canvas) return this.toast('QR kod yo\'q', 'error');

    // Yangi canvas — faqat QR (ramkasiz)
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'qrmaster-' + Date.now() + '.png';
    a.click();
    this.toast('Yuklab olindi ✅', 'success');
  },

  // ═══ SAQLASH ═══
  async save() {
    if (!this.currentData) return this.toast('QR kod yo\'q', 'error');

    try {
      this.load(true);
      const res = await this.api('/api/qr/save', 'POST', {
        qr_type: this.currentType,
        name: this.types.find(t => t.id === this.currentType)?.l || 'QR',
        data: this.currentData
      });

      this.toast('✅ Saqlandi! Botga xabar yuborildi', 'success');

      if (this.me) {
        this.me.qr_count = res.total;
        this.updateStats();
      }
      await this.loadHistory();

      // Reklama kerakmi?
      if (res.show_ad) {
        this.load(false);
        const ok = confirm(
          '🎬 Bepul limit tugadi!\n\n' +
          'Reklama ko\'rib +3 QR unlock olasizmi?'
        );
        if (ok) {
          this.load(true);
          const watched = await AdManager.show();
          this.load(false);
          if (watched) {
            const ar = await this.api('/api/qr/ad', 'POST', {});
            this.me.unlock_count = ar.unlock;
            this.me.ad_count = ar.ad_count;
            this.updateStats();
            this.toast('🎁 +3 QR unlock!', 'success');
          } else {
            this.toast('Reklama ko\'rilmadi', 'error');
          }
        }
      }
    } catch (e) {
      this.toast(e.message, 'error');
    } finally {
      this.load(false);
    }
  },

  // ═══ TARIXNI YUKLASH ═══
  async loadHistory() {
    try {
      const list = await this.api('/api/qr/list');
      this.renderHistory(list);
      this.renderRecent(list);
    } catch (e) {
      console.warn('Tarix yuklanmadi:', e);
    }
  },

  renderRecent(list) {
    const el = document.getElementById('rl');
    const r = list.slice(0, 3);

    if (!r.length) {
      el.innerHTML = '<div class="empty"><span class="ico">🎯</span>Hozircha bo\'sh</div>';
      return;
    }

    el.innerHTML = r.map(h =>
      '<div class="hi">' +
        '<div class="hi-i">' +
          '<h4>' + h.name + '</h4>' +
          '<p>' + h.qr_type + ' · ' +
              new Date(h.created_at).toLocaleString('uz') + '</p>' +
        '</div>' +
      '</div>'
    ).join('');
  },

  renderHistory(list) {
    const el = document.getElementById('hl');

    if (!list.length) {
      el.innerHTML = '<div class="empty"><span class="ico">🕐</span>Tarix bo\'sh</div>';
      return;
    }

    el.innerHTML = list.map(h =>
      '<div class="hi">' +
        '<div class="hi-i">' +
          '<h4>' + h.name + '</h4>' +
          '<p>' + h.qr_type + ' · ' +
              new Date(h.created_at).toLocaleString('uz') + '</p>' +
        '</div>' +
        '<button class="ic" onclick="App.delQr(' + h.id + ')">🗑</button>' +
      '</div>'
    ).join('');
  },

  // ═══ QR O'CHIRISH ═══
  async delQr(id) {
    if (!confirm('O\'chirilsinmi?')) return;
    try {
      await this.api('/api/qr/' + id, 'DELETE');
      this.toast('O\'chirildi', 'info');
      await this.loadHistory();
      if (this.me) {
        this.me.qr_count = Math.max(0, this.me.qr_count - 1);
        this.updateStats();
      }
    } catch (e) {
      this.toast(e.message, 'error');
    }
  },

  // ═══ REFERALLARNI YUKLASH ═══
  async loadRefs() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (!u) return;

    const bot = this.me?.bot_username || 'BotUsername';
    const link = 'https://t.me/' + bot + '?start=ref_' + u.id;
    document.getElementById('rlink').textContent = link;

    try {
      const data = await this.api('/api/ref/list');
      document.getElementById('rc').textContent = data.total || 0;

      const el = document.getElementById('rlist');
      if (!data.refs || !data.refs.length) {
        el.innerHTML = '<div class="empty"><span class="ico">👥</span>Referal yo\'q</div>';
        return;
      }

      el.innerHTML = data.refs.map(r =>
        '<div class="hi">' +
          '<div class="hi-i">' +
            '<h4>' + (r.first_name || 'Foydalanuvchi') + '</h4>' +
            '<p>@' + (r.username || '—') + ' · ' +
                (r.created_at || '').slice(0, 10) + '</p>' +
          '</div>' +
        '</div>'
      ).join('');
    } catch (e) {
      console.warn('Referallar yuklanmadi:', e);
    }
  },

  // ═══ REFERAL BIND ═══
  bindRef() {
    document.getElementById('cr').onclick = async () => {
      const link = document.getElementById('rlink').textContent;
      try {
        await navigator.clipboard.writeText(link);
        this.toast('Nusxalandi 📋', 'success');
      } catch (e) {
        this.toast('Nusxalab bo\'lmadi', 'error');
      }
    };

    document.getElementById('sr').onclick = () => {
      const link = document.getElementById('rlink').textContent;
      window.open(
        'https://t.me/share/url?url=' + encodeURIComponent(link) +
        '&text=' + encodeURIComponent('QR Master — zo\'r bot!'),
        '_blank'
      );
    };
  },

  // ═══ REKLAMA BIND ═══
  bindAds() {
    document.getElementById('wab').onclick = async () => {
      this.load(true);
      const ok = await AdManager.show();
      this.load(false);

      if (ok) {
        try {
          const r = await this.api('/api/qr/ad', 'POST', {});
          this.me.unlock_count = r.unlock;
          this.me.ad_count = r.ad_count;
          this.updateStats();
          this.toast('🎁 +3 QR unlock!', 'success');
        } catch (e) {
          this.toast(e.message, 'error');
        }
      } else {
        this.toast('Reklama ko\'rilmadi. Qayta urinib ko\'ring', 'error');
      }
    };

    document.getElementById('ib').onclick = () => this.go('ref');
  },

  // ═══ PROFIL BIND ═══
  bindProfile() {
    document.getElementById('tb').onclick = () => {
      const cur = document.documentElement.getAttribute('data-theme');
      document.documentElement.setAttribute('data-theme',
        cur === 'dark' ? 'light' : 'dark');
    };

    document.getElementById('rl2').onclick = async () => {
      this.load(true);
      try {
        this.me = await this.api('/api/me', 'POST');
        this.updateStats();
        await this.loadHistory();
        await this.loadRefs();
        this.toast('Yangilandi ✅', 'success');
      } catch (e) {
        this.toast(e.message, 'error');
      }
      this.load(false);
    };
  },

  // ═══ FORMA BIND ═══
  bindForm() {
    document.getElementById('gb').onclick = () => this.generate();
    document.getElementById('bb').onclick = () => this.go('home');
    document.getElementById('dlb').onclick = () => this.download();
    document.getElementById('sb').onclick = () => this.save();

    // Logo yuklash
    document.getElementById('lf').onchange = (e) => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 500 * 1024) {
        return this.toast('Fayl 500 KB dan oshmasin', 'error');
      }
      const reader = new FileReader();
      reader.onload = (ev) => {
        this.logoData = ev.target.result;
        document.getElementById('lp').src = ev.target.result;
        document.getElementById('cl').style.display = 'block';
      };
      reader.readAsDataURL(f);
    };

    document.getElementById('cl').onclick = () => {
      this.logoData = null;
      document.getElementById('lp').src =
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='50' height='50'%3E%3Ctext x='50%25' y='55%25' text-anchor='middle' font-size='24' fill='%2364748b'%3E%2B%3C/text%3E%3C/svg%3E";
      document.getElementById('cl').style.display = 'none';
    };
  },

  // ═══ NAVIGATSIYA BIND ═══
  bindNav() {
    document.querySelectorAll('.nb').forEach(b => {
      b.onclick = () => this.go(b.dataset.page);
    });
  },

  // ═══ SAHIFA ALMASHTIRISH ═══
  go(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById('p-' + name);
    if (page) page.classList.add('active');

    document.querySelectorAll('.nb').forEach(b => {
      b.classList.toggle('active', b.dataset.page === name);
    });

    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  // ═══ TOAST ═══
  toast(msg, type) {
    type = type || 'info';
    const w = document.getElementById('tw');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    w.appendChild(el);
    setTimeout(() => el.remove(), 3500);
  },

  // ═══ LOADING ═══
  load(on) {
    document.getElementById('ld').classList.toggle('on', on);
  },
};

// ═══ ISHGA TUSHIRISH ═══
window.addEventListener('DOMContentLoaded', () => App.start());
</script>
</body>
</html>
'''

# ═══════════════════════════════════════════════════════════════
# FLASK API ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/", methods=["GET", "HEAD"])
def index():
    return Response(HTML_PAGE, mimetype="text/html")


@app.route("/health", methods=["GET", "HEAD"])
def health():
    return jsonify({"ok": True, "time": datetime.utcnow().isoformat()})


@app.route("/api/me", methods=["POST", "GET", "OPTIONS"])
def api_me():
    """Foydalanuvchi ma'lumotlari."""
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    init_data = request.headers.get("X-Telegram-Init-Data", "")
    try:
        tg = validate_init_data(init_data)
    except ValueError as e:
        print(f"❌ Auth xato: {e}")
        return jsonify({"detail": str(e)}), 401

    upsert_user(tg)
    u = get_user(tg["id"])
    if not u:
        return jsonify({"detail": "Foydalanuvchi topilmadi"}), 404

    return jsonify({
        "id": u["telegram_id"],
        "username": u["username"],
        "first_name": u["first_name"],
        "qr_count": u["qr_count"],
        "ad_count": u["ad_count"],
        "unlock_count": u.get("unlock_count", 0),
        "is_admin": is_admin(tg["id"]),
        "referrals": count_referrals(tg["id"]),
        "bot_username": BOT_USERNAME,
        "free_qr": get_setting("free_qr_count", "1"),
        "qr_per_ad": get_setting("qr_per_ad", "3"),
        "need_sub": not check_subscription(tg["id"]),
    })


@app.route("/api/qr/save", methods=["POST", "OPTIONS"])
@auth_required
def api_qr_save(tg):
    """QR saqlash + botga xabar."""
    body = request.get_json(silent=True) or {}
    data = (body.get("data") or "").strip()

    if not data:
        return jsonify({"detail": "Ma'lumot bo'sh"}), 400
    if len(data) > 5000:
        return jsonify({"detail": "Ma'lumot juda uzun"}), 400

    upsert_user(tg)
    qr_type = body.get("qr_type") or "universal"
    name = (body.get("name") or "QR")[:255]

    add_qr(tg["id"], qr_type, name, data)

    u = get_user(tg["id"])
    total = u["qr_count"]
    free = get_int_setting("free_qr_count", 1)
    unlock = u.get("unlock_count", 0)
    per_ad = get_int_setting("qr_per_ad", 3)
    limit = free + unlock

    # Reklama kerakmi?
    show_ad = False
    if per_ad > 0 and total > limit:
        if (total - limit) % per_ad == 0:
            show_ad = True

    # Botga xabar
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

        text = (
            f"✅ <b>Yangi QR kod saqlandi!</b>\n\n"
            f"📌 <b>{name}</b>\n"
            f"🔧 Turi: <code>{qr_type}</code>\n"
            f"📊 Jami: <b>{total}</b> ta\n"
        )

        if show_ad:
            text += f"\n🎬 <b>Bepul limit tugadi!</b>\nReklama ko'rib +3 QR unlock oling."

        bot.send_message(tg["id"], text, reply_markup=kb)
    except Exception as e:
        print(f"⚠️ Bot xabar yuborilmadi: {e}")

    return jsonify({
        "ok": True,
        "total": total,
        "limit": limit,
        "unlock": unlock,
        "show_ad": show_ad,
    })


@app.route("/api/qr/ad", methods=["POST", "OPTIONS"])
@auth_required
def api_qr_ad(tg):
    """Reklama ko'rilgandan keyin unlock berish."""
    log_ad_event(tg["id"], "rewarded", "completed")

    bonus = get_int_setting("qr_per_ad", 3)
    q_exec(
        "UPDATE users SET unlock_count = unlock_count + ? WHERE telegram_id=?",
        (bonus, tg["id"])
    )

    u = get_user(tg["id"])
    return jsonify({
        "unlock": u.get("unlock_count", 0),
        "ad_count": u["ad_count"],
    })


@app.route("/api/qr/list", methods=["GET", "OPTIONS"])
@auth_required
def api_qr_list(tg):
    """Foydalanuvchi QR ro'yxati."""
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
    """QR o'chirish."""
    if delete_qr(qid, tg["id"]):
        return jsonify({"ok": True})
    return jsonify({"detail": "Topilmadi"}), 404


@app.route("/api/ref/list", methods=["GET", "OPTIONS"])
@auth_required
def api_ref_list(tg):
    """Referallar ro'yxati."""
    refs = get_referrals(tg["id"], 50, 0)
    return jsonify({
        "total": count_referrals(tg["id"]),
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
# BOT ISHGA TUSHIRISH
# ═══════════════════════════════════════════════════════════════
def run_bot():
    """Botni alohida thread'da ishga tushirish."""
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


# ═══════════════════════════════════════════════════════════════
# ASOSIY ISHGA TUSHIRISH
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Botni alohida thread'da
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Botning tayyor bo'lishini kutish
    time.sleep(3)

    # Flask serverni ishga tushirish
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
