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

# --- CONFIGURACIÓN PRINCIPAL ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8911010643:AAFg6p4MYFH9ipyHNz0KxafCZE-gNCy6Suk")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5962089466"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

# --- DATOS REALES DE BINANCE PAY ---
BINANCE_PAY_ID = "735205094"
BINANCE_PAY_EMAIL = "cadizsantiago8@gmail.com"
# URL directa de tu imagen QR de Binance
BINANCE_QR_URL = "https://raw.githubusercontent.com/SantiagoCadiz/imagenes/main/binance_qr.jpg"  # Se enviará la info clara en texto y foto

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
            FOREIGN KEY(league_id) REFERENCES leagues(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

init_db()

ADMIN_STATES = {}
USER_PAYMENT_STATES = {}

# --- COMANDO /START (CLIENTES) ---
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

# --- COMANDO /ADMIN (SOLO PARA TI) ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Acceso denegado. Este comando es exclusivo para el administrador.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Agregar Liga", callback_data="admin_add_league"), InlineKeyboardButton("🗑️ Eliminar Liga", callback_data="admin_del_league")],
        [InlineKeyboardButton("⚽ Agregar Partido/Pronóstico", callback_data="admin_add_match"), InlineKeyboardButton("❌ Borrar Partido", callback_data="admin_del_match")],
        [InlineKeyboardButton("👥 Activar Suscripción Manual", callback_data="admin_activate_user")],
        [InlineKeyboardButton("📋 Ver Todo lo Cargado", callback_data="admin_list_all")]
    ]
    await update.message.reply_text("🛠️ **Panel de Administrador (Gestión de Base de Datos)**\n\n¿Qué acción deseas realizar?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- MANEJADOR DE BOTONES ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    conn = sqlite3.connect("bot_sports.db")
    cursor = conn.cursor()

    # CAMBIO DE IDIOMA
    if data.startswith("lang_"):
        lang = data.split("_")[1]
        cursor.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
        conn.commit()
        await show_main_screen(query, user_id, cursor)

    # MOSTRAR DATOS DE PAGO BINANCE
    elif data.startswith("pay_"):
        plan = data.split("_")[1]
        precios = {"1m": "$20 USDT", "2m": "$35 USDT", "6m": "$100 USDT"}
        monto = precios.get(plan, "$20 USDT")
        USER_PAYMENT_STATES[user_id] = plan
        
        texto_pago = (
            f"💳 **INSTRUCCIONES DE PAGO BINANCE PAY**\n\n"
            f"📌 **Plan Seleccionado:** {monto}\n\n"
            f"Para realizar tu pago de forma segura:\n"
            f"• **Binance Pay ID:** `{BINANCE_PAY_ID}`\n"
            f"• **Correo Binance:** `{BINANCE_PAY_EMAIL}`\n\n"
            f"📸 **Siguiente paso:**\n"
            f"Realiza el pago desde tu app de Binance y **envía por aquí la captura de pantalla (comprobante)**.\n\n"
            f"⏳ Una vez enviado el comprobante, **tu aprobación de pago será verificada y aprobada en menos de 24 horas**."
        )
        keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="show_main")]]
        
        await query.message.delete()
        await context.bot.send_message(
            chat_id=user_id,
            text=texto_pago,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "show_main":
        await show_main_screen(query, user_id, cursor)

    elif data == "show_leagues":
        await show_leagues_screen(query, user_id, cursor)

    # VISTA CLIENTE: CONSULTAR LIGAS Y PARTIDOS
    elif data.startswith("view_league_"):
        league_id = int(data.split("_")[2])
        cursor.execute("SELECT id, title FROM matches WHERE league_id = ?", (league_id,))
        matches = cursor.fetchall()
        
        keyboard = []
        for m in matches:
            keyboard.append([InlineKeyboardButton(m[1], callback_data=f"view_match_{m[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Volver a Ligas", callback_data="show_leagues")])
        
        await query.edit_message_text("⚽ **Partidos y Pronósticos Disponibles:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("view_match_"):
        match_id = int(data.split("_")[2])
        cursor.execute("SELECT title, prediction FROM matches WHERE id = ?", (match_id,))
        match = cursor.fetchone()
        
        keyboard = [[InlineKeyboardButton("🔙 Volver a Ligas", callback_data="show_leagues")]]
        if match:
            await query.edit_message_text(f"📌 **{match[0]}**\n\n{match[1]}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await query.edit_message_text("⚠️ El pronóstico ya no está disponible.", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- ACCIONES ADMINISTRATIVAS ---
    elif data == "admin_add_league":
        ADMIN_STATES[user_id] = "WAITING_LEAGUE_NAME"
        await query.edit_message_text("📝 Escribe el nombre de la nueva Liga (Ej: NBA, Premier League):")

    elif data == "admin_del_league":
        cursor.execute("SELECT id, name FROM leagues")
        leagues = cursor.fetchall()
        if not leagues:
            await query.edit_message_text("⚠️ No hay ligas registradas para eliminar.")
        else:
            keyboard = [[InlineKeyboardButton(f"❌ {l[1]}", callback_data=f"confirm_del_league_{l[0]}")] for l in leagues]
            keyboard.append([InlineKeyboardButton("🔙 Cancelar", callback_data="admin_back")])
            await query.edit_message_text("Selecciona la liga que deseas **eliminar** (se borrarán todos sus partidos):", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("confirm_del_league_"):
        league_id = int(data.split("_")[3])
        cursor.execute("DELETE FROM leagues WHERE id = ?", (league_id,))
        cursor.execute("DELETE FROM matches WHERE league_id = ?", (league_id,))
        conn.commit()
        await query.edit_message_text("🗑️ Liga y sus partidos eliminados con éxito. Usa /admin para continuar.")

    elif data == "admin_add_match":
        cursor.execute("SELECT id, name FROM leagues")
        leagues = cursor.fetchall()
        if not leagues:
            await query.edit_message_text("⚠️ Primero debes crear al menos una liga.")
        else:
            keyboard = [[InlineKeyboardButton(l[1], callback_data=f"admin_select_league_{l[0]}")] for l in leagues]
            await query.edit_message_text("Selecciona la liga donde publicarás el pronóstico:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("admin_select_league_"):
        league_id = int(data.split("_")[3])
        ADMIN_STATES[user_id] = f"WAITING_MATCH_TITLE_{league_id}"
        await query.edit_message_text("⚽ Escribe el título del partido (Ej: Real Madrid vs Barcelona):")

    elif data == "admin_del_match":
        cursor.execute("SELECT matches.id, matches.title, leagues.name FROM matches JOIN leagues ON matches.league_id = leagues.id")
        matches = cursor.fetchall()
        if not matches:
            await query.edit_message_text("⚠️ No hay partidos cargados en la base de datos.")
        else:
            keyboard = [[InlineKeyboardButton(f"❌ [{m[2]}] {m[1]}", callback_data=f"confirm_del_match_{m[0]}")] for l in matches]
            keyboard.append([InlineKeyboardButton("🔙 Cancelar", callback_data="admin_back")])
            await query.edit_message_text("Selecciona el partido que deseas eliminar:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("confirm_del_match_"):
        match_id = int(data.split("_")[3])
        cursor.execute("DELETE FROM matches WHERE id = ?", (match_id,))
        conn.commit()
        await query.edit_message_text("🗑️ Partido eliminado con éxito. Usa /admin para continuar.")

    elif data == "admin_activate_user":
        ADMIN_STATES[user_id] = "WAITING_USER_ID_TO_ACTIVATE"
        await query.edit_message_text("👤 Escribe o pega el **ID de Telegram del cliente** al que deseas activarle el acceso VIP:")

    elif data.startswith("admin_quick_approve_"):
        target_id = int(data.split("_")[3])
        cursor.execute("INSERT INTO users (user_id, is_subscribed) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET is_subscribed = 1", (target_id,))
        conn.commit()
        await query.edit_message_text(f"✅ ¡Suscripción VIP activada con éxito para el usuario `{target_id}`!")
        
        # Notificar al cliente
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="🎉 **¡Tu pago ha sido verificado y tu suscripción VIP ha sido activada!**\n\nUsa /start para consultar los pronósticos disponibles."
            )
        except Exception as e:
            logging.error(f"Error al notificar cliente: {e}")

    elif data == "admin_list_all":
        cursor.execute("SELECT leagues.name, matches.title FROM leagues LEFT JOIN matches ON leagues.id = matches.league_id")
        rows = cursor.fetchall()
        if not rows:
            res = "ℹ️ La base de datos está completamente vacía."
        else:
            res = "📋 **ESTADO ACTUAL DE LA BASE DE DATOS:**\n\n"
            for r in rows:
                partido = r[1] if r[1] else "(Sin partidos)"
                res += f"• **{r[0]}**: {partido}\n"
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="admin_back")]]
        await query.edit_message_text(res, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_back":
        keyboard = [
            [InlineKeyboardButton("➕ Agregar Liga", callback_data="admin_add_league"), InlineKeyboardButton("🗑️ Eliminar Liga", callback_data="admin_del_league")],
            [InlineKeyboardButton("⚽ Agregar Partido/Pronóstico", callback_data="admin_add_match"), InlineKeyboardButton("❌ Borrar Partido", callback_data="admin_del_match")],
            [InlineKeyboardButton("👥 Activar Suscripción Manual", callback_data="admin_activate_user")],
            [InlineKeyboardButton("📋 Ver Todo lo Cargado", callback_data="admin_list_all")]
        ]
        await query.edit_message_text("🛠️ **Panel de Administrador**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    conn.close()

# --- MANEJADOR DE FOTOS (RECEPCIÓN DE COMPROBANTES DE PAGO) ---
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo = update.message.photo[-1]  # Toma la mayor resolución de la foto
    
    # Respuesta automática al cliente
    await update.message.reply_text(
        "✅ **Comprobante de pago recibido.**\n\n"
        "Tu aprobación de pago será verificada y aprobada en menos de 24 horas. "
        "Te notificaremos por aquí tan pronto tu suscripción esté activa."
    )
    
    # Reenviar el comprobante de pago inmediatamente al Administrador
    plan = USER_PAYMENT_STATES.get(user_id, "No especificado")
    username = update.effective_user.username or "Sin username"
    
    caption_admin = (
        f"🚨 **NUEVO COMPROBANTE DE PAGO**\n\n"
        f"👤 **Cliente:** @{username}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"💳 **Plan Solicitado:** {plan}\n"
    )
    keyboard = [[InlineKeyboardButton("✅ Aprobar Suscripción Ahora", callback_data=f"admin_quick_approve_{user_id}")]]
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=caption_admin,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- MANEJADOR DE TEXTO (RESPUESTAS DEL ADMIN) ---
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
            await update.message.reply_text(f"✅ Liga **{text}** creada con éxito. Usa /admin para volver al menú.", parse_mode="Markdown")

        elif state.startswith("WAITING_MATCH_TITLE_"):
            league_id = int(state.split("_")[3])
            ADMIN_STATES[user_id] = f"WAITING_MATCH_PRED_{league_id}_{text}"
            await update.message.reply_text("✍️ Ahora pega el **Pronóstico completo** (análisis generado por tu IA):")

        elif state.startswith("WAITING_MATCH_PRED_"):
            parts = state.split("_")
            league_id = int(parts[3])
            match_title = parts[4]
            
            cursor.execute("INSERT INTO matches (league_id, title, prediction) VALUES (?, ?, ?)", (league_id, match_title, text))
            conn.commit()
            del ADMIN_STATES[user_id]
            await update.message.reply_text(f"🚀 ¡Pronóstico para **{match_title}** guardado exitosamente!", parse_mode="Markdown")

        elif state == "WAITING_USER_ID_TO_ACTIVATE":
            try:
                target_user_id = int(text.strip())
                cursor.execute("INSERT INTO users (user_id, is_subscribed) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET is_subscribed = 1", (target_user_id,))
                conn.commit()
                del ADMIN_STATES[user_id]
                await update.message.reply_text(f"🎉 ¡El usuario `{target_user_id}` ahora es **VIP Activo**!", parse_mode="Markdown")
            except ValueError:
                await update.message.reply_text("⚠️ El ID introducido no es válido. Debe ser solo números. Inténtalo de nuevo:")

        conn.close()

# --- PANTALLAS DE INTERFAZ ---
async def show_main_screen(query, user_id, cursor):
    cursor.execute("SELECT lang, is_subscribed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    is_sub = row[1] if row else 0

    text = (
        "👋 ¡Bienvenido a **SportsPicks VIP**!\n\n"
        "Accede a pronósticos deportivos de alta precisión automatizados por Inteligencia Artificial.\n\n"
        "💳 **Planes de Suscripción:**\n"
        "• 1 Mes: **$20 USDT**\n"
        "• 2 Meses: **$35 USDT**\n"
        "• 6 Meses: **$100 USDT**\n\n"
        "Selecciona un plan para ver los datos de pago vía Binance Pay:"
    )
    keyboard = [
        [InlineKeyboardButton("1 Mes ($20 USDT)", callback_data="pay_1m")],
        [InlineKeyboardButton("2 Meses ($35 USDT)", callback_data="pay_2m")],
        [InlineKeyboardButton("6 Meses ($100 USDT)", callback_data="pay_6m")],
    ]
    if is_sub:
        keyboard.append([InlineKeyboardButton("🚀 Ver Pronósticos VIP", callback_data="show_leagues")])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_leagues_screen(query, user_id, cursor):
    cursor.execute("SELECT is_subscribed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row or row[0] == 0:
        await query.edit_message_text("⚠️ Necesitas una suscripción activa para ver la sección VIP.")
        return

    cursor.execute("SELECT id, name FROM leagues")
    leagues = cursor.fetchall()
    
    if not leagues:
        await query.edit_message_text("🏆 No hay pronósticos cargados por el momento. Vuelve más tarde.")
        return

    keyboard = [[InlineKeyboardButton(l[1], callback_data=f"view_league_{l[0]}")] for l in leagues]
    await query.edit_message_text("🏆 **Ligas Disponibles:**\nSelecciona una para consultar los partidos:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- CONSTRUCCIÓN DE LA APLICACIÓN TELEGRAM ---
ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("admin", admin_panel))
ptb_app.add_handler(CallbackQueryHandler(button_handler))
ptb_app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
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

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
