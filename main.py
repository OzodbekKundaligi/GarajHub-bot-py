# main.py
import os
import logging
import sqlite3
import json
import secrets
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_cors import CORS
import threading
import traceback

# ==================== KONFIGURATSIYA ====================
BOT_TOKEN = os.getenv('BOT_TOKEN', '8265294721:AAEWhiYC2zTYxPbFpYYFezZGNzKHUumoplE')
CHANNEL_USERNAME = '@GarajHub_uz'
ADMIN_ID = 7903688837
WEB_SECRET_KEY = 'garajhub-secret-key-2026'
WEB_HOST = '0.0.0.0'
WEB_PORT = 5000

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Flask Web App
app = Flask(__name__, template_folder='templates')
app.secret_key = WEB_SECRET_KEY
CORS(app)  # CORS qo'shing deployment uchun

# Error handler
@app.errorhandler(500)
def internal_error(error):
    logging.error(f'Internal error: {traceback.format_exc()}')
    return jsonify({'error': 'Internal Server Error', 'message': str(error)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not Found'}), 404

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Foydalanuvchilar
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            gender TEXT DEFAULT '',
            birth_date TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_admin BOOLEAN DEFAULT 0
        )
    ''')
    
    # Adminlar uchun tokenlar
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE,
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Startuplar
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS startups (
            startup_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            logo TEXT,
            group_link TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            results TEXT,
            views INTEGER DEFAULT 0,
            FOREIGN KEY (owner_id) REFERENCES users (user_id)
        )
    ''')
    
    # Startup a'zolari
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS startup_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            startup_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (startup_id) REFERENCES startups (startup_id),
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            UNIQUE(startup_id, user_id)
        )
    ''')
    
    # Web admin sessiyalari
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS web_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER,
            data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, is_admin) VALUES (?, ?, ?, 1)', 
                   (ADMIN_ID, 'admin', 'Admin'))
    
    conn.commit()
    conn.close()
    logging.info("Database initialized")

# ==================== DATABASE FUNKTSIYALARI ====================
def get_user(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def save_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name) 
        VALUES (?, ?, ?)
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def update_user_field(user_id: int, field: str, value: str):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(f'UPDATE users SET {field} = ? WHERE user_id = ?', (value, user_id))
    conn.commit()
    conn.close()

def create_startup(name: str, description: str, logo: str, group_link: str, owner_id: int) -> int:
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO startups (name, description, logo, group_link, owner_id, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
    ''', (name, description, logo, group_link, owner_id))
    startup_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return startup_id

def get_startup(startup_id: int) -> Optional[Dict]:
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM startups WHERE startup_id = ?', (startup_id,))
    startup = cursor.fetchone()
    conn.close()
    return dict(startup) if startup else None

def get_startups_by_owner(owner_id: int) -> List[Dict]:
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM startups WHERE owner_id = ? ORDER BY created_at DESC', (owner_id,))
    startups = cursor.fetchall()
    conn.close()
    return [dict(s) for s in startups]

def get_pending_startups(page: int = 1, per_page: int = 10) -> Tuple[List[Dict], int]:
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    offset = (page - 1) * per_page
    cursor.execute('''
        SELECT s.*, u.first_name, u.last_name, u.username 
        FROM startups s 
        JOIN users u ON s.owner_id = u.user_id 
        WHERE s.status = "pending" 
        ORDER BY s.created_at DESC 
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    startups = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) as count FROM startups WHERE status = "pending"')
    total = cursor.fetchone()['count']
    conn.close()
    return [dict(s) for s in startups], total

def get_active_startups(page: int = 1, per_page: int = 1) -> Tuple[List[Dict], int]:
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    offset = (page - 1) * per_page
    cursor.execute('''
        SELECT s.*, u.first_name, u.last_name, u.username 
        FROM startups s 
        JOIN users u ON s.owner_id = u.user_id 
        WHERE s.status = "active" 
        ORDER BY s.created_at DESC 
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    startups = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) as count FROM startups WHERE status = "active"')
    total = cursor.fetchone()['count']
    conn.close()
    return [dict(s) for s in startups], total

def update_startup_status(startup_id: int, status: str):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    if status == 'active':
        cursor.execute('UPDATE startups SET status = ?, started_at = CURRENT_TIMESTAMP WHERE startup_id = ?', 
                      (status, startup_id))
    elif status == 'completed':
        cursor.execute('UPDATE startups SET status = ?, ended_at = CURRENT_TIMESTAMP WHERE startup_id = ?', 
                      (status, startup_id))
    else:
        cursor.execute('UPDATE startups SET status = ? WHERE startup_id = ?', (status, startup_id))
    conn.commit()
    conn.close()

