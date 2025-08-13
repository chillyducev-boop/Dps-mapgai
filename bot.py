import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Загружаем переменные из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PUBLISH_CHAT_ID = int(os.getenv("PUBLISH_CHAT_ID"))
MIN_NO_TO_MARK_GONE = int(os.getenv("MIN_NO_TO_MARK_GONE"))
GONE_LIFETIME_MINUTES = int(os.getenv("GONE_LIFETIME_MINUTES"))

DATA_FILE = "points.json"

# Загружаем существующие точки
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        points = json.load(f)
else:
    points = []

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("Отправить локацию", request_location=True)]]
    await update.message.reply_text(
        "Привет! Отправь мне точку, где ты видел ДПС, и описание.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Обработка локации
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_location = update.message.location
    context.user_data["lat"] = user_location.latitude
    context.user_data["lon"] = user_location.longitude
    await update.message.reply_text("Теперь отправь описание или фото/видео.")

# Обработка текста и медиа
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

# Обработка голосования
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

# Создание приложения бота
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, media_handler))
app.add_handler(CallbackQueryHandler(vote_handler))

# Запуск бота
app.run_polling()
