import os
import sqlite3
import logging
import asyncio
from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configuración de Logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- DATOS CONFIGURADOS ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8911010643:AAFg6p4MYFH9ipyHNz0KxafCZE-gNCy6Suk")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5962089466"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

# --- INICIALIZACIÓN DE BASE DE DATOS (SQLITE) ---
def init_db():
    conn = sqlite3.connect("bot_sports.db")
    cursor = conn.cursor()
    
    # Tabla de Usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            lang TEXT DEFAULT 'es',
            is_subscribed INTEGER DEFAULT 0
        )
    ''')
    
    # Tabla de Ligas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leagues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    
    # Tabla de Partidos y Pronósticos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER,
            title TEXT,
            prediction TEXT,
            FOREIGN KEY(league_id) REFERENCES leagues(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

ADMIN_STATES = {}

# --- COMANDO /START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect("bot_sports.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, lang, is_subscribed) VALUES (?, 'es', 0)", (user_id,))
    conn.commit()
    conn.close()

    keyboard = [
        [
            InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es"),
            InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"),
            InlineKeyboardButton("Português 🇵🇹", callback_data="lang_pt"),
        ]
    ]
    await update.message.reply_text("🌐 Selecciona tu idioma / Select your language:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- COMANDO /ADMIN ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Acceso denegado. Este comando es exclusivo para el administrador.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Agregar Liga", callback_data="admin_add_league")],
        [InlineKeyboardButton("⚽ Agregar Partido y Pronóstico", callback_data="admin_add_match")]
    ]
    await update.message.reply_text("🛠️ **Panel de Administrador**\n¿Qué deseas hacer?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- MANEJADOR DE BOTONES ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    conn = sqlite3.connect("bot_sports.db")
    cursor = conn.cursor()

    if data.startswith("lang_"):
        lang = data.split("_")[1]
        cursor.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()
        await show_main_screen(query, user_id, cursor)

    elif data.startswith("pay_"):
        plan = data.split("_")[1]
        keyboard = [[InlineKeyboardButton("✅ Confirmar Pago (Simulación)", callback_data=f"confirm_pay_{plan}")]]
        await query.edit_message_text(f"💳 **Instrucciones de Pago Binance Pay**\n\nPlan seleccionado: {plan}\nTransfiere a Binance ID: 123456789\n\nPresiona abajo tras enviar:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("confirm_pay_"):
        cursor.execute("UPDATE users SET is_subscribed = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        await query.edit_message_text("🎉 ¡Pago confirmado con éxito! Ahora tienes acceso VIP.")
        await show_leagues_screen(query, user_id, cursor)

    elif data == "show_leagues":
        await show_leagues_screen(query, user_id, cursor)

    elif data.startswith("view_league_"):
        league_id = int(data.split("_")[2])
        cursor.execute("SELECT id, title FROM matches WHERE league_id = ?", (league_id,))
        matches = cursor.fetchall()
        
        keyboard = []
        for m in matches:
            keyboard.append([InlineKeyboardButton(m[1], callback_data=f"view_match_{m[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Volver a Ligas", callback_data="show_leagues")])
        
        await query.edit_message_text("⚽ **Partidos Disponibles:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("view_match_"):
        match_id = int(data.split("_")[2])
        cursor.execute("SELECT title, prediction FROM matches WHERE id = ?", (match_id,))
        match = cursor.fetchone()
        
        keyboard = [[InlineKeyboardButton("🔙 Volver a Ligas", callback_data="show_leagues")]]
        await query.edit_message_text(f"📌 **{match[0]}**\n\n{match[1]}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_add_league":
        ADMIN_STATES[user_id] = "WAITING_LEAGUE_NAME"
        await query.edit_message_text("📝 Escribe el nombre de la nueva Liga (Ej: NBA, Premier League):")

    elif data == "admin_add_match":
        cursor.execute("SELECT id, name FROM leagues")
        leagues = cursor.fetchall()
        if not leagues:
            await query.edit_message_text("⚠️ Primero debes crear al menos una liga.")
        else:
            keyboard = [[InlineKeyboardButton(l[1], callback_data=f"admin_select_league_{l[0]}")] for l in leagues]
            await query.edit_message_text("Selecciona la liga para el nuevo partido:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("admin_select_league_"):
        league_id = int(data.split("_")[3])
        ADMIN_STATES[user_id] = f"WAITING_MATCH_TITLE_{league_id}"
        await query.edit_message_text("⚽ Escribe el nombre del partido (Ej: Lakers vs Celtics):")

    conn.close()

# --- MANEJADOR DE TEXTO (ADMIN) ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id in ADMIN_STATES:
        state = ADMIN_STATES[user_id]
        conn = sqlite3.connect("bot_sports.db")
        cursor = conn.cursor()

        if state == "WAITING_LEAGUE_NAME":
            cursor.execute("INSERT INTO leagues (name) VALUES (?)", (text,))
            conn.commit()
            del ADMIN_STATES[user_id]
            await update.message.reply_text(f"✅ Liga **{text}** creada exitosamente. Usa /admin para continuar.", parse_mode="Markdown")

        elif state.startswith("WAITING_MATCH_TITLE_"):
            league_id = int(state.split("_")[3])
            ADMIN_STATES[user_id] = f"WAITING_MATCH_PRED_{league_id}_{text}"
            await update.message.reply_text("✍️ Ahora pega el **Pronóstico** de tu IA:")

        elif state.startswith("WAITING_MATCH_PRED_"):
            parts = state.split("_")
            league_id = int(parts[3])
            match_title = parts[4]
            
            cursor.execute("INSERT INTO matches (league_id, title, prediction) VALUES (?, ?, ?)", (league_id, match_title, text))
            conn.commit()
            del ADMIN_STATES[user_id]
            await update.message.reply_text(f"🚀 ¡Partido y Pronóstico para **{match_title}** guardados con éxito!", parse_mode="Markdown")

        conn.close()

async def show_main_screen(query, user_id, cursor):
    cursor.execute("SELECT lang, is_subscribed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    is_sub = row[1] if row else 0

    text = "👋 ¡Bienvenido a **SportsPicks VIP**!\n\nPlanes de Suscripción:\n• 1 Mes: $20 USDT\n• 2 Meses: $35 USDT\n• 6 Meses: $100 USDT"
    keyboard = [
        [InlineKeyboardButton("1 Mes ($20 USDT)", callback_data="pay_1m")],
        [InlineKeyboardButton("2 Meses ($35 USDT)", callback_data="pay_2m")],
        [InlineKeyboardButton("6 Meses ($100 USDT)", callback_data="pay_6m")],
    ]
    if is_sub:
        keyboard.append([InlineKeyboardButton("🚀 Ver Pronósticos VIP", callback_data="show_leagues")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_leagues_screen(query, user_id, cursor):
    cursor.execute("SELECT is_subscribed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row or row[0] == 0:
        await query.edit_message_text("⚠️ Necesitas una suscripción activa para ver esta sección.")
        return

    cursor.execute("SELECT id, name FROM leagues")
    leagues = cursor.fetchall()
    
    if not leagues:
        await query.edit_message_text("🏆 No hay ligas disponibles por el momento.")
        return

    keyboard = [[InlineKeyboardButton(l[1], callback_data=f"view_league_{l[0]}")] for l in leagues]
    await query.edit_message_text("🏆 **Ligas Disponibles:**\nSelecciona una para consultar los partidos:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- CONSTRUCCIÓN DE LA APLICACIÓN TELEGRAM ---
ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("admin", admin_panel))
ptb_app.add_handler(CallbackQueryHandler(button_handler))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

# --- RUTAS DE AIOHTTP PARA RENDER ---
async def health_check(request):
    return web.Response(text="Bot activo y saludable")

async def telegram_webhook(request):
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return web.Response(text="ok")

async def main():
    await ptb_app.initialize()
    await ptb_app.start()
    
    # Configurar Webhook si existe la URL de Render
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}"
        await ptb_app.bot.set_webhook(url=webhook_url)
        logging.info(f"Webhook registrado en: {webhook_url}")

    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_post(f"/{BOT_TOKEN}", telegram_webhook)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Servidor aiohttp escuchando en puerto {port}")

    # Mantener corriendo el evento principal
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
