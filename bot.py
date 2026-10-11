# -*- coding: utf-8 -*-
"""
QR MASTER — Yaxshilangan versiya\nLimit = free_qr + unlock_count | Reklama limitisiz | unlock ishlaydi
Ishga tushirish: python bot.py
"""
import os, sys, hmac, hashlib, json, threading, time, sqlite3, io
from datetime import datetime
from functools import wraps
from urllib.parse import parse_qsl


# ═══════════════════════════════════════════════════════════════
# KUTUBXONALARNI O'RNATISH
# ═══════════════════════════════════════════════════════════════
def _install():
    import importlib, subprocess
    needed = {
        "telebot": "pyTelegramBotAPI",
        "flask": "Flask",
        "flask_cors": "Flask-Cors",
        "qrcode": "qrcode[pil]",
        "PIL": "Pillow",
    }
    missing = []
    for mod, pkg in needed.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"📦 O'rnatilmoqda: {', '.join(missing)}")
        for pkg in missing:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        print("✅ O'rnatildi! Qayta ishga tushirilmoqda...")
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    print("✅ Barcha kutubxonalar tayyor")


_install()

from flask import Flask, request, jsonify, Response
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
# SOZLAMALAR
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
WEBAPP_URL   = os.getenv("WEBAPP_URL", "http://localhost:8000")
ADMIN_IDS    = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
MONETAG_ZONE = os.getenv("MONETAG_ZONE", "11990967")
PORT         = int(os.getenv("PORT", 8000))
DB_FILE      = os.getenv("DB_FILE", "qr_master.db")
BOT_USERNAME = ""

os.makedirs(os.path.dirname(DB_FILE) or ".", exist_ok=True)

print("=" * 60)
print("🚀 QR MASTER")
print("=" * 60)
print(f"📁 DB:       {DB_FILE}")
print(f"🌐 URL:      {WEBAPP_URL}")
print(f"👤 Admin:    {ADMIN_IDS}")
print(f"💰 Monetag:  {MONETAG_ZONE}")
print("=" * 60)


