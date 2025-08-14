import os
import json
from datetime import datetime, timedelta
import requests
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

# --- Переменные окружения ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PUBLISH_CHAT_ID = int(os.environ.get("PUBLISH_CHAT_ID", 0))
YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY")
MIN_NO_TO_MARK_GONE = int(os.environ.get("MIN_NO_TO_MARK_GONE", 3))
GONE_LIFETIME_MINUTES = int(os.environ.get("GONE_LIFETIME_MINUTES", 30))

DATA_FILE = "points.json"

# --- Загружаем точки ---
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        points = json.load(f)
else:
    points = []

# --- Функции бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Отправить локацию", request_location=True)],
        [KeyboardButton("Добавить вручную")]
    ]
    await update.message.reply_text(
        "Привет! Отправь мне точку, где ты видел ДПС, и описание.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_location = update.message.location
    context.user_data["lat"] = user_location.latitude
    context.user_data["lon"] = user_location.longitude
    await update.message.reply_text("Теперь отправь описание или фото/видео.")

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lat = context.user_data.get("lat")
    lon = context.user_data.get("lon")
    if not lat or not lon:
        await update.message.reply_text("Сначала отправь локацию.")
        return

    description = update.message.caption or update.message.text or "ДПС"
    point_id = len(points) + 1
    expire_time = datetime.now() + timedelta(minutes=GONE_LIFETIME_MINUTES)
    new_point = {
        "id": point_id,
        "lat": lat,
        "lon": lon,
        "desc": description,
        "yes": 1,
        "no": 0,
        "expire": expire_time.isoformat()
    }
    points.append(new_point)
    with open(DATA_FILE, "w") as f:
        json.dump(points, f)

    keyboard = [
        [InlineKeyboardButton("✅ Да, видел", callback_data=f"yes_{point_id}"),
         InlineKeyboardButton("❌ Уже нету", callback_data=f"no_{point_id}")]
    ]

    await context.bot.send_message(
        chat_id=PUBLISH_CHAT_ID,
        text=f"🚓 {description}\n📍 {lat}, {lon}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Точка добавлена!")

async def vote_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, pid = query.data.split("_")
    pid = int(pid)

    for point in points:
        if point["id"] == pid:
            if action == "yes":
                point["yes"] += 1
            elif action == "no":
                point["no"] += 1
                if point["no"] >= MIN_NO_TO_MARK_GONE:
                    points.remove(point)
            break

    with open(DATA_FILE, "w") as f:
        json.dump(points, f)

    await query.edit_message_text(f"🚓 {point['desc']}\n✅ {point['yes']}  ❌ {point['no']}")

# --- Ручной ввод через Яндекс Геокодер ---
MANUAL_INPUT = 1

async def manual_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Напиши адрес или описание точки, например: 'Самара, улица Ленина 50'."
    )
    return MANUAL_INPUT

async def save_manual_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text
    url = f"https://geocode-maps.yandex.ru/1.x/?apikey={YANDEX_API_KEY}&geocode={address}&format=json"
    response = requests.get(url).json()

    try:
        coords = response["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
        lon, lat = map(float, coords.split())
    except (IndexError, KeyError):
        await update.message.reply_text("Не удалось определить координаты. Попробуй другой адрес.")
        return

    description = address
    point_id = len(points) + 1
    expire_time = datetime.now() + timedelta(minutes=GONE_LIFETIME_MINUTES)
    new_point = {
        "id": point_id,
        "lat": lat,
        "lon": lon,
        "desc": description,
        "yes": 1,
        "no": 0,
        "expire": expire_time.isoformat()
    }
    points.append(new_point)
    with open(DATA_FILE, "w") as f:
        json.dump(points, f)

    await context.bot.send_message(
        chat_id=PUBLISH_CHAT_ID,
        text=f"🚓 {description}\n📍 {lat}, {lon}"
    )
    await update.message.reply_text("Точка добавлена!")
    return ConversationHandler.END

# --- Создаем приложение ---
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, media_handler))
app.add_handler(CallbackQueryHandler(vote_handler))

manual_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("Добавить вручную"), manual_handler)],
    states={MANUAL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_manual_point)]},
    fallbacks=[]
)
app.add_handler(manual_conv)

app.run_polling()
