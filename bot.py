import asyncio
import re
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

# 1. Вставьте токен вашего бота
BOT_TOKEN = "8962380300:AAHjm3VlqgUT--ATCQcU6p0wPAreGOMsXNM"

# 2. Вставьте ссылку на ваш API на Render (БЕЗ слэша на конце!)
# Пример: "https://wishlist-api-a3wl.onrender.com"
API_URL = "https://hotelochkki.onrender.com"

# 3. Ссылка на будущий фронтенд (Mini App)
# Пока фронтенда нет, можете вставить любую заглушку, например "https://google.com". 
# На следующем шаге мы заменим ее на реальную ссылку с Netlify/GitHub Pages.
WEB_APP_URL = "https://ваша-ссылка.netlify.app"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start_cmd(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Мой Wishlist 🎁",
        web_app=WebAppInfo(url=WEB_APP_URL)
    )
    
    welcome_text = (
        f"Привет, {message.from_user.first_name}! 🛍\n\n"
        "Я твой личный **Wishlist**. Больше не нужно терять ссылки в «Избранном»!\n\n"
        "🔗 **Как это работает:**\n"
        "Просто отправь мне в чат ссылку на любой товар (WB, Ozon, AliExpress и др.), и я сохраню его для тебя.\n\n"
        "А чтобы посмотреть все свои желания красивым списком, нажми на кнопку ниже 👇"
    )
    
    await message.answer(
        text=welcome_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# Обработка любых текстовых сообщений
@dp.message(F.text)
async def handle_text(message: Message):
    text = message.text
    
    # Ищем все ссылки в тексте сообщения с помощью регулярных выражений
    urls = re.findall(r'(https?://\S+)', text)
    
    if not urls:
        await message.answer("Я не нашел ссылку в твоем сообщении. Пожалуйста, отправь мне ссылку на товар 🔗")
        return
        
    url_to_save = urls[0] # Берем первую найденную ссылку
    
    # Отправляем временное сообщение, пока сервер обрабатывает ссылку
    msg = await message.answer("⏳ Анализирую ссылку и сохраняю товар...")
    
    # Отправляем запрос на наш бэкенд на Render
    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "user_id": message.from_user.id,
                "url": url_to_save
            }
            # Делаем POST запрос к нашему API
            async with session.post(f"{API_URL}/api/wishlist", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get("title", "Неизвестный товар")
                    
                    success_text = (
                        f"✅ **Успешно сохранено!**\n\n"
                        f"📦 {title}\n\n"
                        f"Товар уже ждет тебя в твоем Wishlist."
                    )
                    await msg.edit_text(success_text, parse_mode="Markdown")
                else:
                    await msg.edit_text("❌ Ошибка при сохранении товара. Сервер ответил ошибкой.")
                    
        except Exception as e:
            print(f"Ошибка связи с API: {e}")
            await msg.edit_text("❌ Не удалось связаться с сервером. Проверьте работает ли Render.")

async def main():
    print("Бот Wishlist запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
