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

# --- DATOS DEL BOT Y SUPERADMINISTRADOR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8911010643:AAFg6p4MYFH9ipyHNz0KxafCZE-gNCy6Suk")
SUPERADMIN_ID = int(os.environ.get("ADMIN_ID", "5962089466"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

# --- DATOS REALES DE BINANCE PAY ---
BINANCE_PAY_ID = "735205094"
BINANCE_PAY_EMAIL = "cadizsantiago8@gmail.com"
BINANCE_QR_URL = "https://i.ibb.co/68vN0v0/binance-qr.jpg"  # Enlace alojado de tu QR

# --- INICIALIZACIÓN DE BASE DE DATOS (SQLITE) ---
def init_db():
    conn = sqlite3.connect("bot_sports.db")
    cursor = conn.cursor()
    
    # Tabla de Usuarios (Suscripciones y Rol de Admin)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            is_subscribed INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    # Asegurar que el Creador sea SuperAdmin
    cursor.execute("INSERT INTO users (user_id, is_admin) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET is_admin = 1", (SUPERADMIN_ID,))
    
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

def is_user_admin(user_id):
    conn = sqlite3.connect("bot_sports.db")
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return (row and row[0] == 1) or user_id == SUPERADMIN_ID

# --- COMANDO /START (ENTRADA DIRECTA SIN IDIOMAS) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "SinUsername"
    
    conn = sqlite3.connect("bot_sports.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, username) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET username = ?",
        (user_id, username, username)
    )
    cursor.execute("SELECT is_subscribed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    is_sub = row[0] if row else 0
    conn.close()

    text = (
        "👋 ¡Bienvenido a **SportsPicks VIP**!\n\n"
        "Obtén los mejores pronósticos deportivos automatizados e impulsados por inteligencia artificial.\n\n"
        "💳 **Planes de Suscripción:**\n"
        "• 1 Mes: **$20 USDT**\n"
        "• 2 Meses: **$35 USDT**\n"
        "• 6 Meses: **$100 USDT**\n\n"
        "*(Nota: El bot a veces puede tardar unos segundos en responder)*\n\n"
        "Selecciona una opción abajo para ver las instrucciones y realizar tu pago vía Binance Pay:"
    )
    
    keyboard = [
        [InlineKeyboardButton("1 Mes ($20 USDT)", callback_data="pay_1m")],
        [InlineKeyboardButton("2 Meses ($35 USDT)", callback_data="pay_2m")],
        [InlineKeyboardButton("6 Meses ($100 USDT)", callback_data="pay_6m")],
    ]
    if is_sub:
        keyboard.append([InlineKeyboardButton("🚀 Ver Pronósticos VIP", callback_data="show_leagues")])

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- COMANDO /ADMIN ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_admin(user_id):
        await update.message.reply_text("⛔ Acceso denegado. Este comando es exclusivo para administradores.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Agregar Liga", callback_data="admin_add_league"), InlineKeyboardButton("🗑️ Eliminar Liga", callback_data="admin_del_league")],
        [InlineKeyboardButton("⚽ Cargar Pronóstico", callback_data="admin_add_match"), InlineKeyboardButton("❌ Borrar Pronóstico", callback_data="admin_del_match")],
        [InlineKeyboardButton("✅ Aprobar VIP", callback_data="admin_activate_user"), InlineKeyboardButton("🚫 Anular VIP", callback_data="admin_revoke_user")],
        [InlineKeyboardButton("👑 Agregar Nuevo Admin", callback_data="admin_add_admin")],
        [InlineKeyboardButton("📋 Ver Estado de la Base de Datos", callback_data="admin_list_all")]
    ]
    await update.message.reply_text("🛠️ **Panel de Control de Administrador**\n\n¿Qué acción deseas realizar?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- MANEJADOR DE BOTONES ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or "SinUsername"
    data = query.data

    conn = sqlite3.connect("bot_sports.db")
    cursor = conn.cursor()

    # VISTA DE PAGO BINANCE
    if data.startswith("pay_"):
        plan = data.split("_")[1]
        precios = {"1m": "$20 USDT (1 Mes)", "2m": "$35 USDT (2 Meses)", "6m": "$100 USDT (6 Meses)"}
        monto = precios.get(plan, "$20 USDT")
        
        texto_pago = (
            f"💳 **INSTRUCCIONES DE PAGO BINANCE PAY**\n\n"
            f"📌 **Plan Seleccionado:** {monto}\n\n"
            f"Escanéa el código QR arriba o utiliza los siguientes datos para realizar la transferencia:\n\n"
            f"🔹 **Binance Pay ID:** `{BINANCE_PAY_ID}`\n"
            f"🔹 **Correo de Binance:** `{BINANCE_PAY_EMAIL}`\n\n"
            f"📌 **Pasos finales:**\n"
            f"1. Realiza el pago exacto en **USDT**.\n"
            f"2. Haz una captura de pantalla del comprobante de pago.\n"
            f"3. Presiona el botón **'Ya envié el pago'** abajo para notificar al administrador.\n\n"
            f"*(Nota: El bot a veces puede tardar unos segundos en responder)*\n\n"
            f"⏳ *Tu aprobación de pago será verificada y activada en menos de 24 horas.*"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Ya envié el pago", callback_data=f"notify_admin_payment_{plan}")],
            [InlineKeyboardButton("🔙 Volver al Menú", callback_data="show_main")]
        ]
        
        try:
            await query.message.delete()
        except Exception:
            pass
            
        await context.bot.send_photo(
            chat_id=user_id,
            photo=BINANCE_QR_URL,
            caption=texto_pago,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data.startswith("notify_admin_payment_"):
        plan = data.split("_")[3]
        
        msg_cliente = (
            "📩 **¡Notificación Registrada!**\n\n"
            "Por favor envía en este chat la **captura del comprobante** de pago.\n"
            f"Tu ID de Usuario es: `{user_id}`\n\n"
            "⏳ Tu suscripción será verificada y activada en un plazo máximo de **24 horas**."
        )
        await query.message.reply_text(msg_cliente, parse_mode="Markdown")

        try:
            keyboard_admin = [
                [InlineKeyboardButton(f"⚡ Activar VIP a {user_id}", callback_data=f"auto_activate_{user_id}")],
                [InlineKeyboardButton(f"🚫 Anular VIP a {user_id}", callback_data=f"auto_revoke_{user_id}")]
            ]
            await context.bot.send_message(
                chat_id=SUPERADMIN_ID,
                text=f"🔔 **NUEVO REPORTE DE PAGO**\n\n"
                     f"👤 **Usuario:** @{username} (ID: `{user_id}`)\n"
                     f"📦 **Plan:** {plan}\n\n"
                     f"Revisa el pago en Binance y selecciona la acción:",
                reply_markup=InlineKeyboardMarkup(keyboard_admin),
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Error notificando al admin: {e}")

    elif data.startswith("auto_activate_"):
        target_id = int(data.split("_")[2])
        cursor.execute("UPDATE users SET is_subscribed = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        await query.edit_message_text(f"✅ ¡El usuario `{target_id}` ha sido activado como **VIP**!", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="🎉 **¡Tu pago ha sido verificado con éxito!**\n\nTu suscripción VIP ya está activa. Escribe /start para acceder a los pronósticos.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif data.startswith("auto_revoke_"):
        target_id = int(data.split("_")[2])
        cursor.execute("UPDATE users SET is_subscribed = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        await query.edit_message_text(f"🚫 La suscripción del usuario `{target_id}` ha sido **anulada/cancelada**.", parse_mode="Markdown")

    elif data == "show_main":
        await show_main_screen(query, user_id, cursor)

    elif data == "show_leagues":
        await show_leagues_screen(query, user_id, cursor)

    # AL SELECCIONAR UNA LIGA -> MUESTRA TODOS LOS PRONÓSTICOS DE ESA LIGA DE UNA VEZ
    elif data.startswith("view_league_"):
        league_id = int(data.split("_")[2])
        cursor.execute("SELECT name FROM leagues WHERE id = ?", (league_id,))
        league_row = cursor.fetchone()
        league_name = league_row[0] if league_row else "Liga"

        cursor.execute("SELECT title, prediction FROM matches WHERE league_id = ?", (league_id,))
        matches = cursor.fetchall()
        
        keyboard = [[InlineKeyboardButton("🔙 Volver a Ligas", callback_data="show_leagues")]]
        
        if not matches:
            texto = f"🏆 **{league_name}**\n\nNo hay pronósticos disponibles en esta liga por el momento."
        else:
            texto = f"🏆 **PRONÓSTICOS DISPONIBLES EN {league_name.upper()}**\n\n"
            for m in matches:
                texto += f"📌 **{m[0]}**\n{m[1]}\n───────────────────\n\n"
                
        await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # ACCIONES DEL PANEL ADMINISTRADOR
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
            await query.edit_message_text("Selecciona la liga que deseas **eliminar**:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("confirm_del_league_"):
        league_id = int(data.split("_")[3])
        cursor.execute("DELETE FROM leagues WHERE id = ?", (league_id,))
        cursor.execute("DELETE FROM matches WHERE league_id = ?", (league_id,))
        conn.commit()
        await query.edit_message_text("🗑️ Liga eliminada con éxito. Usa /admin para continuar.")

    elif data == "admin_add_match":
        cursor.execute("SELECT id, name FROM leagues")
        leagues = cursor.fetchall()
        if not leagues:
            await query.edit_message_text("⚠️ Primero debes crear al menos una liga.")
        else:
            keyboard = [[InlineKeyboardButton(l[1], callback_data=f"admin_select_league_{l[0]}")] for l in leagues]
            await query.edit_message_text("Selecciona la liga para el pronóstico:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("admin_select_league_"):
        league_id = int(data.split("_")[3])
        ADMIN_STATES[user_id] = f"WAITING_MATCH_TITLE_{league_id}"
        await query.edit_message_text("⚽ Escribe el título del partido (Ej: Real Madrid vs Barcelona):")

    elif data == "admin_del_match":
        cursor.execute("SELECT matches.id, matches.title, leagues.name FROM matches JOIN leagues ON matches.league_id = leagues.id")
        matches = cursor.fetchall()
        if not matches:
            await query.edit_message_text("⚠️ No hay pronósticos cargados.")
        else:
            keyboard = [[InlineKeyboardButton(f"❌ [{m[2]}] {m[1]}", callback_data=f"confirm_del_match_{m[0]}")] for m in matches]
            keyboard.append([InlineKeyboardButton("🔙 Cancelar", callback_data="admin_back")])
            await query.edit_message_text("Selecciona el pronóstico a eliminar:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("confirm_del_match_"):
        match_id = int(data.split("_")[3])
        cursor.execute("DELETE FROM matches WHERE id = ?", (match_id,))
        conn.commit()
        await query.edit_message_text("🗑️ Pronóstico eliminado de la base de datos. Usa /admin para continuar.")

    elif data == "admin_activate_user":
        ADMIN_STATES[user_id] = "WAITING_USER_ID_TO_ACTIVATE"
        await query.edit_message_text("👤 Escribe o pega el **ID de Telegram del cliente** a quien deseas APROBAR el VIP:")

    elif data == "admin_revoke_user":
        ADMIN_STATES[user_id] = "WAITING_USER_ID_TO_REVOKE"
        await query.edit_message_text("🚫 Escribe o pega el **ID de Telegram del cliente** a quien deseas ANULAR/CANCELAR el VIP:")

    elif data == "admin_add_admin":
        ADMIN_STATES[user_id] = "WAITING_NEW_ADMIN_ID"
        await query.edit_message_text("👑 Escribe o pega el **ID de Telegram** del usuario que deseas nombrar como ADMINISTRADOR:")

    elif data == "admin_list_all":
        cursor.execute("SELECT leagues.name, matches.title FROM leagues LEFT JOIN matches ON leagues.id = matches.league_id")
        rows = cursor.fetchall()
        if not rows:
            res = "ℹ️ La base de datos está vacía."
        else:
            res = "📋 **ESTADO DE LA BASE DE DATOS:**\n\n"
            for r in rows:
                partido = r[1] if r[1] else "(Sin pronósticos)"
                res += f"• **{r[0]}**: {partido}\n"
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="admin_back")]]
        await query.edit_message_text(res, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_back":
        keyboard = [
            [InlineKeyboardButton("➕ Agregar Liga", callback_data="admin_add_league"), InlineKeyboardButton("🗑️ Eliminar Liga", callback_data="admin_del_league")],
            [InlineKeyboardButton("⚽ Cargar Pronóstico", callback_data="admin_add_match"), InlineKeyboardButton("❌ Borrar Pronóstico", callback_data="admin_del_match")],
            [InlineKeyboardButton("✅ Aprobar VIP", callback_data="admin_activate_user"), InlineKeyboardButton("🚫 Anular VIP", callback_data="admin_revoke_user")],
            [InlineKeyboardButton("👑 Agregar Nuevo Admin", callback_data="admin_add_admin")],
            [InlineKeyboardButton("📋 Ver Estado de la Base de Datos", callback_data="admin_list_all")]
        ]
        await query.edit_message_text("🛠️ **Panel de Administrador**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    conn.close()

# --- MANEJADOR DE TEXTO ---
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
            await update.message.reply_text(f"✅ Liga **{text}** creada con éxito. Usa /admin para continuar.", parse_mode="Markdown")

        elif state.startswith("WAITING_MATCH_TITLE_"):
            league_id = int(state.split("_")[3])
            ADMIN_STATES[user_id] = f"WAITING_MATCH_PRED_{league_id}_{text}"
            await update.message.reply_text("✍️ Ahora pega el **Pronóstico completo**:")

        elif state.startswith("WAITING_MATCH_PRED_"):
            parts = state.split("_")
            league_id = int(parts[3])
            match_title = parts[4]
            
            cursor.execute("INSERT INTO matches (league_id, title, prediction) VALUES (?, ?, ?)", (league_id, match_title, text))
            conn.commit()
            del ADMIN_STATES[user_id]
            await update.message.reply_text(f"🚀 ¡Pronóstico para **{match_title}** guardado con éxito!", parse_mode="Markdown")

        elif state == "WAITING_USER_ID_TO_ACTIVATE":
            try:
                target_user_id = int(text.strip())
                cursor.execute("INSERT INTO users (user_id, is_subscribed) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET is_subscribed = 1", (target_user_id,))
                conn.commit()
                del ADMIN_STATES[user_id]
                await update.message.reply_text(f"🎉 ¡El usuario `{target_user_id}` ahora es **VIP Activo**!", parse_mode="Markdown")
            except ValueError:
                await update.message.reply_text("⚠️ ID inválido. Debe ser solo números. Inténtalo de nuevo:")

        elif state == "WAITING_USER_ID_TO_REVOKE":
            try:
                target_user_id = int(text.strip())
                cursor.execute("UPDATE users SET is_subscribed = 0 WHERE user_id = ?", (target_user_id,))
                conn.commit()
                del ADMIN_STATES[user_id]
                await update.message.reply_text(f"🚫 La suscripción VIP del usuario `{target_user_id}` ha sido **anulada/cancelada**.", parse_mode="Markdown")
            except ValueError:
                await update.message.reply_text("⚠️ ID inválido. Debe ser solo números. Inténtalo de nuevo:")

        elif state == "WAITING_NEW_ADMIN_ID":
            try:
                target_user_id = int(text.strip())
                cursor.execute("INSERT INTO users (user_id, is_admin) VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET is_admin = 1", (target_user_id,))
                conn.commit()
                del ADMIN_STATES[user_id]
                await update.message.reply_text(f"👑 ¡El usuario `{target_user_id}` ahora es **Administrador**!", parse_mode="Markdown")
            except ValueError:
                await update.message.reply_text("⚠️ ID inválido. Debe ser solo números. Inténtalo de nuevo:")

        conn.close()

async def show_main_screen(query, user_id, cursor):
    cursor.execute("SELECT is_subscribed FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    is_sub = row[0] if row else 0

    text = (
        "👋 ¡Bienvenido a **SportsPicks VIP**!\n\n"
        "Obtén los mejores pronósticos deportivos automatizados e impulsados por inteligencia artificial.\n\n"
        "💳 **Planes de Suscripción:**\n"
        "• 1 Mes: **$20 USDT**\n"
        "• 2 Meses: **$35 USDT**\n"
        "• 6 Meses: **$100 USDT**\n\n"
        "*(Nota: El bot a veces puede tardar unos segundos en responder)*\n\n"
        "Selecciona una opción abajo para ver las instrucciones y realizar tu pago vía Binance Pay:"
    )
    keyboard = [
        [InlineKeyboardButton("1 Mes ($20 USDT)", callback_data="pay_1m")],
        [InlineKeyboardButton("2 Meses ($35 USDT)", callback_data="pay_2m")],
        [InlineKeyboardButton("6 Meses ($100 USDT)", callback_data="pay_6m")],
    ]
    if is_sub:
        keyboard.append([InlineKeyboardButton("🚀 Ver Pronósticos VIP", callback_data="show_leagues")])

    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception:
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

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
    await query.edit_message_text("🏆 **Ligas Disponibles:**\nSelecciona una para ver todos los pronósticos disponibles:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

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
