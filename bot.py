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

# Генерация ссылки на карту с метками
def generate_map_url():
    if not points:
        return None
    pt_list = "~".join([f"{p['lon']},{p['lat']},pm2rdm" for p in points])
    return f"https://static-maps.yandex.ru/1.x/?apikey={YANDEX_API_KEY}&l=map&pt={pt_list}"

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Отправить локацию"), KeyboardButton("Добавить вручную")]
    ]
    await update.message.reply_text(
        "Привет! Отправь мне точку, где ты видел ДПС, или добавь вручную.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Обработка локации
async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_location = update.message.location
    context.user_data["lat"] = user_location.latitude
    context.user_data["lon"] = user_location.longitude
    await update.message.reply_text("Теперь отправь описание или фото/видео.")

# Обработка ручного ввода
async def manual_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправьте координаты в формате: широта, долгота или адрес.")
    context.user_data["manual"] = True

# Обработка текста/медиа
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Если ручной ввод
    if context.user_data.get("manual"):
        text = update.message.text
        context.user_data["manual"] = False
        # Попробуем распарсить как "lat,lon"
        try:
            lat_str, lon_str = text.split(",")
            lat = float(lat_str.strip())
            lon = float(lon_str.strip())
        except:
            # Если не числа — используем геокодинг через Яндекс
            geocode_url = f"https://geocode-maps.yandex.ru/1.x/?apikey={YANDEX_API_KEY}&geocode={text}&format=json"
            resp = requests.get(geocode_url).json()
            try:
                pos = resp["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
                lon, lat = map(float, pos.split())
            except:
                await update.message.reply_text("Не удалось определить координаты. Попробуйте ещё раз.")
                return
        description = update.message.caption or update.message.text or "ДПС"
    else:
        # Авто локация
        lat = context.user_data.get("lat")
        lon = context.user_data.get("lon")
        if not lat or not lon:
            await update.message.reply_text("Сначала отправьте локацию или добавьте вручную.")
            return
        description = update.message.caption or update.message.text or "ДПС"

    # Создаём точку
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

    # Сохраняем
    with open(DATA_FILE, "w") as f:
        json.dump(points, f)

    # Генерируем карту
    map_url = generate_map_url()

    keyboard = [
        [InlineKeyboardButton("✅ Да, видел", callback_data=f"yes_{point_id}"),
         InlineKeyboardButton("❌ Уже нету", callback_data=f"no_{point_id}")]
    ]

    text_msg = f"🚓 {description}\n📍 {lat}, {lon}"
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
app.add_handler(MessageHandler(filters.LOCATION, location_handler))
app.add_handler(MessageHandler(filters.Regex("Добавить вручную"), manual_handler))
app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO, media_handler))
app.add_handler(CallbackQueryHandler(vote_handler))

app.run_polling()