def add_startup_member(startup_id: int, user_id: int):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO startup_members (startup_id, user_id, status)
        VALUES (?, ?, 'pending')
    ''', (startup_id, user_id))
    conn.commit()
    conn.close()

def get_join_request_id(startup_id: int, user_id: int):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM startup_members WHERE startup_id = ? AND user_id = ?', (startup_id, user_id))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_join_request(request_id: int, status: str):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE startup_members SET status = ? WHERE id = ?', (status, request_id))
    conn.commit()
    conn.close()

def get_statistics() -> Dict:
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM startups')
    total_startups = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM startups WHERE status = "active"')
    active_startups = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM startups WHERE status = "pending"')
    pending_startups = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM startups WHERE status = "completed"')
    completed_startups = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM startup_members')
    total_members = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM startup_members WHERE status = "pending"')
    pending_requests = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_users': total_users,
        'total_startups': total_startups,
        'active_startups': active_startups,
        'pending_startups': pending_startups,
        'completed_startups': completed_startups,
        'total_members': total_members,
        'pending_requests': pending_requests
    }

def get_all_users():
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    return [u['user_id'] for u in users]

def get_recent_users(limit: int = 10):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM users 
        ORDER BY joined_at DESC 
        LIMIT ?
    ''', (limit,))
    users = cursor.fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_recent_startups(limit: int = 10):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, u.first_name, u.last_name, u.username 
        FROM startups s 
        JOIN users u ON s.owner_id = u.user_id 
        ORDER BY s.created_at DESC 
        LIMIT ?
    ''', (limit,))
    startups = cursor.fetchall()
    conn.close()
    return [dict(s) for s in startups]

# ==================== WEB SESSIYA FUNKTSIYALARI ====================
def create_web_session(user_id: int):
    session_id = secrets.token_hex(32)
    expires_at = datetime.now().timestamp() + 3600  # 1 soat
    
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO web_sessions (session_id, user_id, expires_at)
        VALUES (?, ?, ?)
    ''', (session_id, user_id, expires_at))
    conn.commit()
    conn.close()
    
    return session_id

def validate_web_session(session_id: str) -> Optional[int]:
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM web_sessions WHERE session_id = ? AND expires_at > ?', 
                   (session_id, datetime.now().timestamp()))
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else None

def delete_web_session(session_id: str):
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM web_sessions WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

# ==================== TELEGRAM BOT ====================
@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    save_user(user_id, username, first_name)
    
    # Check subscription
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            show_main_menu(message)
        else:
            ask_for_subscription(message)
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
        ask_for_subscription(message)

def ask_for_subscription(message):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton('🔗 Kanalga o\'tish', url=f'https://t.me/{CHANNEL_USERNAME[1:]}'),
        InlineKeyboardButton('✅ Tekshirish', callback_data='check_subscription')
    )
    bot.send_message(
        message.chat.id,
        "🤖 <b>GarajHub Bot</b>\n\n"
        "Botdan foydalanish uchun avval kanalimizga obuna bo'ling 👇",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == 'check_subscription')
def check_subscription_callback(call):
    user_id = call.from_user.id
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if chat_member.status in ['member', 'administrator', 'creator']:
            show_main_menu(call)
            bot.answer_callback_query(call.id, "✅ Obuna tasdiqlandi!")
        else:
            bot.answer_callback_query(call.id, "❌ Iltimos, kanalga obuna bo'ling!", show_alert=True)
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
        bot.answer_callback_query(call.id, "⚠️ Xatolik yuz berdi!", show_alert=True)

def show_main_menu(message_or_call):
    if isinstance(message_or_call, types.CallbackQuery):
        chat_id = message_or_call.message.chat.id
        try:
            bot.delete_message(chat_id, message_or_call.message.message_id)
        except:
            pass
    else:
        chat_id = message_or_call.chat.id
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton('🌐 Startuplar'),
        KeyboardButton('📌 Mening startuplarim'),
        KeyboardButton('➕ Startup yaratish'),
        KeyboardButton('👤 Profil')
    ]
    markup.add(*buttons)
    
    if chat_id == ADMIN_ID:
        markup.add(KeyboardButton('🛠 Admin panel'))
    
    text = "👋 <b>Assalomu alaykum!</b>\n\n🚀 <b>GarajHub</b> — startaplar uchun platforma.\n\nQuyidagilardan birini tanlang:"
    
    bot.send_message(chat_id, text, reply_markup=markup)

# ==================== PROFIL ====================
@bot.message_handler(func=lambda message: message.text == '👤 Profil')
def show_profile(message):
    user = get_user(message.from_user.id)
    if not user:
        save_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
        user = get_user(message.from_user.id)
    
    profile_text = (
        "👤 <b>Profil ma'lumotlari:</b>\n\n"
        f"🧑 <b>Ism:</b> {user.get('first_name', '—')}\n"
        f"🧾 <b>Familiya:</b> {user.get('last_name', '—')}\n"
        f"⚧️ <b>Jins:</b> {user.get('gender', '—')}\n"
        f"📞 <b>Telefon:</b> {user.get('phone', '+998*')}\n"
        f"🎂 <b>Tug'ilgan sana:</b> {user.get('birth_date', '—')}\n"
        f"📝 <b>Bio:</b> {user.get('bio', '—')}"
    )
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('✏️ Ism', callback_data='edit_first_name'),
        InlineKeyboardButton('✏️ Familiya', callback_data='edit_last_name'),
        InlineKeyboardButton('📞 Telefon', callback_data='edit_phone'),
        InlineKeyboardButton('⚧️ Jins', callback_data='edit_gender'),
        InlineKeyboardButton('🎂 Tug\'ilgan sana', callback_data='edit_birth_date'),
        InlineKeyboardButton('📝 Bio', callback_data='edit_bio')
    )
    
    markup.add(InlineKeyboardButton('🔙 Asosiy menyu', callback_data='main_menu'))
    
    bot.send_message(message.chat.id, profile_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_'))
def handle_edit_profile(call):
    if call.data == 'edit_first_name':
        msg = bot.send_message(call.message.chat.id, "📝 <b>Ismingizni kiriting:</b>")
        bot.register_next_step_handler(msg, process_first_name, call.message.message_id)
    
    elif call.data == 'edit_last_name':
        msg = bot.send_message(call.message.chat.id, "📝 <b>Familiyangizni kiriting:</b>")
        bot.register_next_step_handler(msg, process_last_name, call.message.message_id)
    
    elif call.data == 'edit_phone':
        msg = bot.send_message(call.message.chat.id, 
                              "📱 <b>Telefon raqamingizni kiriting:</b>\n\n"
                              "Masalan: <code>+998901234567</code>")
        bot.register_next_step_handler(msg, process_phone, call.message.message_id)
    
    elif call.data == 'edit_gender':
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton('👨 Erkak', callback_data='gender_male'),
            InlineKeyboardButton('👩 Ayol', callback_data='gender_female')
        )
        bot.send_message(call.message.chat.id, "⚧️ <b>Jinsingizni tanlang:</b>", reply_markup=markup)
    
    elif call.data == 'edit_birth_date':
        msg = bot.send_message(call.message.chat.id, 
                              "🎂 <b>Tug'ilgan sanangizni kiriting (kun-oy-yil)</b>\n"
                              "Masalan: <code>30-04-2010</code>")
        bot.register_next_step_handler(msg, process_birth_date, call.message.message_id)
    
    elif call.data == 'edit_bio':
        msg = bot.send_message(call.message.chat.id, "📝 <b>Bio kiriting:</b>")
        bot.register_next_step_handler(msg, process_bio, call.message.message_id)
    
    bot.answer_callback_query(call.id)

