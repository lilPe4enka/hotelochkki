import psycopg2
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from contextlib import asynccontextmanager

import asyncio
import re
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, WebAppInfo, Update
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================================
# --- НАСТРОЙКИ (ОБЯЗАТЕЛЬНО ЗАПОЛНИТЕ!) ---
BOT_TOKEN = "8962380300:AAHjm3VlqgUT--ATCQcU6p0wPAreGOMsXNM"
BOT_USERNAME = "hotelochkki_bot" # без @
RENDER_URL = "https://hotelochkki.onrender.com" # Ваша ссылка на Render (без слэша на конце)
WEB_APP_URL = "https://lilpe4enka.github.io/hotelochkki/"
DATABASE_URL = "postgresql://postgres.cxxtkkkagyuemunlabgx:3LT-f2C-JSK-PPe@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
# Ключ от ZenRows для парсинга Ozon
ZENROWS_API_KEY = "d266f5dd2f2615833ebfe209035b689beb17e847"

# Секретный пароль для ночного обновления цен
CRON_SECRET = "super_secret_night_update_777"
# ==========================================

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ (PostgreSQL) ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            image_url TEXT,
            price TEXT,
            category TEXT DEFAULT 'Остальное',
            is_purchased INTEGER DEFAULT 0,
            is_priority INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ СЕРВЕРА ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook успешно установлен!")
    yield
    await bot.delete_webhook()
    print("🛑 Webhook удален!")

# --- ИНИЦИАЛИЗАЦИЯ FASTAPI ---
app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ==========================================
# 1. ЧАСТЬ ДЛЯ ТЕЛЕГРАМ БОТА (ОБРАБОТЧИКИ)
# ==========================================

