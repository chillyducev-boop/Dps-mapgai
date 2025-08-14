from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import os
import json
from datetime import datetime, timedelta
import urllib.parse

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PUBLISH_CHAT_ID = os.environ.get("PUBLISH_CHAT_ID")
MIN_NO_TO_MARK_GONE = int(os.environ.get("MIN_NO_TO_MARK_GONE"))
GONE_LIFETIME_MINUTES = 120  # 2 часа
YANDEX_MAP_LINK = "https://yandex.ru/maps/?um=constructor%3A8b6492d36113042cc1a1ab47cf0bd001486ca8187bb59c0aebc381e56a872997&source=constructorLink"

DATA_FILE = "points.json"

# Загружаем точки
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        points = json.load(f)
else:
    points = []

def cleanup_points():
    """Удаляем старые точки (старше 2 часов)"""
    now = datetime.now()
    global points
    points = [p for p in points if datetime.fromisoformat(p["expire"]) > now]
    with open(DATA_FILE, "w") as f:
        json.dump(points, f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("Отправить локацию"), KeyboardButton("Добавить адрес")]]
    await update.message.reply_text(
        "Привет! Выберите, как хотите добавить ДПС:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Авто-геолокация
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cleanup_points()
    user_location = update.message.location
    description = update.message.caption or "ДПС"
    point_id = len(points) + 1
    expire_time = datetime.now() + timedelta(minutes=GONE_LIFETIME_MINUTES)

    new_point = {
        "id": point_id,
        "desc": description,
        "lat": user_location.latitude,
        "lon": user_location.longitude,
        "yes": 1,
        "no": 0,
        "expire": expire_time.isoformat()
    }
    points.append(new_point)
    with open(DATA_FILE, "w") as f:
        json.dump(points, f)

    point_link = f"https://yandex.ru/maps/?ll={user_location.longitude}%2C{user_location.latitude}&z=14"
    keyboard = [
        [InlineKeyboardButton("✅ Да, видел", callback_data=f"yes_{point_id}"),
         InlineKeyboardButton("❌ Уже нету", callback_data=f"no_{point_id}")]
    ]

    await context.bot.send_message(
        chat_id=PUBLISH_CHAT_ID,
        text=f"🚓 {description}\n📍 Точка: {point_link}\n🌐 Общая карта: {YANDEX_MAP_LINK}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("Точка добавлена!")

# Добавление адреса вручную
async def add_address_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите адрес:")

async def address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cleanup_points()
    address = update.message.text
    point_id = len(points) + 1
    expire_time = datetime.now() + timedelta(minutes=GONE_LIFETIME_MINUTES)

    new_point = {
        "id": point_id,
        "desc": "ДПС",
        "address": address,
        "yes": 1,
        "no": 0,
        "expire": expire_time.isoformat()
    }
    points.append(new_point)
    with open(DATA_FILE, "w") as f:
        json.dump(points, f)

    point_link = f"https://yandex.ru/maps/?text={urllib.parse.quote(address)}"
    keyboard = [
        [InlineKeyboardButton("✅ Да, видел", callback_data=f"yes_{point_id}"),
         InlineKeyboardButton("❌ Уже нету", callback_data=f"no_{point_id}")]
    ]

    await context.bot.send_message(
        chat_id=PUBLISH_CHAT_ID,
        text=f"🚓 {new_point['desc']}\n📍 Точка: {point_link}\n🌐 Общая карта: {YANDEX_MAP_LINK}",
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

    await query.edit_message_text(
        f"🚓 {point.get('desc','ДПС')}\n✅ {point['yes']}  ❌ {point['no']}\n🌐 Общая карта: {YANDEX_MAP_LINK}"
    )

# Привязка обработчиков
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, address_handler))
app.add_handler(MessageHandler(filters.Regex("Добавить адрес"), add_address_prompt))
app.add_handler(CallbackQueryHandler(vote_handler))

app.run_polling()