def process_first_name(message, prev_message_id):
    update_user_field(message.from_user.id, 'first_name', message.text)
    bot.send_message(message.chat.id, "✅ <b>Ismingiz muvaffaqiyatli saqlandi</b>")
    show_profile(message)

def process_last_name(message, prev_message_id):
    update_user_field(message.from_user.id, 'last_name', message.text)
    bot.send_message(message.chat.id, "✅ <b>Familiyangiz muvaffaqiyatli saqlandi</b>")
    show_profile(message)

def process_phone(message, prev_message_id):
    update_user_field(message.from_user.id, 'phone', message.text)
    bot.send_message(message.chat.id, "✅ <b>Telefon raqami muvaffaqiyatli saqlandi</b>")
    show_profile(message)

@bot.callback_query_handler(func=lambda call: call.data in ['gender_male', 'gender_female'])
def process_gender(call):
    gender = 'Erkak' if call.data == 'gender_male' else 'Ayol'
    update_user_field(call.from_user.id, 'gender', gender)
    bot.send_message(call.message.chat.id, "✅ <b>Jins muvaffaqiyatli saqlandi</b>")
    show_profile(call.message)
    bot.answer_callback_query(call.id)

def process_birth_date(message, prev_message_id):
    update_user_field(message.from_user.id, 'birth_date', message.text)
    bot.send_message(message.chat.id, "✅ <b>Tug'ilgan sana muvaffaqiyatli saqlandi</b>")
    show_profile(message)

def process_bio(message, prev_message_id):
    update_user_field(message.from_user.id, 'bio', message.text)
    bot.send_message(message.chat.id, "✅ <b>Bio saqlandi</b>")
    show_profile(message)

# ==================== STARTUPLAR ====================
@bot.message_handler(func=lambda message: message.text == '🌐 Startuplar')
def show_startups(message):
    show_startup_page(message.chat.id, 1)

