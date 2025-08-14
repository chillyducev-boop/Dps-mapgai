import os
import json
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv
import requests

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PUBLISH_CHAT_ID = int(os.environ.get("PUBLISH_CHAT_ID"))
MIN_NO_TO_MARK_GONE = int(os.environ.get("MIN_NO_TO_MARK_GONE"))
GONE_LIFETIME_MINUTES = int(os.environ.get("GONE_LIFETIME_MINUTES"))
YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY")

DATA_FILE = "points.json"

# Загружаем существующие точки
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        points = json.load(f)
else:
    points = []

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Добавить вручную")],
        [KeyboardButton("Отправить текущую локацию", request_location=True)]
    ]
    await update.message.reply_text(
        "Привет! Отправь мне точку ДПС:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Обработчик локации
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_location = update.message.location
    context.user_data["lat"] = user_location.latitude
    context.user_data["lon"] = user_location.longitude
    await update.message.reply_text("Теперь отправь описание или фото/видео.")

# Обработчик ручного ввода (через текст)
async def manual_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправь описание точки ДПС и координаты через запятую (широта, долгота), например:\n"
        "ДПС на трассе, 53.1959, 50.1008"
    )

# Обработчик сообщений с описанием/координатами
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.startswith("ДПС"):
        try:
            # Разбираем текст вручную
            desc, lat, lon = map(str.strip, text.split(","))
            lat = float(lat)
            lon = float(lon)
        except:
            await update.message.reply_text("Ошибка формата. Пример: ДПС на трассе, 53.1959, 50.1008")
            return
    else:
        lat = context.user_data.get("lat")
        lon = context.user_data.get("lon")
        desc = text
        if not lat or not lon:
            await update.message.reply_text("Сначала отправь локацию или используй ручное добавление.")
            return

    point_id = len(points) + 1
    expire_time = datetime.now() + timedelta(minutes=GONE_LIFETIME_MINUTES)
    new_point = {
        "id": point_id,
        "lat": lat,
        "lon": lon,
        "desc": desc,
        "yes": 1,
        "no": 0,
        "expire": expire_time.isoformat()
    }
    points.append(new_point)

    # Генерируем ссылку на Яндекс карты
    map_url = f"https://yandex.ru/maps/?ll={lon}%2C{lat}&z=14&pt={lon}%2C{lat},pm2rdm"

    keyboard = [
        [InlineKeyboardButton("✅ Да, видел", callback_data=f"yes_{point_id}"),
         InlineKeyboardButton("❌ Уже нет", callback_data=f"no_{point_id}")]
    ]

    await context.bot.send_message(
        chat_id=PUBLISH_CHAT_ID,
        text=f"🚓 {desc}\n📍 {map_url}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Точка добавлена!")

    # Сохраняем данные
    with open(DATA_FILE, "w") as f:
        json.dump(points, f)

# Голосование
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

# Создаем приложение
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.Regex("Добавить вручную"), manual_add_handler))
app.add_handler(MessageHandler(filters.TEXT, media_handler))
app.add_handler(CallbackQueryHandler(vote_handler))

# Запуск бота
app.run_polling()
