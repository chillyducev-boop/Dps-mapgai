from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import os
import json
from datetime import datetime, timedelta
import urllib.parse

# Загрузка переменных окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PUBLISH_CHAT_ID = os.environ.get("PUBLISH_CHAT_ID")
MIN_NO_TO_MARK_GONE = int(os.environ.get("MIN_NO_TO_MARK_GONE"))
GONE_LIFETIME_MINUTES = int(os.environ.get("GONE_LIFETIME_MINUTES"))

DATA_FILE = "points.json"

# Загружаем существующие точки
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        points = json.load(f)
else:
    points = []

# Старт бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("Отправить локацию"), KeyboardButton("Добавить адрес")]]
    await update.message.reply_text(
        "Привет! Выберите способ добавления точки ДПС:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Обработка автоматической геолокации
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_location = update.message.location
    description = update.message.caption or "ДПС"
    point_id = len(points) + 1
    expire_time = datetime.now() + timedelta(minutes=GONE_LIFETIME_MINUTES)
    
    new_point = {
        "id": point_id,
        "lat": user_location.latitude,
        "lon": user_location.longitude,
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

    map_link = f"https://yandex.ru/maps/?ll={user_location.longitude}%2C{user_location.latitude}&z=14"
    await context.bot.send_message(
        chat_id=PUBLISH_CHAT_ID,
        text=f"🚓 {description}\n📍 {map_link}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Точка добавлена!")

# Кнопка "Добавить адрес"
async def add_address_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите адрес:")

# Обработка адреса
async def address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text
    point_id = len(points) + 1
    expire_time = datetime.now() + timedelta(minutes=GONE_LIFETIME_MINUTES)
    
    new_point = {
        "id": point_id,
        "address": address,
        "desc": "ДПС",
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

    # Общая ссылка на карту с адресами всех точек
    all_addresses = [urllib.parse.quote(p["address"]) for p in points if "address" in p]
    map_text = "%0A".join(all_addresses)
    map_link = f"https://yandex.ru/maps/?text={map_text}" if all_addresses else "Нет адресов"

    await context.bot.send_message(
        chat_id=PUBLISH_CHAT_ID,
        text=f"🚓 {new_point['desc']}\n📍 {map_link}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Точка добавлена по адресу!")

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

    await query.edit_message_text(f"🚓 {point.get('desc','ДПС')}\n✅ {point['yes']}  ❌ {point['no']}")

# Привязка обработчиков
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, address_handler))
app.add_handler(MessageHandler(filters.Regex("Добавить адрес"), add_address_prompt))
app.add_handler(CallbackQueryHandler(vote_handler))

app.run_polling()
