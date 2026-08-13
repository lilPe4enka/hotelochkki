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
    # В PostgreSQL используется SERIAL для автоинкремента ID и BIGINT для ID пользователя Телеграм
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
    # При запуске сервера говорим Телеграму, куда слать сообщения
    await bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook успешно установлен!")
    yield
    # При выключении сервера удаляем Webhook
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
# 2. ЧАСТЬ FASTAPI (API И WEBHOOK)
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

def parse_link(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    title, image_url = "Новый товар", "https://via.placeholder.com/300x300?text=Нет+фото"
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            og_title = soup.find('meta', property='og:title')
            title = og_title.get('content') if (og_title and og_title.get('content')) else (soup.title.string if soup.title else title)
            og_img = soup.find('meta', property='og:image')
            image_url = og_img.get('content') if (og_img and og_img.get('content')) else image_url
    except Exception: pass
    return {"title": title[:62] + "..." if len(title)>65 else title, "image_url": image_url, "price": None}

@app.get("/")
def read_root(): return {"status": "ok", "message": "Wishlist API + Supabase DB are running!"}

@app.get("/api/wishlist/{user_id}", response_model=List[ItemResponse])
def get_wishlist(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    # В PostgreSQL плейсхолдеры для переменных это %s (вместо ?)
    cursor.execute("SELECT id, user_id, url, title, image_url, price, category, is_purchased, is_priority FROM items WHERE user_id = %s ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "user_id": r[1], "url": r[2], "title": r[3], "image_url": r[4], "price": r[5], "category": r[6], "is_purchased": r[7], "is_priority": r[8]} for r in rows]

@app.post("/api/wishlist", response_model=ItemResponse)
def add_item(request: AddItemRequest):
    parsed = parse_link(request.url)
    conn = get_db_connection()
    cursor = conn.cursor()
    # Используем RETURNING id, чтобы сразу получить ID нового товара
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
