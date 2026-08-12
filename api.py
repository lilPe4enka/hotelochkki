import sqlite3
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# Разрешаем запросы от нашего Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "wishlist.db"

# --- 1. НАСТРОЙКА БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Создаем таблицу товаров, если ее еще нет
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            image_url TEXT,
            price TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db() # Запускаем при старте сервера

# --- 2. МОДЕЛИ ДАННЫХ ---
class AddItemRequest(BaseModel):
    user_id: int
    url: str

class ItemResponse(BaseModel):
    id: int
    user_id: int
    url: str
    title: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[str] = None

# --- 3. УМНАЯ ФУНКЦИЯ ПАРСИНГА ССЫЛОК ---
def parse_link(url: str):
    # Притворяемся настоящим человеком из браузера Chrome
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com/"
    }
    
    title = "Товар по ссылке"
    image_url = "https://via.placeholder.com/300x300?text=Нет+фото"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. Ищем НАЗВАНИЕ товара (3 разных способа)
            og_title = soup.find('meta', property='og:title')
            title_tag = soup.find('title')
            h1_tag = soup.find('h1')
            
            if og_title and og_title.get('content'):
                title = og_title.get('content')
            elif title_tag and title_tag.text:
                title = title_tag.text
            elif h1_tag and h1_tag.text:
                title = h1_tag.text

            # 2. Ищем КАРТИНКУ товара (3 разных способа)
            og_image = soup.find('meta', property='og:image')
            tw_image = soup.find('meta', attrs={'name': 'twitter:image'})
            
            if og_image and og_image.get('content'):
                image_url = og_image.get('content')
            elif tw_image and tw_image.get('content'):
                image_url = tw_image.get('content')
            else:
                # Если ничего нет, ищем просто любую первую картинку на странице
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if src and src.startswith('http'):
                        # Отсеиваем мелкие логотипы и иконки
                        if not any(x in src.lower() for x in ['logo', 'icon', 'pixel', 'avatar']):
                            image_url = src
                            break
                            
    except Exception as e:
        print(f"Ошибка парсинга {url}: {e}")
        
    # Приводим название в красивый вид (убираем лишние пробелы и сокращаем длину)
    title = title.replace('\n', ' ').strip()
    if len(title) > 65:
        title = title[:62] + "..."
        
    return {"title": title, "image_url": image_url, "price": None}

# --- 4. РОУТЫ API ---

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Wishlist API is running!"}

# Получить все товары пользователя
@app.get("/api/wishlist/{user_id}", response_model=List[ItemResponse])
def get_wishlist(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, url, title, image_url, price FROM items WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    items = []
    for row in rows:
        items.append({
            "id": row[0], "user_id": row[1], "url": row[2],
            "title": row[3], "image_url": row[4], "price": row[5]
        })
    return items

# Добавить новый товар (вызывается и из бота, и из Mini App)
@app.post("/api/wishlist", response_model=ItemResponse)
def add_item(request: AddItemRequest):
    # Парсим ссылку
    parsed_data = parse_link(request.url)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO items (user_id, url, title, image_url, price)
        VALUES (?, ?, ?, ?, ?)
    ''', (request.user_id, request.url, parsed_data['title'], parsed_data['image_url'], parsed_data['price']))
    
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {
        "id": item_id,
        "user_id": request.user_id,
        "url": request.url,
        "title": parsed_data['title'],
        "image_url": parsed_data['image_url'],
        "price": parsed_data['price']
    }

# Удалить товар
@app.delete("/api/wishlist/{item_id}")
def delete_item(item_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"success": True}