# ═══════════════════════════════════════════════════════════════
# DATABASE SCHEMA
# ═══════════════════════════════════════════════════════════════
def init_database():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Foydalanuvchilar
    c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            telegram_id   INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            last_name     TEXT,
            language      TEXT DEFAULT 'uz',
            status        TEXT DEFAULT 'active',
            qr_count      INTEGER DEFAULT 0,
            ad_count      INTEGER DEFAULT 0,
            unlock_count  INTEGER DEFAULT 0,
            created_at    TEXT,
            last_active   TEXT
        )
    """)

    # QR kodlar tarixi
    c.execute("""
        CREATE TABLE IF NOT EXISTS qr_history(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            qr_type       TEXT,
            name          TEXT,
            qr_data       TEXT,
            payload_hash  TEXT,
            created_at    TEXT
        )
    """)

    # Majburiy obuna kanallari
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id       TEXT,
            name          TEXT,
            username      TEXT,
            invite_link   TEXT,
            check_mode    TEXT DEFAULT 'member',
            is_active     INTEGER DEFAULT 1
        )
    """)

    # Sozlamalar (kalit-qiymat)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            key           TEXT PRIMARY KEY,
            value         TEXT
        )
    """)

    # Referallar
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id   INTEGER,
            referred_id   INTEGER UNIQUE,
            created_at    TEXT
        )
    """)

    # Yordam xabarlari
    c.execute("""
        CREATE TABLE IF NOT EXISTS support_messages(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            message       TEXT,
            admin_reply   TEXT,
            status        TEXT DEFAULT 'open',
            created_at    TEXT
        )
    """)

    # Reklama hodisalari
    c.execute("""
        CREATE TABLE IF NOT EXISTS ad_events(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            format        TEXT,
            event_type    TEXT,
            created_at    TEXT
        )
    """)

    # Adminlar (qo'shimcha)
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            telegram_id   INTEGER PRIMARY KEY,
            added_by      INTEGER,
            created_at    TEXT
        )
    """)

    # Kutilayotgan obunalar (yopiq kanallar)
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_subs(
            user_id       INTEGER,
            channel_id    INTEGER,
            requested_at  TEXT,
            PRIMARY KEY(user_id, channel_id)
        )
    """)

    # Indekslar
    c.execute("CREATE INDEX IF NOT EXISTS idx_qr_user ON qr_history(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ref_referrer ON referrals(referrer_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ad_created ON ad_events(created_at)")

    # Standart sozlamalar
    defaults = {
        "force_sub_enabled": "0",   # 0=o'chiq, 1=yoqiq
        "referral_enabled":  "1",
        "monetag_enabled":   "1",
        "free_qr_count":     "5",   # Boshida N ta bepul QR
        "ad_bonus_qr":       "3",   # Har reklama uchun +N unlock (frontend bilan mos)
        "invite_bonus_qr":   "10",  # Har referal uchun bonus
        "qr_per_ad":         "3",   # eski kalit (moslik uchun, ad_bonus_qr ishlatiladi)
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
    """SELECT — ro'yxat yoki bitta natija qaytaradi."""
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


def qx(sql, args=()):
    """INSERT/UPDATE/DELETE — lastrowid qaytaradi."""
    conn = sqlite3.connect(DB_FILE)
    try:
        cursor = conn.execute(sql, args)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# SOZLAMALAR (settings jadvali)
# ═══════════════════════════════════════════════════════════════

def get_setting(key, default=""):
    """Sozlama qiymatini olish."""
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


def set_setting(key, value):
    """Sozlama qiymatini o'rnatish."""
    qx("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, str(value)))


def get_int_setting(key, default=0):
    """Raqamli sozlama."""
    try:
        return int(get_setting(key, str(default)))
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════
# ADMINLAR
# ═══════════════════════════════════════════════════════════════

def is_admin(uid):
    """Foydalanuvchi admin ekanligini tekshirish."""
    if uid in ADMIN_IDS:
        return True
    return bool(q("SELECT 1 FROM admins WHERE telegram_id=?", (uid,), one=True))


def add_admin(uid, added_by=0):
    """Yangi admin qo'shish."""
    qx("INSERT OR IGNORE INTO admins(telegram_id, added_by, created_at) VALUES(?, ?, ?)",
       (uid, added_by, datetime.utcnow().isoformat()))


def remove_admin(uid):
    """Adminni o'chirish."""
    qx("DELETE FROM admins WHERE telegram_id=?", (uid,))


def get_all_admins():
    """Barcha adminlar ro'yxati."""
    extras = q("SELECT telegram_id FROM admins")
    return list(ADMIN_IDS) + [r["telegram_id"] for r in extras]


# ═══════════════════════════════════════════════════════════════
# FOYDALANUVCHILAR
# ═══════════════════════════════════════════════════════════════

def get_user(uid):
    """Foydalanuvchini olish."""
    return q("SELECT * FROM users WHERE telegram_id=?", (uid,), one=True)


def upsert_user(tg_data):
    """Foydalanuvchini yaratish yoki yangilash. Yangi bo'lsa True."""
    uid = tg_data["id"]
    now = datetime.utcnow().isoformat()
    existing = q("SELECT 1 FROM users WHERE telegram_id=?", (uid,), one=True)
    if not existing:
        qx("""INSERT INTO users(telegram_id, username, first_name, last_name,
            language, created_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
           (uid, tg_data.get("username"), tg_data.get("first_name"),
            tg_data.get("last_name"), tg_data.get("language_code", "uz"), now, now))
        return True
    qx("""UPDATE users SET username=?, first_name=?, last_name=?, last_active=?
        WHERE telegram_id=?""",
       (tg_data.get("username"), tg_data.get("first_name"),
        tg_data.get("last_name"), now, uid))
    return False


def count_users():
    """Jami foydalanuvchilar soni."""
    r = q("SELECT COUNT(*) AS c FROM users", one=True)
    return r["c"] if r else 0


def count_users_today():
    """Bugun ro'yxatdan o'tganlar."""
    r = q("SELECT COUNT(*) AS c FROM users WHERE date(created_at)=date('now')", one=True)
    return r["c"] if r else 0


def get_users_paginated(offset=0, limit=10):
    """Foydalanuvchilar ro'yxati (sahifalash)."""
    return q("SELECT * FROM users ORDER BY last_active DESC LIMIT ? OFFSET ?",
             (limit, offset))


def update_user_status(uid, status):
    """Foydalanuvchi statusini o'zgartirish."""
    qx("UPDATE users SET status=? WHERE telegram_id=?", (status, uid))


# ═══════════════════════════════════════════════════════════════
# QR KODLAR
# ═══════════════════════════════════════════════════════════════

def add_qr(uid, qr_type, name, qr_data):
    """Yangi QR kodni bazaga qo'shish."""
    qx("""INSERT INTO qr_history(user_id, qr_type, name, qr_data, payload_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
       (uid, qr_type, name, qr_data,
        hashlib.sha256(qr_data.encode()).hexdigest(),
        datetime.utcnow().isoformat()))
    qx("UPDATE users SET qr_count = qr_count + 1 WHERE telegram_id=?", (uid,))


def get_qrs(uid, limit=50, offset=0):
    """Foydalanuvchining QR kodlari."""
    return q("""SELECT id, qr_type, name, qr_data, created_at
        FROM qr_history WHERE user_id=?
        ORDER BY id DESC LIMIT ? OFFSET ?""", (uid, limit, offset))


def get_qr(qr_id, uid):
    """Bitta QR kodni olish."""
    return q("SELECT * FROM qr_history WHERE id=? AND user_id=?",
             (qr_id, uid), one=True)


def count_qrs(uid):
    """Foydalanuvchi QR kodlari soni."""
    r = q("SELECT COUNT(*) AS c FROM qr_history WHERE user_id=?", (uid,), one=True)
    return r["c"] if r else 0


def count_all_qrs():
    """Umumiy QR kodlar soni."""
    r = q("SELECT COUNT(*) AS c FROM qr_history", one=True)
    return r["c"] if r else 0


def delete_qr(qr_id, uid):
    """QR kodni o'chirish."""
    existing = q("SELECT 1 FROM qr_history WHERE id=? AND user_id=?",
                 (qr_id, uid), one=True)
    if existing:
        qx("DELETE FROM qr_history WHERE id=?", (qr_id,))
        # SQLite da MAX() UPDATE ichida ishlamaydi — CASE ishlatamiz
        qx("""UPDATE users SET qr_count = CASE
                WHEN qr_count > 0 THEN qr_count - 1 ELSE 0 END
            WHERE telegram_id=?""", (uid,))
        return True
    return False



def get_qr_limit_info(uid):
    """
    Foydalanuvchi QR limiti haqida ma'lumot.
    Returns: dict free, unlock, used, allowed, remaining, can_create
    """
    u = get_user(uid)
    free = get_int_setting("free_qr_count", 5)
    unlock = (u.get("unlock_count") or 0) if u else 0
    used = (u.get("qr_count") or 0) if u else 0
    allowed = free + unlock
    remaining = max(0, allowed - used)
    return {
        "free": free,
        "unlock": unlock,
        "used": used,
        "allowed": allowed,
        "remaining": remaining,
        "can_create": used < allowed,
    }


# ═══════════════════════════════════════════════════════════════
# REFERALLAR
# ═══════════════════════════════════════════════════════════════

def add_referral(referrer_id, referred_id):
    """Yangi referal qo'shish. True qaytaradi, agar qo'shilsa."""
    if referrer_id == referred_id:
        return False
    try:
        qx("""INSERT INTO referrals(referrer_id, referred_id, created_at)
            VALUES (?, ?, ?)""",
           (referrer_id, referred_id, datetime.utcnow().isoformat()))
        bonus = get_int_setting("invite_bonus_qr", 10)
        qx("UPDATE users SET unlock_count = unlock_count + ? WHERE telegram_id=?",
           (bonus, referrer_id))
        return True
    except sqlite3.IntegrityError:
        return False


def count_referrals(uid):
    """Referallar soni."""
    r = q("SELECT COUNT(*) AS c FROM referrals WHERE referrer_id=?", (uid,), one=True)
    return r["c"] if r else 0


def get_referrals(uid, limit=50, offset=0):
    """Referallar ro'yxati."""
    return q("""SELECT r.*, u.first_name, u.username
        FROM referrals r
        LEFT JOIN users u ON u.telegram_id = r.referred_id
        WHERE r.referrer_id=?
        ORDER BY r.id DESC LIMIT ? OFFSET ?""", (uid, limit, offset))


# ═══════════════════════════════════════════════════════════════
# MAJBURIY OBUNA KANALLARI
# ═══════════════════════════════════════════════════════════════

def get_channels():
    """Faol kanallar."""
    return q("SELECT * FROM channels WHERE is_active=1 ORDER BY id")


def get_all_channels():
    """Barcha kanallar (admin uchun)."""
    return q("SELECT * FROM channels ORDER BY id")


def get_channel(ch_id):
    """Bitta kanal."""
    return q("SELECT * FROM channels WHERE id=?", (ch_id,), one=True)


def add_channel(chat_id, name, username=None, invite_link=None, check_mode="member"):
    """Yangi kanal qo'shish."""
    return qx("""INSERT INTO channels(chat_id, name, username, invite_link, check_mode)
        VALUES (?, ?, ?, ?, ?)""",
        (str(chat_id), name, username, invite_link, check_mode))


def delete_channel(ch_id):
    """Kanalni o'chirish."""
    qx("DELETE FROM channels WHERE id=?", (ch_id,))


def update_channel_mode(ch_id, mode):
    """Kanal rejimini o'zgartirish."""
    qx("UPDATE channels SET check_mode=? WHERE id=?", (mode, ch_id))


# ═══════════════════════════════════════════════════════════════
# PENDING SUBS (yopiq kanallar uchun)
# ═══════════════════════════════════════════════════════════════

def save_pending_sub(uid, ch_id):
    """So'rov yuborilganini qayd etish."""
    qx("""INSERT OR REPLACE INTO pending_subs(user_id, channel_id, requested_at)
        VALUES (?, ?, ?)""", (uid, ch_id, datetime.utcnow().isoformat()))


def has_pending_sub(uid, ch_id):
    """So'rov allaqachon yuborilganmi."""
    r = q("SELECT 1 FROM pending_subs WHERE user_id=? AND channel_id=?",
          (uid, ch_id), one=True)
    return bool(r)


# ═══════════════════════════════════════════════════════════════
# REKLAMA HODISALARI
# ═══════════════════════════════════════════════════════════════

def log_ad_event(uid, ad_format="rewarded", event_type="completed"):
    """Reklama hodisasini qayd etish."""
    qx("""INSERT INTO ad_events(user_id, format, event_type, created_at)
        VALUES (?, ?, ?, ?)""",
       (uid, ad_format, event_type, datetime.utcnow().isoformat()))
    if event_type == "completed":
        qx("UPDATE users SET ad_count = ad_count + 1 WHERE telegram_id=?", (uid,))


def count_ad_events(event_type="completed"):
    """Reklama hodisalari soni."""
    r = q("SELECT COUNT(*) AS c FROM ad_events WHERE event_type=?",
          (event_type,), one=True)
    return r["c"] if r else 0


# ═══════════════════════════════════════════════════════════════
# YORDAM XABARLARI
# ═══════════════════════════════════════════════════════════════

def save_support_message(uid, message):
    """Yordam xabarini saqlash."""
    return qx("""INSERT INTO support_messages(user_id, message, created_at)
        VALUES (?, ?, ?)""", (uid, message, datetime.utcnow().isoformat()))


def get_open_support_messages(limit=10):
    """Ochiq yordam xabarlari."""
    return q("""SELECT * FROM support_messages WHERE status='open'
        ORDER BY created_at DESC LIMIT ?""", (limit,))


def get_support_message(mid):
    """Bitta xabar."""
    return q("SELECT * FROM support_messages WHERE id=?", (mid,), one=True)


def reply_support_message(mid, reply):
    """Admin javobini saqlash."""
    qx("UPDATE support_messages SET admin_reply=?, status='answered' WHERE id=?",
       (reply, mid))


# ═══════════════════════════════════════════════════════════════
# QR RASM YARATISH (bot uchun)
# ═══════════════════════════════════════════════════════════════

def make_qr_png(data):
    """QR kodni PNG bytes qilib qaytarish (botda ko'rsatish uchun)."""
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


# ═══════════════════════════════════════════════════════════════
# STATISTIKA
# ═══════════════════════════════════════════════════════════════

def get_global_stats():
    """Umumiy statistika."""
    return {
        "users_total": count_users(),
        "users_today": count_users_today(),
        "qr_total":    count_all_qrs(),
        "ads_total":   count_ad_events("completed"),
    }


# ═══════════════════════════════════════════════════════════════
# 1-QISM TUGADI
# Keyingi: 2-QISM (Bot handlers + Admin panel)
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# TELEGRAM BOT YARATISH
# ═══════════════════════════════════════════════════════════════
if not BOT_TOKEN:
    print("❌ BOT_TOKEN bo'sh! Environment variable qo'shing")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
BC_STATE = {}  # broadcast vaqtinchalik holat {admin_id: text}


def setup_bot():
    """Bot menu button, username va commands ni sozlash."""
    global BOT_USERNAME
    try:
        me = bot.get_me()
        BOT_USERNAME = me.username
        print(f"✅ Bot: @{BOT_USERNAME}")

        try:
            bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                text="🚀 QR Master",
                web_app=WebAppInfo(url=WEBAPP_URL)
            ))
            print(f"✅ Menu button: {WEBAPP_URL}")
        except Exception as e:
            print(f"⚠️ Menu button: {e}")

        bot.set_my_commands([
            BotCommand("start", "🏠 Bosh menyu"),
            BotCommand("admin", "👑 Admin panel"),
            BotCommand("id", "🆔 Telegram ID"),
        ])
    except Exception as e:
        print(f"⚠️ Setup: {e}")


# ═══════════════════════════════════════════════════════════════
# MAJBURIY OBUNA TEKSHIRISH
# ═══════════════════════════════════════════════════════════════

def check_member_status(chat_id, user_id):
    """
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
    if is_admin(uid):
        return True
    if get_setting("force_sub_enabled") != "1":
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
        # st is None — bot admin emas
        if ch["check_mode"] == "request":
            if has_pending_sub(uid, ch["id"]):
                continue
            return False
    return True


def sub_prompt(chat_id, uid):
    """Obuna talab qiluvchi xabar."""
    channels = get_channels()
    if not channels:
        return

    text = "🔒 <b>Botdan foydalanish uchun obuna bo'ling:</b>\n\n"
    kb = InlineKeyboardMarkup()

    for i, ch in enumerate(channels, 1):
        st = check_member_status(ch["chat_id"], uid)
        if st is True:
            icon = "✅"
        elif ch["check_mode"] == "request" and has_pending_sub(uid, ch["id"]):
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
# REPLY KEYBOARD (oddiy matn tugmalar)
# ═══════════════════════════════════════════════════════════════

def main_menu():
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
# BUYRUQLAR
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
# QR YARATISH — INLINE WEBAPP TUGMA
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
        "QR <b>avtomatik saqlanadi</b>! ✅",
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
        f"🎁 Bepul limit: <b>{get_setting('free_qr_count')} ta</b>\n"
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
    total = count_qrs(uid)
    if total == 0:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🚀 QR yaratish",
               web_app=WebAppInfo(url=WEBAPP_URL)))
        bot.send_message(
            chat_id,
            "📜 Sizda hali QR kodlar yo'q.\n\n"
            "🧩 Mini App orqali yarating!",
            reply_markup=kb
        )
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
    total = count_referrals(uid)
    bonus = get_int_setting("invite_bonus_qr", 10)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📋 Havolani nusxalash", callback_data="copy_ref"))
    kb.add(InlineKeyboardButton(
        "📤 Ulashish",
        url=f"https://t.me/share/url?url={link}&text=QR Master"
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
        f"👥 Referallar: <b>{refs}</b>"
    )


# ═══════════════════════════════════════════════════════════════
# YORDAM XABARI
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
    mid = save_support_message(uid, message.text)
    bot.reply_to(message, "✅ Xabaringiz adminga yuborildi!")

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
                    save_pending_sub(uid, ch["id"])
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
        qr_id = int(data.split(":")[1])
        qr = get_qr(qr_id, uid)
        if qr:
            try:
                img = make_qr_png(qr["qr_data"])
                bot.send_photo(uid, InputFile(img, f"qr_{qr_id}.png"),
                    caption=f"📥 <b>{qr['name']}</b>\n\n<code>{qr['qr_data'][:100]}</code>")
            except Exception as e:
                bot.send_message(uid, f"❌ {e}")

    elif data.startswith("qr_del:"):
        qr_id = int(data.split(":")[1])
        if delete_qr(qr_id, uid):
            bot.delete_message(uid, call.message.message_id)
            show_user_qrs(uid, uid, 0)

    # ─── ADMIN ───
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
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙", callback_data="adm_back"))
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=kb)

    elif data.startswith("adm_users:"):
        offset = int(data.split(":")[1])
        total = count_users()
        users = get_users_paginated(offset, 10)
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
        text = BC_STATE.pop(uid, "")
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
        cur = get_setting("force_sub_enabled", "0")
        set_setting("force_sub_enabled", "0" if cur == "1" else "1")
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
        delete_channel(int(data.split(":")[1]))
        bot.answer_callback_query(call.id, "✅")
        show_subscription_menu(uid, call.message.message_id)

    elif data == "adm_admins":
        admins = get_all_admins()
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
        msgs = get_open_support_messages(10)
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
            f"📢 <b>Reklama / Limit sozlamalari</b>\n\n"
            f"🧩 Bepul QR: <b>{get_setting('free_qr_count')}</b>\n"
            f"🎬 Reklama bonusi: <b>+{get_setting('ad_bonus_qr', '3')}</b>\n"
            f"🎁 Referal bonus: <b>+{get_setting('invite_bonus_qr')}</b>\n\n"
            f"<i>Limit = bepul + unlock. Reklama limitisiz.</i>"
        )
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🧩 Bepul QR", callback_data="adm_set:free_qr_count"),
            InlineKeyboardButton("🎬 Ad bonus", callback_data="adm_set:ad_bonus_qr"),
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
    channels = get_all_channels()
    enabled = get_setting("force_sub_enabled") == "1"
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
    BC_STATE[message.from_user.id] = message.text
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
                    "❌ Format xato.\n\nYuboring:\n"
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
    try:
        val = int(message.text.strip())
        set_setting(key, str(val))
        bot.send_message(message.chat.id, f"✅ <b>{key}</b> = {val}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Faqat raqam")


def send_admin_reply(message, mid):
    if message.content_type != "text":
        bot.reply_to(message, "❌")
        return
    support = get_support_message(mid)
    if not support:
        return
    reply_support_message(mid, message.text)
    try:
        bot.send_message(support["user_id"], f"📬 <b>Admin javobi:</b>\n\n{message.text}")
        bot.send_message(message.chat.id, "✅ Yuborildi")
    except Exception:
        bot.send_message(message.chat.id, "❌ Yuborib bo'lmadi")


# ═══════════════════════════════════════════════════════════════
# JOIN REQUEST HANDLER (yopiq kanallar)
# ═══════════════════════════════════════════════════════════════

@bot.chat_join_request_handler(func=lambda r: True)
def on_join_request(req):
    uid = req.from_user.id
    # channels jadvalidagi id ni topish (pending_subs.channel_id = channels.id)
    ch = q("SELECT id FROM channels WHERE chat_id=? AND is_active=1",
           (str(req.chat.id),), one=True)
    if ch:
        save_pending_sub(uid, ch["id"])
    else:
        # fallback: chat_id ni saqlamaymiz, faqat adminlarga xabar
        pass

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
                f"👤 {req.from_user.full_name} (@{req.from_user.username or '—'})\n"
                f"🆔 <code>{uid}</code>\n"
                f"📢 <b>{req.chat.title}</b>",
                reply_markup=kb
            )
        except Exception:
            pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("jr_"))
def on_join_action(call):
    if call.from_user.id not in get_all_admins():
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


# ═══════════════════════════════════════════════════════════════
# 2-QISM TUGADI
# Keyingi: 3-QISM (Flask + Auth + HTML)
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# FLASK APP + AUTH
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
CORS(app, origins="*")


@app.after_request
def cors_headers(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Telegram-Init-Data'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return r


def validate_init_data(init_data):
    """Telegram WebApp initData imzosini tekshirish."""
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
# HTML MINI APP — TO'LIQ
# ═══════════════════════════════════════════════════════════════
HTML_PAGE = r'''<!DOCTYPE html>
<html lang="uz" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>QR Master</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script src="//libtl.com/sdk.js" data-zone="11990967" data-sdk="show_11990967"></script>
<style>
:root{--bg:#fff;--fg:#0f172a;--muted:#64748b;--card:#f1f5f9;--primary:#6366f1;
--primary-2:#8b5cf6;--border:#e2e8f0;--success:#22c55e;--danger:#ef4444;
--warning:#f59e0b;--radius:16px}
[data-theme="dark"]{--bg:#0f172a;--fg:#f1f5f9;--muted:#94a3b8;--card:#1e293b;--border:#334155}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:var(--bg);color:var(--fg);padding-bottom:80px;min-height:100dvh;overflow-x:hidden}
.header{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;
background:var(--bg);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:19px}
.lm{width:34px;height:34px;border-radius:10px;
background:linear-gradient(135deg,var(--primary),var(--primary-2));
display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;
box-shadow:0 4px 12px rgba(99,102,241,.3)}
.av{width:36px;height:36px;border-radius:50%;
background:linear-gradient(135deg,#06b6d4,var(--primary));
display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:14px}
.main{padding:0 16px}
.hero{margin:16px 0;padding:22px;border-radius:var(--radius);
background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;
box-shadow:0 10px 30px rgba(99,102,241,.35)}
.hero h2{font-size:20px;margin-bottom:6px;font-weight:800}
.hero p{font-size:13px;opacity:.9}
.st{font-size:15px;font-weight:700;margin:22px 0 12px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.tc{background:var(--card);border:none;border-radius:14px;padding:14px 8px;
display:flex;flex-direction:column;align-items:center;gap:6px;cursor:pointer;
color:var(--fg);font-family:inherit;transition:transform .15s}
.tc:active{transform:scale(.94)}
.ti{font-size:24px;line-height:1}
.tl{font-size:11px;text-align:center;font-weight:600;line-height:1.2}
.nav{position:fixed;bottom:0;left:0;right:0;display:flex;background:var(--bg);
border-top:1px solid var(--border);padding:8px 0 calc(8px + env(safe-area-inset-bottom));z-index:100}
.nb{flex:1;background:none;border:none;color:var(--muted);display:flex;
flex-direction:column;align-items:center;gap:2px;padding:6px 4px;font-size:10px;
font-weight:600;cursor:pointer;font-family:inherit}
.nb.active{color:var(--primary)}
.nb .ico{font-size:20px;line-height:1}
.page{display:none;animation:fade .25s ease}
.page.active{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.field{margin-bottom:14px}
.field label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px;font-weight:600}
.input,.select,.textarea{width:100%;padding:14px 16px;background:var(--card);
border:1.5px solid transparent;border-radius:14px;font-size:15px;color:var(--fg);
outline:none;font-family:inherit}
.input:focus,.textarea:focus,.select:focus{border-color:var(--primary)}
.textarea{resize:vertical;min-height:80px}
.btn{width:100%;padding:16px;border:none;border-radius:14px;font-size:15px;
font-weight:700;cursor:pointer;font-family:inherit;transition:transform .15s}
.btn:active{transform:scale(.97)}
.bp{background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;
box-shadow:0 6px 20px rgba(99,102,241,.35)}
.bg{background:var(--card);color:var(--fg)}
.bw{background:linear-gradient(135deg,var(--warning),var(--danger));color:#fff}
.qr-r{margin-top:20px;padding:20px;border-radius:var(--radius);
background:var(--card);text-align:center}
.qr-r canvas{border-radius:12px;max-width:100%;height:auto}
.qa{display:flex;gap:8px;margin-top:14px}
.qa .btn{padding:12px;font-size:13px}
.tw{position:fixed;top:80px;left:50%;transform:translateX(-50%);z-index:1000;
display:flex;flex-direction:column;gap:8px;pointer-events:none;max-width:90vw}
.toast{padding:12px 20px;border-radius:12px;color:#fff;font-size:14px;
font-weight:600;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,.15)}
.toast.success{background:var(--success)}
.toast.error{background:var(--danger)}
.toast.info{background:var(--primary)}
.empty{text-align:center;padding:40px 20px;color:var(--muted);font-size:14px}
.empty .ico{font-size:44px;display:block;margin-bottom:10px;opacity:.5}
.hi{display:flex;align-items:center;gap:12px;padding:14px;background:var(--card);
border-radius:14px;margin-bottom:8px}
.hi-i{flex:1;min-width:0}
.hi-i h4{font-size:14px;font-weight:700;margin-bottom:3px;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
.hi-i p{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ic{width:34px;height:34px;border-radius:10px;border:none;background:var(--bg);
color:var(--fg);cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center}
.pc{padding:20px;border-radius:var(--radius);
background:linear-gradient(135deg,var(--primary),var(--primary-2));color:#fff;
text-align:center;margin-bottom:16px;box-shadow:0 10px 30px rgba(99,102,241,.35)}
.pc .av{width:70px;height:70px;border-radius:50%;background:rgba(255,255,255,.2);
margin:0 auto 10px;display:flex;align-items:center;justify-content:center;
font-size:28px;font-weight:800}
.pc h3{font-size:17px;margin-bottom:4px}
.pc p{font-size:13px;opacity:.85}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:16px}
.stat{background:rgba(255,255,255,.15);padding:10px;border-radius:12px}
.stat b{display:block;font-size:18px;font-weight:800}
.stat span{font-size:10px;opacity:.85}
.loading{position:fixed;inset:0;background:rgba(15,23,42,.55);display:none;
align-items:center;justify-content:center;z-index:2000}
.loading.on{display:flex}
.spin{width:42px;height:42px;border:3px solid rgba(255,255,255,.25);
border-top-color:#fff;border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.rl{background:var(--card);padding:12px;border-radius:10px;
font-family:'Courier New',monospace;font-size:11px;word-break:break-all;
margin:10px 0;border:1px solid var(--border);color:var(--primary)}
.lu{display:flex;align-items:center;gap:10px;padding:14px;background:var(--card);
border-radius:14px;border:2px dashed var(--border);cursor:pointer;margin-bottom:10px}
.lu img{width:50px;height:50px;object-fit:contain;border-radius:8px;background:var(--bg)}
.ep{padding:60px 20px;text-align:center}
.ep .ico{font-size:64px;margin-bottom:20px}
.ep h2{color:var(--primary);margin-bottom:10px;font-size:20px}
.ep p{color:var(--muted);line-height:1.6;font-size:14px}
.badge{display:inline-block;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:700}
.badge.ok{background:rgba(34,197,94,.15);color:var(--success)}
.badge.warn{background:rgba(245,158,11,.15);color:var(--warning)}
.color-row{display:flex;gap:10px}
.color-row .field{flex:1}
input[type=color]{width:100%;height:50px;border:none;border-radius:12px;
background:transparent;cursor:pointer;padding:0}
</style>
</head>
<body>

<div class="header">
  <div class="logo"><div class="lm">QR</div><span>QR Master</span></div>
  <div class="av" id="av">U</div>
</div>

<div class="main" id="mainC">

  <div class="page active" id="p-home">
    <div class="hero"><h2>🎯 QR Master</h2><p>20+ turdagi QR kod yaratish va dizayn</p></div>
    <div class="st">QR Turlari</div>
    <div class="grid" id="tg"></div>
    <div class="st">So'nggi QR kodlar</div>
    <div id="rl"></div>
  </div>

  <div class="page" id="p-create">
    <div class="st" id="ct">QR kod</div>
    <div id="df"></div>
    <div class="st">🎨 Dizayn</div>
    <div class="color-row">
      <div class="field"><label>QR rangi</label>
        <input type="color" id="fc" value="#6366f1"></div>
      <div class="field"><label>Fon rangi</label>
        <input type="color" id="bc" value="#ffffff"></div>
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
      <button class="btn bg" id="cl" style="display:none;padding:8px;font-size:12px">🗑 O'chirish</button>
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
      <div class="qa"><button class="btn bp" id="dlb">⬇️ Yuklab olish</button></div>
    </div>
  </div>

  <div class="page" id="p-ads">
    <div class="st">🎬 Reklama / Unlock</div>
    <div class="hero"><h2>🔓 Qo'shimcha QR limit</h2><p>Reklama ko'ring yoki do'st taklif qiling</p></div>
    <div class="hi">
      <div class="hi-i"><h4>🎁 Bepul limit</h4><p id="fc2">5 ta</p></div>
      <span class="badge ok">FREE</span>
    </div>
    <div class="hi">
      <div class="hi-i"><h4>🔓 Unlock qilingan</h4><p id="uc">0 ta</p></div>
      <span class="badge warn">UNLOCK</span>
    </div>
    <button class="btn bw" id="wab" style="margin-top:14px">▶️ Reklama ko'rish (+3 QR)</button>
    <button class="btn bp" id="ib" style="margin-top:8px">👥 Do'st taklif qilish (+10 QR)</button>
    <div class="st">📊 Statistika</div>
    <div class="hi">
      <div class="hi-i"><h4>Ko'rilgan reklamalar</h4><p id="at">0</p></div>
      <span class="badge ok" id="ab">+0</span>
    </div>
  </div>

  <div class="page" id="p-hist">
    <div class="st">🕐 Tarix</div>
    <div id="hl"></div>
  </div>

  <div class="page" id="p-ref">
    <div class="st">👥 Referal tizimi</div>
    <div class="hero"><h2>🎁 Har referal +10 QR</h2><p>Do'stni taklif qiling va bonus oling</p></div>
    <div class="field"><label>🔗 Sizning havolangiz:</label>
      <div class="rl" id="rlink">—</div></div>
    <button class="btn bp" id="cr">📋 Nusxalash</button>
    <button class="btn bg" id="sr" style="margin-top:8px">📤 Ulashish</button>
    <div class="st">Referallaringiz (<span id="rc">0</span>)</div>
    <div id="rlist"></div>
  </div>

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
const MZ = "11990967";

const AdManager = {
  async show() {
    const fn = window['show_' + MZ];
    if (typeof fn !== 'function') {
      console.warn('Monetag SDK yuklanmagan');
      // SDK yo'q bo'lsa ham foydalanuvchiga imkon beramiz (dev/test)
      // Production da false qaytarish mumkin
      return false;
    }
    try {
      // Turli formatlarni sinab ko'ramiz
      try {
        await fn('pop');
        return true;
      } catch (e1) {
        try {
          await fn();
          return true;
        } catch (e2) {
          try {
            const r = fn('pop');
            if (r && typeof r.then === 'function') await r;
            return true;
          } catch (e3) {
            console.warn('Reklama xatosi:', e1, e2, e3);
            return false;
          }
        }
      }
    } catch (e) {
      console.warn('Reklama xatosi:', e);
      return false;
    }
  }
};

const App = {
  currentType: 'universal',
  currentData: null,
  initData: '',
  me: null,
  logoData: null,

  async start() {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready(); tg.expand();
      document.documentElement.setAttribute('data-theme',
        tg.colorScheme === 'dark' ? 'dark' : 'light');
    }
    this.initData = tg?.initData || '';

    if (!this.initData) {
      this.showError('⚠️', 'Telegram orqali oching',
        'Bu sahifa faqat Telegram bot orqali ishlaydi.<br><br>Botga qaytib <b>🧩 QR yaratish</b> tugmasini bosing.');
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
          'Botdan foydalanish uchun kanalga obuna bo\'ling.<br><br>Botga qaytib <b>✅ Obunani tekshirish</b> tugmasini bosing.');
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

  showError(icon, title, text) {
    document.getElementById('mainC').innerHTML =
      '<div class="ep"><div class="ico">' + icon + '</div><h2>' + title + '</h2><p>' + text + '</p></div>';
    document.querySelector('.nav').style.display = 'none';
  },

  async api(path, method = 'GET', body = null) {
    const opts = {
      method,
      headers: {
        'X-Telegram-Init-Data': this.initData,
        'Content-Type': 'application/json'
      }
    };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    const data = await r.json().catch(() => ({ detail: 'Xatolik' }));
    if (!r.ok) {
      const err = new Error(data.detail || 'Xatolik');
      err.payload = data;
      err.status = r.status;
      throw err;
    }
    return data;
  },

  updateStats() {
    if (!this.me) return;
    document.getElementById('s1').textContent = this.me.qr_count || 0;
    document.getElementById('s2').textContent = this.me.ad_count || 0;
    document.getElementById('s3').textContent = this.me.unlock_count || 0;
    document.getElementById('s4').textContent = this.me.referrals || 0;
    document.getElementById('fc2').textContent = (this.me.remaining != null ? this.me.remaining : (this.me.free_qr || 5)) + ' ta';
    document.getElementById('uc').textContent = (this.me.unlock_count || 0) + ' ta';
    document.getElementById('at').textContent = this.me.ad_count || 0;
    const bonus = this.me.ad_bonus || 3;
    document.getElementById('ab').textContent = '+' + bonus;
    const wab = document.getElementById('wab');
    if (wab) wab.textContent = '▶️ Reklama ko\'rish (+' + bonus + ' QR)';
  },

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

  types: [
    {id:'universal',i:'✨',l:'Universal',f:[{k:'text',l:'Matn / URL',t:'textarea',p:'Istalgan matn'}]},
    {id:'url',i:'🔗',l:'URL',f:[{k:'url',l:'Havola',t:'url',p:'https://example.com'}]},
    {id:'text',i:'📝',l:'Matn',f:[{k:'text',l:'Matn',t:'textarea',p:'Salom dunyo!'}]},
    {id:'wifi',i:'📶',l:'Wi-Fi',f:[
      {k:'ssid',l:'Tarmoq',t:'text'},
      {k:'pass',l:'Parol',t:'text'},
      {k:'sec',l:'Xavfsizlik',t:'select',o:['WPA','WEP','nopass']}]},
    {id:'vcard',i:'👤',l:'Kontakt',f:[
      {k:'first',l:'Ism',t:'text'},{k:'last',l:'Familiya',t:'text'},
      {k:'phone',l:'Telefon',t:'tel'},{k:'email',l:'Email',t:'email'}]},
    {id:'phone',i:'📞',l:'Telefon',f:[{k:'phone',l:'Raqam',t:'tel',p:'+998901234567'}]},
    {id:'sms',i:'💬',l:'SMS',f:[{k:'phone',l:'Telefon',t:'tel'},{k:'msg',l:'Xabar',t:'textarea'}]},
    {id:'email',i:'✉️',l:'Email',f:[{k:'to',l:'Kimga',t:'email'},{k:'subject',l:'Mavzu',t:'text'}]},
    {id:'tg',i:'✈️',l:'Telegram',f:[{k:'username',l:'Username',t:'text',p:'durov'}]},
    {id:'instagram',i:'📸',l:'Instagram',f:[{k:'username',l:'Username',t:'text'}]},
    {id:'youtube',i:'▶️',l:'YouTube',f:[{k:'url',l:'URL',t:'url'}]},
    {id:'tiktok',i:'🎵',l:'TikTok',f:[{k:'username',l:'Username',t:'text'}]},
    {id:'geo',i:'📍',l:'Geo',f:[
      {k:'lat',l:'Kenglik',t:'text',p:'41.311081'},{k:'lng',l:'Uzunlik',t:'text',p:'69.240562'}]},
    {id:'event',i:'📅',l:'Tadbir',f:[
      {k:'title',l:'Nomi',t:'text'},{k:'start',l:'Boshlanish',t:'text',p:'2025-12-31 18:00'}]},
    {id:'video',i:'🎬',l:'Video',f:[{k:'url',l:'Video URL',t:'url'}]},
    {id:'audio',i:'🎧',l:'Audio',f:[{k:'url',l:'Audio URL',t:'url'}]},
    {id:'pdf',i:'📄',l:'PDF',f:[{k:'url',l:'PDF URL',t:'url'}]},
    {id:'image',i:'🖼️',l:'Rasm',f:[{k:'url',l:'Rasm URL',t:'url'}]},
    {id:'app',i:'📱',l:'Ilova',f:[{k:'name',l:'Nomi',t:'text'},{k:'url',l:'URL',t:'url'}]},
    {id:'custom',i:'⚙️',l:'Maxsus',f:[{k:'raw',l:'Format',t:'textarea'}]},
  ],

  renderTypes() {
    document.getElementById('tg').innerHTML = this.types.map(t =>
      '<button class="tc" data-t="' + t.id + '">' +
        '<span class="ti">' + t.i + '</span>' +
        '<span class="tl">' + t.l + '</span>' +
      '</button>'
    ).join('');
    document.querySelectorAll('.tc').forEach(b => {
      b.onclick = () => this.openCreate(b.dataset.t);
    });
  },

  openCreate(id) {
    const t = this.types.find(x => x.id === id);
    if (!t) return;
    this.currentType = id;
    document.getElementById('ct').textContent = t.i + ' ' + t.l;
    document.getElementById('df').innerHTML = t.f.map(f => {
      let el;
      if (f.t === 'textarea') el = '<textarea class="textarea" id="f_' + f.k + '" placeholder="' + (f.p||'') + '"></textarea>';
      else if (f.t === 'select') el = '<select class="select" id="f_' + f.k + '">' + f.o.map(o => '<option>' + o + '</option>').join('') + '</select>';
      else el = '<input class="input" type="' + f.t + '" id="f_' + f.k + '" placeholder="' + (f.p||'') + '">';
      return '<div class="field"><label>' + f.l + '</label>' + el + '</div>';
    }).join('');
    document.getElementById('qr').style.display = 'none';
    this.go('create');
  },

  buildPayload() {
    const v = id => (document.getElementById('f_' + id)?.value || '').trim();
    const enc = encodeURIComponent;
    const m = {
      universal: () => v('text'),
      text: () => v('text'),
      url: () => v('url'),
      wifi: () => 'WIFI:T:' + (v('sec')||'WPA') + ';S:' + v('ssid') + ';P:' + v('pass') + ';;',
      vcard: () => ['BEGIN:VCARD','VERSION:3.0',
        'N:' + v('last') + ';' + v('first') + ';;;',
        ('FN:' + v('first') + ' ' + v('last')).trim(),
        v('phone') ? 'TEL:' + v('phone') : '',
        v('email') ? 'EMAIL:' + v('email') : '',
        'END:VCARD'].filter(Boolean).join('\n'),
      phone: () => 'tel:' + v('phone'),
      sms: () => 'SMSTO:' + v('phone') + ':' + v('msg'),
      email: () => 'mailto:' + v('to') + '?subject=' + enc(v('subject')),
      tg: () => 'https://t.me/' + v('username').replace('@',''),
      instagram: () => 'https://instagram.com/' + v('username').replace('@',''),
      youtube: () => v('url'),
      tiktok: () => 'https://tiktok.com/@' + v('username').replace('@',''),
      geo: () => 'geo:' + v('lat') + ',' + v('lng'),
      event: () => ['BEGIN:VEVENT','SUMMARY:' + v('title'),
        'DTSTART:' + v('start').replace(/[-: ]/g,''),'END:VEVENT'].join('\n'),
      video: () => v('url'),
      audio: () => v('url'),
      pdf: () => v('url'),
      image: () => v('url'),
      app: () => 'APP:' + v('name') + '|URL:' + v('url'),
      custom: () => v('raw'),
    };
    return (m[this.currentType] || (() => ''))();
  },

  async generate() {
    const data = this.buildPayload();
    if (!data) return this.toast("Ma'lumot kiriting", 'error');
    if (typeof QRCode === 'undefined') return this.toast("QR kutubxona yo'q", 'error');

    // LIMIT TEKSHIRUVI — avval tekshiramiz, QR yaratmaymiz
    if (this.me) {
      const remaining = this.me.remaining != null
        ? this.me.remaining
        : Math.max(0, (this.me.allowed || (this.me.free_qr || 5) + (this.me.unlock_count || 0)) - (this.me.qr_count || 0));
      if (remaining <= 0) {
        const bonus = this.me.ad_bonus || 3;
        const ok = confirm('🎬 Limit tugadi!\n\nReklama ko\'rib +' + bonus + ' QR unlock olasizmi?');
        if (!ok) return;
        // Reklama ko'rsatish (loading yo'q — reklama ustida chiqishi uchun)
        const watched = await AdManager.show();
        if (!watched) {
          this.toast("Reklama ochilmadi. Keyinroq urinib ko'ring yoki SDK yuklanmagan.", 'error');
          return;
        }
        try {
          this.load(true);
          const ar = await this.api('/api/qr/ad', 'POST', {});
          this.me.unlock_count = ar.unlock;
          this.me.ad_count = ar.ad_count;
          this.me.remaining = ar.remaining;
          this.me.allowed = ar.allowed;
          this.updateStats();
          this.toast('🎁 +' + (ar.bonus || bonus) + ' QR unlock!', 'success');
          this.load(false);
        } catch (e) {
          this.load(false);
          this.toast(e.message || 'Unlock xato', 'error');
          return;
        }
        // unlock olindi — pastga tushib QR yaratish davom etadi
      }
    }

    const size = parseInt(document.getElementById('qs').value);
    const fill = document.getElementById('fc').value;
    const back = document.getElementById('bc').value;

    try {
      this.load(true);
      const c = document.getElementById('qc');
      c.innerHTML = '';

      const wrapper = document.createElement('div');
      wrapper.style.cssText =
        'display:inline-block;padding:24px;' +
        'background:linear-gradient(135deg,' + fill + '15,' + fill + '25);' +
        'border-radius:24px;box-shadow:0 15px 40px ' + fill + '40;' +
        'border:1px solid ' + fill + '30;';
      c.appendChild(wrapper);

      const qrDiv = document.createElement('div');
      qrDiv.style.cssText =
        'padding:14px;background:' + back + ';' +
        'border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,.1);';
      wrapper.appendChild(qrDiv);

      new QRCode(qrDiv, {
        text: data, width: size, height: size,
        colorDark: fill, colorLight: back,
        correctLevel: QRCode.CorrectLevel.H
      });

      if (this.logoData) {
        setTimeout(() => {
          const canvas = qrDiv.querySelector('canvas');
          if (!canvas) return;
          const ctx = canvas.getContext('2d');
          const img = new Image();
          img.onload = () => {
            const s = canvas.width, ls = s * 0.22, p = s * 0.015;
            const x = (s - ls) / 2, y = (s - ls) / 2;
            ctx.fillStyle = '#fff';
            ctx.fillRect(x - p, y - p, ls + p*2, ls + p*2);
            ctx.drawImage(img, x, y, ls, ls);
          };
          img.src = this.logoData;
        }, 150);
      }

      this.currentData = data;
      document.getElementById('qr').style.display = 'block';
      document.getElementById('qr').scrollIntoView({ behavior: 'smooth' });
      this.toast('QR kod yaratildi ✅', 'success');

      setTimeout(() => this.save(), 800);
    } catch (e) {
      this.toast('Xato: ' + e.message, 'error');
    } finally {
      this.load(false);
    }
  },

  async save() {
    if (!this.currentData) return;
    try {
      const r = await this.api('/api/qr/save', 'POST', {
        qr_type: this.currentType,
        name: this.types.find(t => t.id === this.currentType)?.l || 'QR',
        data: this.currentData
      });

      this.toast('✅ Botga saqlandi!', 'success');

      if (this.me) {
        this.me.qr_count = r.total;
        if (r.remaining != null) this.me.remaining = r.remaining;
        this.updateStats();
      }
      await this.loadHistory();

      if (r.show_ad) {
        // Bu QR saqlandi, lekin keyingisi uchun limit tugadi
        if (this.me) this.me.remaining = 0;
        this.updateStats();
        this.toast('Bu QR saqlandi. Keyingisi uchun reklama kerak.', 'info');
      }
    } catch (e) {
      const p = e.payload || {};
      if (e.status === 403 && p.show_ad) {
        // Limit — QR ni yashiramiz (yaratilmasligi kerak edi)
        document.getElementById('qr').style.display = 'none';
        this.currentData = null;
        if (this.me) {
          this.me.remaining = 0;
          this.updateStats();
        }
        const bonus = p.ad_bonus || this.me?.ad_bonus || 3;
        const ok = confirm('🎬 Limit tugadi!\n\nReklama ko\'rib +' + bonus + ' QR unlock olasizmi?');
        if (!ok) {
          this.toast('Limit tugagan. Reklama ko\'ring yoki do\'st taklif qiling.', 'error');
          return;
        }
        // Loading O'CHIQ — reklama to'silib qolmasin
        const watched = await AdManager.show();
        if (!watched) {
          this.toast("Reklama ochilmadi. 'Reklama' bo'limidan qayta urinib ko'ring.", 'error');
          return;
        }
        try {
          this.load(true);
          const ar = await this.api('/api/qr/ad', 'POST', {});
          if (this.me) {
            this.me.unlock_count = ar.unlock;
            this.me.ad_count = ar.ad_count;
            this.me.remaining = ar.remaining;
            this.me.allowed = ar.allowed;
            this.updateStats();
          }
          this.load(false);
          this.toast('🎁 +' + (ar.bonus || bonus) + ' QR unlock! Endi qayta yarating.', 'success');
        } catch (e2) {
          this.load(false);
          this.toast(e2.message, 'error');
        }
        return;
      }
      this.toast('Saqlash xato: ' + e.message, 'error');
    }
  },

  download() {
    const canvas = document.querySelector('#qc canvas');
    if (!canvas) return this.toast("QR yo'q", 'error');
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'qrmaster-' + Date.now() + '.png';
    a.click();
    this.toast('Yuklab olindi ✅', 'success');
  },

  async loadHistory() {
    try {
      const list = await this.api('/api/qr/list');
      this.renderHistory(list);
      this.renderRecent(list);
    } catch (e) { console.warn(e); }
  },

  renderRecent(list) {
    const el = document.getElementById('rl');
    const r = list.slice(0, 3);
    if (!r.length) {
      el.innerHTML = '<div class="empty"><span class="ico">🎯</span>Hozircha bo\'sh</div>';
      return;
    }
    el.innerHTML = r.map(h =>
      '<div class="hi"><div class="hi-i">' +
        '<h4>' + h.name + '</h4>' +
        '<p>' + h.qr_type + ' · ' + new Date(h.created_at).toLocaleString('uz') + '</p>' +
      '</div></div>'
    ).join('');
  },

  renderHistory(list) {
    const el = document.getElementById('hl');
    if (!list.length) {
      el.innerHTML = '<div class="empty"><span class="ico">🕐</span>Tarix bo\'sh</div>';
      return;
    }
    el.innerHTML = list.map(h =>
      '<div class="hi"><div class="hi-i">' +
        '<h4>' + h.name + '</h4>' +
        '<p>' + h.qr_type + ' · ' + new Date(h.created_at).toLocaleString('uz') + '</p>' +
      '</div>' +
      '<button class="ic" onclick="App.delQr(' + h.id + ')">🗑</button></div>'
    ).join('');
  },

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
    } catch (e) { this.toast(e.message, 'error'); }
  },

  async loadRefs() {
    const u = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (!u) return;
    const bot = this.me?.bot_username || 'BotUsername';
    document.getElementById('rlink').textContent =
      'https://t.me/' + bot + '?start=ref_' + u.id;

    try {
      const d = await this.api('/api/ref/list');
      document.getElementById('rc').textContent = d.total || 0;
      const el = document.getElementById('rlist');
      if (!d.refs || !d.refs.length) {
        el.innerHTML = '<div class="empty"><span class="ico">👥</span>Referal yo\'q</div>';
        return;
      }
      el.innerHTML = d.refs.map(r =>
        '<div class="hi"><div class="hi-i">' +
          '<h4>' + (r.first_name || 'Foydalanuvchi') + '</h4>' +
          '<p>@' + (r.username || '—') + '</p>' +
        '</div></div>'
      ).join('');
    } catch (e) { console.warn(e); }
  },

  bindRef() {
    document.getElementById('cr').onclick = async () => {
      try {
        await navigator.clipboard.writeText(document.getElementById('rlink').textContent);
        this.toast('Nusxalandi 📋', 'success');
      } catch { this.toast('Xato', 'error'); }
    };
    document.getElementById('sr').onclick = () => {
      const l = document.getElementById('rlink').textContent;
      window.open('https://t.me/share/url?url=' + encodeURIComponent(l) + '&text=QR Master', '_blank');
    };
  },

  bindAds() {
    document.getElementById('wab').onclick = async () => {
      // Loading YO'Q — reklama to'silmasin
      const ok = await AdManager.show();
      if (ok) {
        try {
          this.load(true);
          const r = await this.api('/api/qr/ad', 'POST', {});
          this.me.unlock_count = r.unlock;
          this.me.ad_count = r.ad_count;
          this.me.remaining = r.remaining;
          this.me.allowed = r.allowed;
          this.updateStats();
          this.load(false);
          this.toast('🎁 +' + (r.bonus || 3) + ' QR unlock!', 'success');
        } catch (e) {
          this.load(false);
          this.toast(e.message, 'error');
        }
      } else {
        this.toast("Reklama ochilmadi. Internet yoki SDK muammosi bo'lishi mumkin.", 'error');
      }
    };
    document.getElementById('ib').onclick = () => this.go('ref');
  },

  bindProfile() {
    document.getElementById('tb').onclick = () => {
      const cur = document.documentElement.getAttribute('data-theme');
      document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
    };
    document.getElementById('rl2').onclick = async () => {
      this.load(true);
      try {
        this.me = await this.api('/api/me', 'POST');
        this.updateStats();
        await this.loadHistory();
        await this.loadRefs();
        this.toast('Yangilandi ✅', 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      this.load(false);
    };
  },

  bindForm() {
    document.getElementById('gb').onclick = () => this.generate();
    document.getElementById('bb').onclick = () => this.go('home');
    document.getElementById('dlb').onclick = () => this.download();

    document.getElementById('lf').onchange = (e) => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 500 * 1024) return this.toast('500 KB dan oshmasin', 'error');
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

  bindNav() {
    document.querySelectorAll('.nb').forEach(b => {
      b.onclick = () => this.go(b.dataset.page);
    });
  },

  go(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById('p-' + name)?.classList.add('active');
    document.querySelectorAll('.nb').forEach(b =>
      b.classList.toggle('active', b.dataset.page === name));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  toast(msg, type = 'info') {
    const w = document.getElementById('tw');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    w.appendChild(el);
    setTimeout(() => el.remove(), 3500);
  },

  load(on) {
    document.getElementById('ld').classList.toggle('on', on);
  }
};

window.addEventListener('DOMContentLoaded', () => App.start());
</script>
</body>
</html>
'''


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

    info = get_qr_limit_info(tg["id"])
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
        "free_qr": info["free"],
        "ad_bonus": get_int_setting("ad_bonus_qr", 3),
        "remaining": info["remaining"],
        "allowed": info["allowed"],
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
    uid = tg["id"]

    # Limit tekshiruvi: free + unlock
    info = get_qr_limit_info(uid)
    if not info["can_create"]:
        bonus = get_int_setting("ad_bonus_qr", 3)
        return jsonify({
            "ok": False,
            "detail": "Limit tugadi",
            "show_ad": True,
            "remaining": 0,
            "allowed": info["allowed"],
            "used": info["used"],
            "ad_bonus": bonus,
        }), 403

    qr_type = body.get("qr_type") or "universal"
    name = (body.get("name") or "QR")[:255]
    add_qr(uid, qr_type, name, data)

    info = get_qr_limit_info(uid)
    total = info["used"]
    remaining = info["remaining"]
    show_ad = remaining <= 0  # keyingi yaratish uchun reklama kerakmi

    bonus = get_int_setting("ad_bonus_qr", 3)

    # Botga xabar
    try:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(
            "📜 Mening QR larim",
            web_app=WebAppInfo(url=WEBAPP_URL)
        ))
        if show_ad:
            kb.add(InlineKeyboardButton(
                f"🎬 Reklama ko'rish (+{bonus} QR)",
                web_app=WebAppInfo(url=WEBAPP_URL)
            ))

        text = (f"✅ <b>Yangi QR kod saqlandi!</b>\n\n"
                f"📌 <b>{name}</b>\n"
                f"🔧 Turi: <code>{qr_type}</code>\n"
                f"📊 Jami: <b>{total}</b> ta\n"
                f"🎁 Qolgan limit: <b>{remaining}</b> ta\n")
        if show_ad:
            text += f"\n🎬 <b>Limit tugadi!</b>\nReklama ko'rib +{bonus} QR unlock oling."

        bot.send_message(uid, text, reply_markup=kb)
    except Exception as e:
        print(f"⚠️ Bot xabar: {e}")

    return jsonify({
        "ok": True,
        "total": total,
        "remaining": remaining,
        "show_ad": show_ad,
        "ad_bonus": bonus,
    })


@app.route("/api/qr/ad", methods=["POST", "OPTIONS"])
@auth_required
def api_qr_ad(tg):
    """Reklama ko'rilgandan keyin unlock berish. Limit yo'q — har chaqiruvda bonus."""
    log_ad_event(tg["id"], "rewarded", "completed")

    bonus = get_int_setting("ad_bonus_qr", 3)
    qx("UPDATE users SET unlock_count = unlock_count + ? WHERE telegram_id=?",
       (bonus, tg["id"]))

    u = get_user(tg["id"])
    info = get_qr_limit_info(tg["id"])
    return jsonify({
        "unlock": u.get("unlock_count", 0),
        "ad_count": u["ad_count"],
        "bonus": bonus,
        "remaining": info["remaining"],
        "allowed": info["allowed"],
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
    if delete_qr(qid, tg["id"]):
        return jsonify({"ok": True})
    return jsonify({"detail": "Topilmadi"}), 404


@app.route("/api/ref/list", methods=["GET", "OPTIONS"])
@auth_required
def api_ref_list(tg):
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
# ISHGA TUSHIRISH
# ═══════════════════════════════════════════════════════════════

def run_bot():
    while True:
        try:
            bot.remove_webhook()
            setup_bot()
            print("✅ Bot tayyor")
            print("=" * 60)
            print("🚀 Telegram'da /start bosing")
            print("=" * 60)
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
    threading.Thread(target=run_bot, daemon=True).start()
    time.sleep(3)

    print("=" * 60)
    print(f"🌐 Server:    http://0.0.0.0:{PORT}")
    print(f"🔗 Mini App:  {WEBAPP_URL}")
    print(f"👤 Admin:     {ADMIN_IDS}")
    print(f"💰 Monetag:   {MONETAG_ZONE}")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        threaded=True,
    )
