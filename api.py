import sqlite3
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "wishlist.db"

# --- 1. НАСТРОЙКА И ОБНОВЛЕНИЕ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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
    
    # Безопасное добавление новых колонок (если их еще нет)
    try:
        cursor.execute("ALTER TABLE items ADD COLUMN category TEXT DEFAULT 'Остальное'")
        cursor.execute("ALTER TABLE items ADD COLUMN is_purchased INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE items ADD COLUMN is_priority INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Если возникает ошибка, значит колонки уже существуют, идем дальше
        
    conn.commit()
    conn.close()

init_db()

# --- 2. МОДЕЛИ ДАННЫХ ---
class AddItemRequest(BaseModel):
    user_id: int
    url: str

class UpdateItemRequest(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    is_purchased: Optional[int] = None
    is_priority: Optional[int] = None

class ItemResponse(BaseModel):
    id: int
    user_id: int
    url: str
    title: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[str] = None
    category: Optional[str] = "Остальное"
    is_purchased: Optional[int] = 0
    is_priority: Optional[int] = 0

# --- 3. ПАРСЕР ---
def parse_link(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
    }
    title = "Новый товар (нажмите ✏️ чтобы изменить)"
    image_url = "https://via.placeholder.com/300x300?text=Нет+фото"
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title.get('content')
            elif soup.title:
                title = soup.title.string
                
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                image_url = og_image.get('content')
                            
    except Exception as e:
        print(f"Ошибка парсинга {url}: {e}")
        
    title = title.replace('\n', ' ').strip()
    if len(title) > 65:
        title = title[:62] + "..."
        
    return {"title": title, "image_url": image_url, "price": None}

# --- 4. РОУТЫ API ---
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Wishlist API 2.0 is running!"}

@app.get("/api/wishlist/{user_id}", response_model=List[ItemResponse])
def get_wishlist(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Запрашиваем новые поля
    cursor.execute("SELECT id, user_id, url, title, image_url, price, category, is_purchased, is_priority FROM items WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    items = []
    for row in rows:
        items.append({
            "id": row[0], "user_id": row[1], "url": row[2],
            "title": row[3], "image_url": row[4], "price": row[5],
            "category": row[6], "is_purchased": row[7], "is_priority": row[8]
        })
    return items

@app.post("/api/wishlist", response_model=ItemResponse)
def add_item(request: AddItemRequest):
    parsed_data = parse_link(request.url)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO items (user_id, url, title, image_url, price, category, is_purchased, is_priority)
        VALUES (?, ?, ?, ?, ?, 'Остальное', 0, 0)
    ''', (request.user_id, request.url, parsed_data['title'], parsed_data['image_url'], parsed_data['price']))
    
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {
        "id": item_id, "user_id": request.user_id, "url": request.url,
        "title": parsed_data['title'], "image_url": parsed_data['image_url'],
        "price": parsed_data['price'], "category": "Остальное",
        "is_purchased": 0, "is_priority": 0
    }

# ДИНАМИЧЕСКОЕ ОБНОВЛЕНИЕ (Название, категория, статус покупки, приоритет)
@app.put("/api/wishlist/{item_id}")
def update_item(item_id: int, request: UpdateItemRequest):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Собираем только те поля, которые пришли в запросе
    update_fields = []
    params = []
    
    if request.title is not None:
        update_fields.append("title = ?")
        params.append(request.title)
    if request.category is not None:
        update_fields.append("category = ?")
        params.append(request.category)
    if request.is_purchased is not None:
        update_fields.append("is_purchased = ?")
        params.append(request.is_purchased)
    if request.is_priority is not None:
        update_fields.append("is_priority = ?")
        params.append(request.is_priority)
        
    if update_fields:
        params.append(item_id)
        query = f"UPDATE items SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()
        
    conn.close()
    return {"success": True}

@app.delete("/api/wishlist/{item_id}")
def delete_item(item_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"success": True}