def show_startup_page(chat_id, page):
    startups, total = get_active_startups(page)
    
    if not startups:
        bot.send_message(chat_id, "📭 <b>Hozircha startup mavjud emas.</b>")
        return
    
    startup = startups[0]
    owner_name = f"{startup.get('first_name', '')} {startup.get('last_name', '')}".strip()
    
    total_pages = max(1, total)
    
    text = (
        f"<b>🌐 Startuplar</b>\n"
        f"📄 Sahifa: <b>{page}/{total_pages}</b>\n\n"
        f"🎯 <b>{startup['name']}</b>\n"
        f"📌 {startup['description'][:200]}...\n"
        f"👤 <b>Muallif:</b> {owner_name}"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton('🤝 Startupga qo\'shilish', 
                                   callback_data=f'join_startup_{startup["startup_id"]}'))
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton('⏮️ Oldingi', callback_data=f'startup_page_{page-1}'))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton('⏭️ Keyingi', callback_data=f'startup_page_{page+1}'))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    markup.add(InlineKeyboardButton('🔙 Asosiy menyu', callback_data='main_menu'))
    
    try:
        if startup.get('logo'):
            bot.send_photo(chat_id, startup['logo'], caption=text, reply_markup=markup)
        else:
            bot.send_message(chat_id, text, reply_markup=markup)
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('startup_page_'))
def handle_startup_page(call):
    page = int(call.data.split('_')[2])
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_startup_page(call.message.chat.id, page)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_startup_'))
def handle_join_startup(call):
    startup_id = int(call.data.split('_')[2])
    user_id = call.from_user.id
    
    # Check if already requested
    request_id = get_join_request_id(startup_id, user_id)
    
    if request_id:
        bot.answer_callback_query(call.id, "📩 Sizning so'rovingiz hali ko'rib chiqilmoqda!", show_alert=True)
        return
    
    # Add join request
    add_startup_member(startup_id, user_id)
    request_id = get_join_request_id(startup_id, user_id)
    
    # Send notification to startup owner
    startup = get_startup(startup_id)
    user = get_user(user_id)
    
    if startup and user:
        text = (
            f"🆕 <b>Startupga qo'shilish so'rovi</b>\n\n"
            f"👤 <b>Foydalanuvchi:</b> {user.get('first_name', '')} {user.get('last_name', '')}\n"
            f"📱 <b>Telefon:</b> {user.get('phone', '—')}\n"
            f"📝 <b>Bio:</b> {user.get('bio', '—')}\n"
            f"🎯 <b>Startup:</b> {startup['name']}\n\n"
            f"🆔 <b>So'rov ID:</b> {request_id}"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton('✅ Tasdiqlash', callback_data=f'approve_join_{request_id}'),
            InlineKeyboardButton('❌ Rad etish', callback_data=f'reject_join_{request_id}')
        )
        
        try:
            bot.send_message(startup['owner_id'], text, reply_markup=markup)
        except:
            pass
    
    bot.answer_callback_query(call.id, "✅ So'rov yuborildi. Startup egasi tasdiqlasa, sizga havola yuboriladi.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_join_'))
def approve_join_request(call):
    request_id = int(call.data.split('_')[2])
    
    # Get request details
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT startup_id, user_id FROM startup_members WHERE id = ?', (request_id,))
    result = cursor.fetchone()
    
    if not result:
        bot.answer_callback_query(call.id, "❌ So'rov topilmadi!", show_alert=True)
        conn.close()
        return
    
    startup_id, user_id = result
    update_join_request(request_id, 'accepted')
    
    # Send group link to user
    startup = get_startup(startup_id)
    if startup:
        try:
            bot.send_message(
                user_id,
                f"🎉 <b>Tabriklaymiz!</b>\n\n"
                f"✅ Sizning so'rovingiz qabul qilindi.\n\n"
                f"🎯 <b>Startup:</b> {startup['name']}\n"
                f"🔗 <b>Guruhga qo'shilish:</b> {startup['group_link']}"
            )
        except:
            pass
    
    try:
        bot.edit_message_text(
            "✅ <b>So'rov tasdiqlandi va foydalanuvchiga havola yuborildi.</b>",
            call.message.chat.id,
            call.message.message_id
        )
    except:
        bot.send_message(call.message.chat.id, "✅ <b>So'rov tasdiqlandi.</b>")
    
    conn.close()
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_join_'))
def reject_join_request(call):
    request_id = int(call.data.split('_')[2])
    
    # Get user_id for notification
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM startup_members WHERE id = ?', (request_id,))
    result = cursor.fetchone()
    
    if not result:
        bot.answer_callback_query(call.id, "❌ So'rov topilmadi!", show_alert=True)
        conn.close()
        return
    
    user_id = result[0]
    update_join_request(request_id, 'rejected')
    
    # Notify user
    try:
        bot.send_message(user_id, "❌ <b>So'rovingiz rad etildi.</b>")
    except:
        pass
    
    try:
        bot.edit_message_text(
            "❌ <b>So'rov rad etildi.</b>",
            call.message.chat.id,
            call.message.message_id
        )
    except:
        bot.send_message(call.message.chat.id, "❌ <b>So'rov rad etildi.</b>")
    
    conn.close()
    bot.answer_callback_query(call.id)

# ==================== MENING STARTUPLARIM ====================
@bot.message_handler(func=lambda message: message.text == '📌 Mening startuplarim')
def show_my_startups(message):
    show_my_startups_page(message.chat.id, message.from_user.id, 1)

def show_my_startups_page(chat_id, user_id, page):
    startups = get_startups_by_owner(user_id)
    
    if not startups:
        bot.send_message(chat_id, "📭 <b>Sizda hali startup mavjud emas.</b>")
        return
    
    per_page = 5
    total = len(startups)
    total_pages = (total + per_page - 1) // per_page
    page = min(max(1, page), total_pages)
    
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total)
    page_startups = startups[start_idx:end_idx]
    
    text = f"<b>📌 Mening startuplarim</b>\n📄 Sahifa: <b>{page}/{total_pages}</b>\n\n"
    for i, startup in enumerate(page_startups, start=start_idx + 1):
        status_emoji = {
            'pending': '⏳',
            'active': '▶️',
            'completed': '✅',
            'rejected': '❌'
        }.get(startup['status'], '❓')
        text += f"{i}. {startup['name']} {status_emoji}\n"
    
    markup = InlineKeyboardMarkup(row_width=5)
    
    # Page numbers
    buttons = []
    for i in range(1, min(6, total_pages + 1)):
        buttons.append(InlineKeyboardButton(str(i), callback_data=f'my_startup_page_{i}'))
    if buttons:
        markup.row(*buttons)
    
    # Navigation
    if page > 1:
        markup.add(InlineKeyboardButton('⏮️ Oldingi', callback_data=f'my_startup_page_{page-1}'))
    if page < total_pages:
        markup.add(InlineKeyboardButton('⏭️ Keyingi', callback_data=f'my_startup_page_{page+1}'))
    
    # Startup selection
    if page_startups:
        for i, startup in enumerate(page_startups):
            markup.add(InlineKeyboardButton(f'{start_idx + i + 1}. {startup["name"][:15]}...', 
                                           callback_data=f'view_startup_{startup["startup_id"]}'))
    
    markup.add(InlineKeyboardButton('🔙 Asosiy menyu', callback_data='main_menu'))
    
    bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('my_startup_page_'))
