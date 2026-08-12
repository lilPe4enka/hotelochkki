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
WEB_APP_URL = "https://lilpe4enka.github.io/hotelochkki/=?v1.1"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Обработчик команды /start
@dp.message(CommandStart())
async def start_cmd(message: Message):
    print(f"👉 Пользователь {message.from_user.first_name} нажал /start")
    
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

# Обработка ЛЮБЫХ текстов и ссылок
@dp.message()
async def handle_text(message: Message):
    # Если это была команда /start, пропускаем её (она уже обработана выше)
    if message.text and message.text.startswith('/start'):
        return

    print(f"\n📩 Получено сообщение от {message.from_user.first_name}: {message.text}")
    text = message.text or ""
    
    # Регулярное выражение для поиска ссылок в тексте
    urls = re.findall(r'(https?://\S+)', text)
    
    if not urls:
        print("❌ Ссылок в сообщении не найдено.")
        await message.answer("Я не нашел ссылку в твоем сообщении. Отправь мне ссылку на товар 🔗")
        return
        
    url_to_save = urls[0] # Берем первую найденную ссылку
    print(f"🔗 Найдена ссылка: {url_to_save}")
    
    msg = await message.answer("⏳ Анализирую ссылку и сохраняю товар...")
    
    # Отправляем запрос на наш сервер Render
    async with aiohttp.ClientSession() as session:
        try:
            payload = {
                "user_id": message.from_user.id,
                "url": url_to_save
            }
            
            print(f"📡 Отправляем POST запрос на {API_URL}/api/wishlist ...")
            async with session.post(f"{API_URL}/api/wishlist", json=payload) as resp:
                print(f"Статус ответа от Render: {resp.status}")
                
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get("title", "Товар")
                    
                    # Очищаем название от спецсимволов, чтобы не сломать Markdown-разметку Telegram
                    safe_title = title.replace('*', '').replace('_', '').replace('`', '')
                    
                    await msg.edit_text(f"✅ **Успешно сохранено!**\n\n📦 {safe_title}", parse_mode="Markdown")
                    print("✅ Товар успешно сохранен!")
                else:
                    error_text = await resp.text()
                    print(f"❌ Ошибка от Render: {error_text}")
                    await msg.edit_text("❌ Ошибка при сохранении товара на сервере.")
                    
        except Exception as e:
            print(f"❌ Критическая ошибка соединения с Render: {e}")
            await msg.edit_text("❌ Не удалось связаться с сервером API. Проверьте, работает ли ваш бэкенд на Render.")

async def main():
    print("Бот Wishlist запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(main())
