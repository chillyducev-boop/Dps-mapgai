import os
import json
from datetime import datetime, timedelta
import requests
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PUBLISH_CHAT_ID = os.getenv("PUBLISH_CHAT_ID")
MIN_NO_TO_MARK_GONE = int(os.getenv("MIN_NO_TO_MARK_GONE", 3))
GONE_LIFETIME_MINUTES = int(os.getenv("GONE_LIFETIME_MINUTES", 30))
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

DATA_FILE = "points.json"

# Загружаем существующие точки
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        points = json.load(f)
else:
    points = []

# Генерация карты с метками
def generate_map_url():
    if not points:
        return None
    pt_list = "~".join([f"{p['lon']},{p['lat']},pm2rdm" for p in points])
    return f"https://static-maps.yandex.ru/1.x/?apikey={YANDEX_API_KEY}&l=map&pt={pt_list}"

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Добавить адрес")]
    ]
    await update.message.reply_text(
        "Привет! Отправьте адрес, где вы видели ДПС.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Обработка ручного ввода адреса
async def address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправьте адрес ДПС (например, город, улица, дом).")
    context.user_data["waiting_for_address"] = True

# Обработка текста
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_address"):
        address = update.message.text
        context.user_data["waiting_for_address"] = False

        # Геокодинг через Яндекс
        geocode_url = f"https://geocode-maps.yandex.ru/1.x/?apikey={YANDEX_API_KEY}&geocode={address}&format=json"
        resp = requests.get(geocode_url).json()
        try:
            pos = resp["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
            lon, lat = map(float, pos.split())
        except:
            await update.message.reply_text("Не удалось определить координаты по адресу. Попробуйте другой адрес.")
            return

        # Создаём точку
        point_id = len(points) + 1
        expire_time = datetime.now() + timedelta(minutes=GONE_LIFETIME_MINUTES)
        new_point = {
            "id": point_id,
            "lat": lat,
            "lon": lon,
            "desc": address,
            "yes": 1,
            "no": 0,
            "expire": expire_time.isoformat()
        }
        points.append(new_point)

        # Сохраняем
        with open(DATA_FILE, "w") as f:
            json.dump(points, f)

        # Генерируем карту
        map_url = generate_map_url()

        keyboard = [
            [InlineKeyboardButton("✅ Да, видел", callback_data=f"yes_{point_id}"),
             InlineKeyboardButton("❌ Уже нету", callback_data=f"no_{point_id}")]
        ]

        text_msg = f"🚓 {address}\n📍 {lat}, {lon}"
        if map_url:
            text_msg += f"\n\nКарта: {map_url}"

        await context.bot.send_message(
            chat_id=PUBLISH_CHAT_ID,
            text=text_msg,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await update.message.reply_text("Точка добавлена!")

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

# Создаём и запускаем бота
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Regex("Добавить адрес"), address_handler))
app.add_handler(MessageHandler(filters.TEXT, text_handler))
app.add_handler(CallbackQueryHandler(vote_handler))

app.run_polling()
