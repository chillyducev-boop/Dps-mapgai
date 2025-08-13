import os
import json
import requests
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PUBLISH_CHAT_ID = os.environ.get("PUBLISH_CHAT_ID")
MIN_NO_TO_MARK_GONE = int(os.environ.get("MIN_NO_TO_MARK_GONE", 3))
GONE_LIFETIME_MINUTES = int(os.environ.get("GONE_LIFETIME_MINUTES", 30))
YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY")

DATA_FILE = "points.json"

# Загружаем существующие точки
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        points = json.load(f)
else:
    points = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Отправить локацию"), KeyboardButton("Добавить вручную")]
    ]
    await update.message.reply_text(
        "Привет! Отправь точку ДПС или добавь вручную.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def add_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь описание и координаты через запятую (lat, lon, описание), например:\n55.123, 37.456, Проверка ДПС")

async def manual_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        lat_str, lon_str, description = text.split(",", 2)
        lat = float(lat_str.strip())
        lon = float(lon_str.strip())
        description = description.strip()
    except Exception:
        await update.message.reply_text("Неверный формат. Используй: lat, lon, описание")
        return

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

    # Формируем Яндекс-карту
    map_url = f"https://static-maps.yandex.ru/1.x/?ll={lon},{lat}&size=450,250&z=12&l=map&pt={lon},{lat},pm2rdm"
    keyboard = [
        [InlineKeyboardButton("✅ Да, видел", callback_data=f"yes_{point_id}"),
         InlineKeyboardButton("❌ Уже нет", callback_data=f"no_{point_id}")]
    ]

    await context.bot.send_photo(
        chat_id=PUBLISH_CHAT_ID,
        photo=map_url,
        caption=f"🚓 {description}\n📍 {lat}, {lon}",
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

    await query.edit_message_caption(
        f"🚓 {point['desc']}\n✅ {point['yes']}  ❌ {point['no']}"
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Regex("Добавить вручную"), add_manual))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manual_handler))
app.add_handler(CallbackQueryHandler(vote_handler))

app.run_polling()