def handle_my_startup_page(call):
    page = int(call.data.split('_')[3])
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_my_startups_page(call.message.chat.id, call.from_user.id, page)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_startup_'))
def view_startup_details(call):
    startup_id = int(call.data.split('_')[2])
    startup = get_startup(startup_id)
    
    if not startup:
        bot.answer_callback_query(call.id, "❌ Startup topilmadi!", show_alert=True)
        return
    
    user = get_user(startup['owner_id'])
    owner_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() if user else "Noma'lum"
    
    # Get member count
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM startup_members WHERE startup_id = ? AND status = "accepted"', (startup_id,))
    member_count = cursor.fetchone()[0]
    conn.close()
    
    status_texts = {
        'pending': '⏳ Kutilmoqda',
        'active': '▶️ Boshlangan',
        'completed': '✅ Yakunlangan',
        'rejected': '❌ Rad etilgan'
    }
    
    status_text = status_texts.get(startup['status'], startup['status'])
    
    start_date = startup.get('started_at', '—')
    if start_date and start_date != '—':
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S').strftime('%d-%m-%Y')
        except:
            pass
    
    text = (
        f"🎯 <b>Nomi:</b> {startup['name']}\n"
        f"📊 <b>Holati:</b> {status_text}\n"
        f"📅 <b>Boshlanish sanasi:</b> {start_date}\n"
        f"👤 <b>Muallif:</b> {owner_name}\n"
        f"👥 <b>A'zolar:</b> {member_count} ta\n"
        f"📌 <b>Tavsif:</b> {startup['description']}"
    )
    
    markup = InlineKeyboardMarkup()
    
    if startup['status'] == 'pending':
        markup.add(InlineKeyboardButton('⏳ Admin tasdigini kutyapti', callback_data='waiting_approval'))
    elif startup['status'] == 'active':
        markup.add(InlineKeyboardButton('👥 A\'zolar', callback_data=f'view_members_{startup_id}_1'))
        markup.add(InlineKeyboardButton('⏹️ Yakunlash', callback_data=f'complete_startup_{startup_id}'))
    elif startup['status'] == 'completed':
        markup.add(InlineKeyboardButton('👥 A\'zolar', callback_data=f'view_members_{startup_id}_1'))
        if startup.get('results'):
            markup.add(InlineKeyboardButton('📊 Natijalar', callback_data=f'view_results_{startup_id}'))
    elif startup['status'] == 'rejected':
        markup.add(InlineKeyboardButton('❌ Rad etilgan', callback_data='rejected_info'))
    
    markup.add(InlineKeyboardButton('🔙 Orqaga', callback_data='back_to_my_startups'))
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    if startup.get('logo'):
        bot.send_photo(call.message.chat.id, startup['logo'], caption=text, reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, text, reply_markup=markup)
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_my_startups')
def back_to_my_startups(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_my_startups_page(call.message.chat.id, call.from_user.id, 1)
    bot.answer_callback_query(call.id)

# ==================== STARTUP YARATISH ====================
@bot.message_handler(func=lambda message: message.text == '➕ Startup yaratish')
def start_creation(message):
    msg = bot.send_message(message.chat.id, "🚀 <b>Yangi startup yaratamiz!</b>\n\n📝 <b>Startup nomini kiriting:</b>")
    bot.register_next_step_handler(msg, process_startup_name, {'owner_id': message.from_user.id})

def process_startup_name(message, data):
    data['name'] = message.text
    msg = bot.send_message(message.chat.id, "📝 <b>Startup tavsifini kiriting:</b>")
    bot.register_next_step_handler(msg, process_startup_description, data)

def process_startup_description(message, data):
    data['description'] = message.text
    msg = bot.send_message(message.chat.id, "🖼 <b>Logo (rasm) yuboring:</b>")
    bot.register_next_step_handler(msg, process_startup_logo, data)

def process_startup_logo(message, data):
    if message.photo:
        data['logo'] = message.photo[-1].file_id
        msg = bot.send_message(message.chat.id, 
                              "🔗 <b>Guruh yoki kanal havolasini kiriting (majburiy):</b>\n\n"
                              "Masalan: <code>https://t.me/group_name</code>")
        bot.register_next_step_handler(msg, process_startup_group_link, data)
    else:
        msg = bot.send_message(message.chat.id, "⚠️ <b>Iltimos, rasm yuboring!</b>")
        bot.register_next_step_handler(msg, process_startup_logo, data)

def process_startup_group_link(message, data):
    data['group_link'] = message.text
    startup_id = create_startup(
        data['name'],
        data['description'],
        data['logo'],
        data['group_link'],
        data['owner_id']
    )
    
    # Send to admin for approval
    startup = get_startup(startup_id)
    user = get_user(data['owner_id'])
    owner_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() if user else "Noma'lum"
    
    text = (
        f"🆕 <b>Yangi startup yaratildi!</b>\n\n"
        f"🎯 <b>Nomi:</b> {startup['name']}\n"
        f"📌 <b>Tavsif:</b> {startup['description'][:200]}...\n"
        f"👤 <b>Muallif:</b> {owner_name}\n"
        f"👤 <b>Muallif ID:</b> {data['owner_id']}"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton('✅ Tasdiqlash', callback_data=f'admin_approve_{startup_id}'),
        InlineKeyboardButton('❌ Rad etish', callback_data=f'admin_reject_{startup_id}')
    )
    
    try:
        if startup.get('logo'):
            bot.send_photo(ADMIN_ID, startup['logo'], caption=text, reply_markup=markup)
        else:
            bot.send_message(ADMIN_ID, text, reply_markup=markup)
    except Exception as e:
        logging.error(f"Admin notification error: {e}")
    
    bot.send_message(message.chat.id, 
                    "✅ <b>Startup yaratildi va tekshiruvga yuborildi!</b>\n\n"
                    "⏳ <i>Administrator tekshirgandan so'ng kanalga joylanadi.</i>")
    show_main_menu(message)

# ==================== ADMIN PANEL (TELEGRAM) ====================
@bot.message_handler(func=lambda message: message.text == '🛠 Admin panel' and message.chat.id == ADMIN_ID)
def admin_panel(message):
    stats = get_statistics()
    
    text = (
        f"👨‍💼 <b>Admin Panel</b>\n\n"
        f"📊 <b>Statistikalar:</b>\n"
        f"├ 👥 Foydalanuvchilar: <b>{stats['total_users']}</b>\n"
        f"├ 🚀 Startuplar: <b>{stats['total_startups']}</b>\n"
        f"├ ⏳ Kutilayotgan: <b>{stats['pending_startups']}</b>\n"
        f"├ ▶️ Faol: <b>{stats['active_startups']}</b>\n"
        f"├ ✅ Yakunlangan: <b>{stats['completed_startups']}</b>\n"
        f"└ 📨 So'rovlar: <b>{stats['pending_requests']}</b>\n\n"
        f"🌐 <b>Web Admin:</b> /admin_link"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton('⏳ Kutilayotgan startuplar', callback_data='pending_startups_1'),
        InlineKeyboardButton('📊 Statistika', callback_data='admin_stats'),
        InlineKeyboardButton('📢 Xabar yuborish', callback_data='admin_broadcast')
    )
    
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('pending_startups_'))
def show_pending_startups_admin(call):
    page = int(call.data.split('_')[2])
    startups, total = get_pending_startups(page)
    
    if not startups:
        text = "⏳ <b>Kutilayotgan startuplar yo'q.</b>"
        markup = InlineKeyboardMarkup()
    else:
        total_pages = max(1, (total + 9) // 10)
        text = f"⏳ <b>Kutilayotgan startuplar</b>\n📄 Sahifa: <b>{page}/{total_pages}</b>\n\n"
        
        for i, startup in enumerate(startups, start=(page-1)*10+1):
            text += f"{i}. <b>{startup['name']}</b>\n   👤 {startup['first_name']} {startup['last_name']}\n\n"
        
        markup = InlineKeyboardMarkup()
        
        # Page navigation
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton('⏮️', callback_data=f'pending_startups_{page-1}'))
        
        nav_buttons.append(InlineKeyboardButton(f'{page}/{total_pages}', callback_data='current_page'))
        
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton('⏭️', callback_data=f'pending_startups_{page+1}'))
        
        if nav_buttons:
            markup.row(*nav_buttons)
        
        # Startup selection
        for i, startup in enumerate(startups):
            markup.add(InlineKeyboardButton(f'{i+1}. {startup["name"][:20]}...', 
                                           callback_data=f'admin_view_startup_{startup["startup_id"]}'))
    
    markup.add(InlineKeyboardButton('🔙 Admin panel', callback_data='admin_back'))
    
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except:
        bot.send_message(call.message.chat.id, text, reply_markup=markup)
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_view_startup_'))
def admin_view_startup_details(call):
    startup_id = int(call.data.split('_')[3])
    startup = get_startup(startup_id)
    
    if not startup:
        bot.answer_callback_query(call.id, "❌ Startup topilmadi!", show_alert=True)
        return
    
    user = get_user(startup['owner_id'])
    owner_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() if user else "Noma'lum"
    
    text = (
        f"🖼 <b>Startup ma'lumotlari</b>\n\n"
        f"🎯 <b>Nomi:</b> {startup['name']}\n"
        f"📌 <b>Tavsif:</b> {startup['description']}\n\n"
        f"👤 <b>Muallif:</b> {owner_name}\n"
        f"🔗 <b>Guruh havolasi:</b> {startup['group_link']}\n"
        f"📅 <b>Yaratilgan sana:</b> {startup['created_at'][:10] if startup.get('created_at') else '—'}\n"
        f"📊 <b>Holati:</b> {startup['status']}"
    )
    
    markup = InlineKeyboardMarkup()
    
    if startup['status'] == 'pending':
        markup.add(
            InlineKeyboardButton('✅ Tasdiqlash', callback_data=f'admin_approve_{startup_id}'),
            InlineKeyboardButton('❌ Rad etish', callback_data=f'admin_reject_{startup_id}')
        )
    
    markup.add(InlineKeyboardButton('🔙 Orqaga', callback_data='pending_startups_1'))
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    if startup.get('logo'):
        bot.send_photo(call.message.chat.id, startup['logo'], caption=text, reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, text, reply_markup=markup)
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_approve_'))
def admin_approve_startup(call):
    startup_id = int(call.data.split('_')[2])
    update_startup_status(startup_id, 'active')
    
    # Notify owner
    startup = get_startup(startup_id)
    if startup:
        try:
            bot.send_message(
                startup['owner_id'],
                f"🎉 <b>Tabriklaymiz!</b>\n\n"
                f"✅ Sizning '<b>{startup['name']}</b>' startupingiz tasdiqlandi va kanalga joylandi!"
            )
        except:
            pass
    
    # Post to channel
    try:
        user = get_user(startup['owner_id'])
        owner_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() if user else "Noma'lum"
        
        channel_text = (
            f"🎯 <b>Nomi:</b> {startup['name']}\n"
            f"📝 <b>Tavsif:</b> {startup['description']}\n\n"
            f"👤 <b>Muallif:</b> {owner_name}\n\n"
            f"👉 <b>Startupga qo'shilish uchun @GarajHub_bot orqali ro'yxatdan o'ting</b>\n"
            f"👉 <b>O'z startupingizni @GarajHub_bot orqali yarating</b>"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton('🤝 Startupga qo\'shilish', 
                                       url=f'https://t.me/{bot.get_me().username}?start=join_{startup_id}'))
        
        if startup.get('logo'):
            bot.send_photo(CHANNEL_USERNAME, startup['logo'], caption=channel_text, reply_markup=markup)
        else:
            bot.send_message(CHANNEL_USERNAME, channel_text, reply_markup=markup)
    except Exception as e:
        logging.error(f"Channel post error: {e}")
    
    bot.answer_callback_query(call.id, "✅ Startup tasdiqlandi!")
    show_pending_startups_admin(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_reject_'))
def admin_reject_startup(call):
    startup_id = int(call.data.split('_')[2])
    update_startup_status(startup_id, 'rejected')
    
    # Notify owner
    startup = get_startup(startup_id)
    if startup:
        try:
            bot.send_message(
                startup['owner_id'],
                f"❌ <b>Xabar!</b>\n\n"
                f"Sizning '<b>{startup['name']}</b>' startupingiz rad etildi."
            )
        except:
            pass
    
    bot.answer_callback_query(call.id, "❌ Startup rad etildi!")
    show_pending_startups_admin(call)

# ==================== WEB ADMIN PANEL ====================
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user_id = data.get('user_id')
    token = data.get('token')
    
    # Check if user is admin
    user = get_user(int(user_id)) if user_id.isdigit() else None
    if not user or not user.get('is_admin'):
        return jsonify({'success': False, 'message': 'Admin emas'})
    
    # Create session
    session_id = create_web_session(int(user_id))
    return jsonify({'success': True, 'session_id': session_id})

@app.route('/admin')
def admin_dashboard():
    session_id = request.cookies.get('session_id')
    user_id = validate_web_session(session_id) if session_id else None
    
    if not user_id:
        return redirect(url_for('login'))
    
    stats = get_statistics()
    recent_users = get_recent_users(5)
    recent_startups = get_recent_startups(5)
    
    return render_template('dashboard.html', 
                         stats=stats,
                         recent_users=recent_users,
                         recent_startups=recent_startups)

@app.route('/api/stats')
def api_stats():
    session_id = request.cookies.get('session_id')
    if not validate_web_session(session_id):
        return jsonify({'error': 'Unauthorized'}), 401
    
    stats = get_statistics()
    return jsonify(stats)

@app.route('/api/startups')
def api_startups():
    session_id = request.cookies.get('session_id')
    if not validate_web_session(session_id):
        return jsonify({'error': 'Unauthorized'}), 401
    
    status = request.args.get('status', 'all')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if status == 'all':
        cursor.execute('SELECT COUNT(*) as count FROM startups')
        total = cursor.fetchone()['count']
        
        offset = (page - 1) * per_page
        cursor.execute('''
            SELECT s.*, u.first_name, u.last_name, u.username 
            FROM startups s 
            JOIN users u ON s.owner_id = u.user_id 
            ORDER BY s.created_at DESC 
            LIMIT ? OFFSET ?
        ''', (per_page, offset))
    else:
        cursor.execute('SELECT COUNT(*) as count FROM startups WHERE status = ?', (status,))
        total = cursor.fetchone()['count']
        
        offset = (page - 1) * per_page
        cursor.execute('''
            SELECT s.*, u.first_name, u.last_name, u.username 
            FROM startups s 
            JOIN users u ON s.owner_id = u.user_id 
            WHERE s.status = ?
            ORDER BY s.created_at DESC 
            LIMIT ? OFFSET ?
        ''', (status, per_page, offset))
    
    startups = cursor.fetchall()
    conn.close()
    
    result = {
        'data': [dict(s) for s in startups],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    }
    
    return jsonify(result)

@app.route('/api/users')
def api_users():
    session_id = request.cookies.get('session_id')
    if not validate_web_session(session_id):
        return jsonify({'error': 'Unauthorized'}), 401
    
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    
    conn = sqlite3.connect('garajhub.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as count FROM users')
    total = cursor.fetchone()['count']
    
    offset = (page - 1) * per_page
    cursor.execute('SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?', (per_page, offset))
    users = cursor.fetchall()
    conn.close()
    
    result = {
        'data': [dict(u) for u in users],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    }
    
    return jsonify(result)

@app.route('/api/broadcast', methods=['POST'])
def api_broadcast():
    session_id = request.cookies.get('session_id')
    if not validate_web_session(session_id):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    message = data.get('message')
    
    if not message:
        return jsonify({'success': False, 'message': 'Xabar bo\'sh'})
    
    users = get_all_users()
    success = 0
    fail = 0
    
    for user_id in users:
        try:
            bot.send_message(user_id, f"📢 <b>Yangilik!</b>\n\n{message}")
            success += 1
        except:
            fail += 1
    
    return jsonify({
        'success': True,
        'sent': success,
        'failed': fail,
        'total': len(users)
    })

@app.route('/api/startup/<int:startup_id>/approve', methods=['POST'])
def api_approve_startup(startup_id):
    session_id = request.cookies.get('session_id')
    if not validate_web_session(session_id):
        return jsonify({'error': 'Unauthorized'}), 401
    
    update_startup_status(startup_id, 'active')
    
    # Notify owner
    startup = get_startup(startup_id)
    if startup:
        try:
            bot.send_message(
                startup['owner_id'],
                f"🎉 <b>Tabriklaymiz!</b>\n\n"
                f"✅ Sizning '<b>{startup['name']}</b>' startupingiz tasdiqlandi!"
            )
        except:
            pass
    
    return jsonify({'success': True})

@app.route('/api/startup/<int:startup_id>/reject', methods=['POST'])
def api_reject_startup(startup_id):
    session_id = request.cookies.get('session_id')
    if not validate_web_session(session_id):
        return jsonify({'error': 'Unauthorized'}), 401
    
    update_startup_status(startup_id, 'rejected')
    
    # Notify owner
    startup = get_startup(startup_id)
    if startup:
        try:
            bot.send_message(
                startup['owner_id'],
                f"❌ <b>Xabar!</b>\n\n"
                f"Sizning '<b>{startup['name']}</b>' startupingiz rad etildi."
            )
        except:
            pass
    
    return jsonify({'success': True})

# ==================== TEMPLATES ====================
@app.route('/templates/<path:filename>')
def serve_template(filename):
    return send_from_directory('templates', filename)

# ==================== BOSHQA HANDLERLAR ====================
@bot.message_handler(commands=['admin_link'])
def send_admin_link(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(
            message.chat.id,
            f"🌐 <b>Web Admin Panel:</b>\n\n"
            f"🔗 <code>http://localhost:{WEB_PORT}/admin</code>\n\n"
            f"🆔 <b>Admin ID:</b> <code>{ADMIN_ID}</code>"
        )
    else:
        bot.send_message(message.chat.id, "❌ Ruxsat yo'q!")

@bot.callback_query_handler(func=lambda call: call.data in ['main_menu', 'admin_back', 'waiting_approval', 
                                                          'rejected_info', 'admin_stats', 'admin_broadcast'])
def handle_common_callbacks(call):
    if call.data == 'main_menu':
        show_main_menu(call)
    elif call.data == 'admin_back':
        admin_panel(call.message)
    elif call.data in ['waiting_approval', 'rejected_info']:
        bot.answer_callback_query(call.id, "Ma'lumot ko'rsatilmoqda...")
    elif call.data == 'admin_stats':
        stats = get_statistics()
        text = (
            f"📊 <b>Statistikalar:</b>\n\n"
            f"👥 Foydalanuvchilar: <b>{stats['total_users']}</b>\n"
            f"🚀 Startuplar: <b>{stats['total_startups']}</b>\n"
            f"⏳ Kutilayotgan: <b>{stats['pending_startups']}</b>\n"
            f"▶️ Faol: <b>{stats['active_startups']}</b>\n"
            f"✅ Yakunlangan: <b>{stats['completed_startups']}</b>\n"
            f"📨 So'rovlar: <b>{stats['pending_requests']}</b>"
        )
        bot.answer_callback_query(call.id, text, show_alert=True)
    elif call.data == 'admin_broadcast':
        msg = bot.send_message(call.message.chat.id, "📢 <b>Xabaringizni yozing:</b>")
        bot.register_next_step_handler(msg, process_admin_broadcast)

def process_admin_broadcast(message):
    text = message.text
    users = get_all_users()
    
    bot.send_message(message.chat.id, f"📤 <b>Xabar yuborilmoqda...</b>")
    
    success = 0
    fail = 0
    
    for user_id in users:
        try:
            bot.send_message(user_id, f"📢 <b>Yangilik!</b>\n\n{text}")
            success += 1
        except:
            fail += 1
    
    bot.send_message(
        message.chat.id,
        f"✅ <b>Xabar yuborish yakunlandi!</b>\n\n"
        f"✅ Yuborildi: {success} ta\n"
        f"❌ Yuborilmadi: {fail} ta"
    )

# ==================== ISHGA TUSHIRISH ====================
def run_bot():
    print("=" * 60)
    print("🚀 GarajHub Bot ishga tushdi...")
    print(f"👨‍💼 Admin ID: {ADMIN_ID}")
    print(f"📢 Kanal: {CHANNEL_USERNAME}")
    print(f"🤖 Bot: @{bot.get_me().username}")
    print("=" * 60)
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logging.error(f"Bot error: {e}")
        print("Bot restarting...")

def run_web():
    print(f"🌐 Web Admin Panel: http://localhost:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)

if __name__ == '__main__':
    init_db()
    
    # Start bot and web in separate threads
    bot_thread = threading.Thread(target=run_bot)
    web_thread = threading.Thread(target=run_web)
    
    bot_thread.start()
    web_thread.start()
    
    bot_thread.join()
    web_thread.join()