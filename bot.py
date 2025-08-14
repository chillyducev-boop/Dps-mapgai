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
MIN_NO_TO_MARK_GONE = int(os.environ.get("MIN_NO_TO_MARK_GONE"))
GONE_LIFETIME_MINUTES = int(os.environ.get("GONE_LIFETIME_MINUTES"))
YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY")

DATA_FILE = "points.json"

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        points = json.load(f)
else:
    points = []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Отправить локацию", request_location=True)],
        [KeyboardButton("Добавить вручную")]
    ]
    await update.message.reply_text(
        "Привет! Отправь точку через геолокацию или добавь вручную.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_location = update.message.location
    context.user_data["lat"] = user_location.latitude
    context.user_data["lon"] = user_location.longitude
    await update.message.reply_text("Теперь отправь описание или фото/видео.")

async def manual_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь адрес или координаты в формате 'широта, долгота':")
    context.user_data["manual_input"] = True

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("manual_input"):
        # Проверка формата "lat, lon"
        text = update.message.text
        try:
            if "," in text:
                lat_str, lon_str = text.split(",")
                lat = float(lat_str.strip())
                lon = float(lon_str.strip())
            else:
                # Используем Яндекс Геокодинг
                r = requests.get("https://geocode-maps.yandex.ru/1.x/", params={
                    "apikey": YANDEX_API_KEY,
                    "geocode": text,
                    "format": "json"
                }).json()
                pos = r["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
                lon, lat = map(float, pos.split())
        except Exception as e:
            await update.message.reply_text("Не удалось определить координаты. Попробуйте другой формат.")
            return
        context.user_data["lat"] = lat
        context.user_data["lon"] = lon
        context.user_data["manual_input"] = False
        await update.message.reply_text("Теперь отправь описание или фото/видео.")
    else:
        await media_handler(update, context)

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lat = context.user_data.get("lat")
    lon = context.user_data.get("lon")
    if not lat or not lon:
        await update.message.reply_text("Сначала отправьте локацию или добавьте вручную.")
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

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.TEXT, text_handler))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, media_handler))
app.add_handler(MessageHandler(filters.Regex("Добавить вручную"), manual_handler))
app.add_handler(CallbackQueryHandler(vote_handler))

app.run_polling()