@dp.message(CommandStart())
async def start_cmd(message: Message):
    text_parts = message.text.split()
    if len(text_parts) > 1 and text_parts[1].startswith("wishlist_"):
        guest_id = text_parts[1].split("_")[1]
        builder = InlineKeyboardBuilder()
        builder.button(text="👀 Посмотреть витрину", web_app=WebAppInfo(url=f"{WEB_APP_URL}?guest_id={guest_id}"))
        await message.answer("👋 Привет! Вас пригласили посмотреть витрину желаний.\n\nНажмите на кнопку ниже:", reply_markup=builder.as_markup())
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Мой Wishlist 🎁", web_app=WebAppInfo(url=WEB_APP_URL))
    text = (f"Привет, {message.from_user.first_name}! 🛍\n\nЯ твой личный <b>Wishlist</b>. Отправляй мне ссылки на товары, и я их сохраню.\n\n"
            "🌟 <b>Как поделиться списком с друзьями?</b>\nПросто отправь команду /share!")
    await message.answer(text=text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.message(Command("share"))
async def share_cmd(message: Message):
    my_link = f"https://t.me/{BOT_USERNAME}?start=wishlist_{message.from_user.id}"
    await message.answer(f"🔗 <b>Твоя личная ссылка на витрину желаний:</b>\n\n<code>{my_link}</code>\n\nСкопируй и отправь её друзьям!", parse_mode="HTML", disable_web_page_preview=True)

@dp.message()
async def handle_text(message: Message):
    if message.text and (message.text.startswith('/start') or message.text.startswith('/share')): return
    urls = re.findall(r'(https?://\S+)', message.text or "")
    if not urls:
        await message.answer("Я не нашел ссылку в твоем сообщении 🔗")
        return
        
    msg = await message.answer("⏳ Анализирую ссылку и сохраняю товар...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{RENDER_URL}/api/wishlist", json={"user_id": message.from_user.id, "url": urls[0]}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    safe_title = data.get("title", "Товар").replace('<', '').replace('>', '')
                    await msg.edit_text(f"✅ <b>Успешно сохранено!</b>\n\n📦 {safe_title}", parse_mode="HTML")
                else:
                    await msg.edit_text("❌ Ошибка при сохранении.")
        except Exception:
            await msg.edit_text("❌ Ошибка соединения. Возможно, сервер Render еще загружается.")

# ==========================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (ПАРСИНГ)
# ==========================================

def extract_number(price_str: str) -> int:
    """Вытаскивает только цифры из строки '1 250 ₽' -> 1250"""
    if not price_str: return 0
    numbers = re.findall(r'\d+', price_str)
    return int(''.join(numbers)) if numbers else 0

def parse_link(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    title = "Новый товар"
    image_url = "https://via.placeholder.com/300x300?text=Нет+фото"
    price = None

    HEAVY_SITES = ["ozon.ru", "market.yandex.ru", "dns-shop.ru", "aliexpress.ru"]

    try:
        # --- 1. ЛОГИКА ДЛЯ СЛОЖНЫХ МАРКЕТПЛЕЙСОВ (ЧЕРЕЗ ZENROWS) ---
        if any(site in url for site in HEAVY_SITES):
            params = {"apikey": ZENROWS_API_KEY, "url": url, "js_render": "true", "premium_proxy": "true"}
            resp = requests.get("https://api.zenrows.com/v1/", params=params, timeout=30)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                og_title = soup.find('meta', property='og:title')
                if og_title: title = og_title.get('content')
                og_img = soup.find('meta', property='og:image')
                if og_img: image_url = og_img.get('content')
                
                # Проверка наличия
                page_text = soup.text.lower()
                out_of_stock_phrases = ["нет в наличии", "этот товар закончился", "раскупили", "out of stock", "товар распродан"]
                
                if any(phrase in page_text for phrase in out_of_stock_phrases):
                    price = "Нет в наличии"
                else:
                    # Ищем цену перед знаком ₽ или руб.
                    clean_text = soup.text.replace('\xa0', ' ').replace('\u2009', ' ')
                    price_match = re.search(r'([0-9\s]+)(?:₽|руб\.?)', clean_text, re.IGNORECASE)
                    
                    if price_match:
                        price = price_match.group(0).strip()
                        
            return {"title": title[:62] + "..." if len(title)>65 else title, "image_url": image_url, "price": price}

        # --- 2. ЛОГИКА ДЛЯ WILDBERRIES (Скрытый API) ---
        elif "wildberries.ru" in url:
            match = re.search(r'catalog/(\d+)/detail', url)
            if match:
                sku = match.group(1)
                api_url = f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={sku}"
                api_resp = requests.get(api_url, headers=headers, timeout=5)
                
                if api_resp.status_code == 200:
                    data = api_resp.json()
                    if not data.get('data') or not data['data'].get('products'):
                        price = "Нет в наличии"
                    else:
                        product = data['data']['products'][0]
                        title = product.get('name', title)
                        price_raw = product.get('salePriceU', 0) // 100
                        if price_raw > 0: 
                            price = f"{price_raw} ₽"
                        else:
                            price = "Нет в наличии"
                
                html_resp = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(html_resp.text, 'html.parser')
                og_img = soup.find('meta', property='og:image')
                if og_img and og_img.get('content'): image_url = og_img.get('content')
                
                return {"title": title[:62] + "..." if len(title)>65 else title, "image_url": image_url, "price": price}

        # --- 3. СТАНДАРТНАЯ ЛОГИКА ДЛЯ ОСТАЛЬНЫХ САЙТОВ ---
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            og_title = soup.find('meta', property='og:title')
            title = og_title.get('content') if (og_title and og_title.get('content')) else (soup.title.string if soup.title else title)
            
            og_img = soup.find('meta', property='og:image')
            image_url = og_img.get('content') if (og_img and og_img.get('content')) else image_url
            
            page_text = soup.text.lower()
            if "нет в наличии" in page_text or "out of stock" in page_text:
                price = "Нет в наличии"
            else:
                clean_text = soup.text.replace('\xa0', ' ').replace('\u2009', ' ')
                price_match = re.search(r'([0-9\s]+)(?:₽|руб\.?)', clean_text, re.IGNORECASE)
                if price_match:
                    price = price_match.group(0).strip()
            
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
        
    return {"title": title[:62] + "..." if len(title)>65 else title, "image_url": image_url, "price": price}

# ==========================================
# 3. ЧАСТЬ FASTAPI (API, WEBHOOK И CRON)
# ==========================================

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update_data = await request.json()
    update = Update.model_validate(update_data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"status": "ok"}

class AddItemRequest(BaseModel): user_id: int; url: str
class UpdateItemRequest(BaseModel): title: Optional[str] = None; category: Optional[str] = None; is_purchased: Optional[int] = None; is_priority: Optional[int] = None
class ItemResponse(BaseModel): id: int; user_id: int; url: str; title: Optional[str] = None; image_url: Optional[str] = None; price: Optional[str] = None; category: Optional[str] = "Остальное"; is_purchased: Optional[int] = 0; is_priority: Optional[int] = 0

@app.get("/")
def read_root(): return {"status": "ok", "message": "Wishlist API is running!"}

@app.get("/api/wishlist/{user_id}", response_model=List[ItemResponse])
def get_wishlist(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, url, title, image_url, price, category, is_purchased, is_priority FROM items WHERE user_id = %s ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "user_id": r[1], "url": r[2], "title": r[3], "image_url": r[4], "price": r[5], "category": r[6], "is_purchased": r[7], "is_priority": r[8]} for r in rows]

@app.post("/api/wishlist", response_model=ItemResponse)
def add_item(request: AddItemRequest):
    parsed = parse_link(request.url)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO items (user_id, url, title, image_url, price, category, is_purchased, is_priority) VALUES (%s, %s, %s, %s, %s, 'Остальное', 0, 0) RETURNING id", 
        (request.user_id, request.url, parsed['title'], parsed['image_url'], parsed['price'])
    )
    item_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": item_id, "user_id": request.user_id, "url": request.url, "title": parsed['title'], "image_url": parsed['image_url'], "price": parsed['price'], "category": "Остальное", "is_purchased": 0, "is_priority": 0}

@app.put("/api/wishlist/{item_id}")
def update_item(item_id: int, request: UpdateItemRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    fields, params = [], []
    if request.title is not None: fields.append("title = %s"); params.append(request.title)
    if request.category is not None: fields.append("category = %s"); params.append(request.category)
    if request.is_purchased is not None: fields.append("is_purchased = %s"); params.append(request.is_purchased)
    if request.is_priority is not None: fields.append("is_priority = %s"); params.append(request.is_priority)
    if fields:
        params.append(item_id)
        cursor.execute(f"UPDATE items SET {', '.join(fields)} WHERE id = %s", params)
        conn.commit()
    conn.close()
    return {"success": True}

@app.delete("/api/wishlist/{item_id}")
def delete_item(item_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = %s", (item_id,))
    conn.commit()
    conn.close()
    return {"success": True}

# --- МАНУАЛЬНОЕ ОБНОВЛЕНИЕ ЦЕН (ПО КНОПКЕ ИЗ MINI APP) ---
@app.post("/api/wishlist/update-prices/{user_id}")
def update_prices_manual(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, url FROM items WHERE user_id = %s AND is_purchased = 0", (user_id,))
    items = cursor.fetchall()
    updated_count = 0
    for item_id, url in items:
        parsed_data = parse_link(url)
        new_price = parsed_data.get("price")
        if new_price:
            cursor.execute("UPDATE items SET price = %s WHERE id = %s", (new_price, item_id))
            updated_count += 1
    conn.commit()
    conn.close()
    return {"success": True, "updated_count": updated_count}

# --- ФОНОВОЕ ОБНОВЛЕНИЕ ЦЕН (НОЧНОЙ CRON) ---
@app.get("/api/cron/update-all-prices")
async def cron_update_all_prices(token: str):
    if token != CRON_SECRET:
        return {"error": "Доступ запрещен"}

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, url, title, price FROM items WHERE is_purchased = 0")
    items = cursor.fetchall()
    
    user_notifications = {}
    updated_count = 0
    
    for item_id, user_id, url, title, old_price_str in items:
        parsed_data = parse_link(url)
        new_price_str = parsed_data.get("price")
        
        if new_price_str:
            cursor.execute("UPDATE items SET price = %s WHERE id = %s", (new_price_str, item_id))
            updated_count += 1
            
            if user_id not in user_notifications:
                user_notifications[user_id] = []
            
            # Товар закончился
            if new_price_str == "Нет в наличии" and old_price_str != "Нет в наличии":
                msg = f"⚠️ <b>{title}</b>\nТовар только что закончился на складе!\n<a href='{url}'>🔗 Проверить страницу</a>"
                user_notifications[user_id].append(msg)
                
            # Снова в наличии
            elif old_price_str == "Нет в наличии" and new_price_str != "Нет в наличии":
                msg = f"✅ <b>{title}</b>\nСнова в наличии! Текущая цена: <b>{new_price_str}</b>\n<a href='{url}'>🔗 Бежать покупать</a>"
                user_notifications[user_id].append(msg)
                
            # Скидка >= 5%
            elif old_price_str and old_price_str != "Нет в наличии" and new_price_str != "Нет в наличии":
                old_price = extract_number(old_price_str)
                new_price = extract_number(new_price_str)
                
                if old_price > 0 and new_price < old_price:
                    drop_percent = int(100 - (new_price / old_price * 100))
                    if drop_percent >= 5:
                        msg = f"📉 <b>{title}</b>\nБыло: <s>{old_price_str}</s>\nСтало: <b>{new_price_str}</b> (-{drop_percent}%)\n<a href='{url}'>🔗 Открыть страницу</a>"
                        user_notifications[user_id].append(msg)
            
    conn.commit()
    conn.close()
    
    # Отправка уведомлений
    for user_id, messages in user_notifications.items():
        if messages:
            final_text = "🔥 <b>Ночные обновления вашего Wishlist!</b>\n\n" + "\n\n".join(messages)
            try:
                await bot.send_message(chat_id=user_id, text=final_text, parse_mode="HTML", disable_web_page_preview=True)
            except Exception as e:
                print(f"❌ Ошибка отправки пользователю {user_id}: {e}")
    
    return {"success": True, "updated": updated_count}