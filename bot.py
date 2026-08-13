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
WEB_APP_URL = "https://lilpe4enka.github.io/hotelochkki/?=v1.3"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Обработка /start (умеет отличать вас от ваших гостей)
@dp.message(CommandStart())
async def start_cmd(message: Message):
    text_parts = message.text.split()
    
    # ЕСЛИ ЭТО ГОСТЬ (Перешел по ссылке-приглашению)
    if len(text_parts) > 1 and text_parts[1].startswith("wishlist_"):
        guest_id = text_parts[1].split("_")[1]
        
        builder = InlineKeyboardBuilder()
        # Добавляем параметр guest_id в ссылку для Mini App
        guest_url = f"{WEB_APP_URL}?guest_id={guest_id}"
        builder.button(text="👀 Посмотреть витрину", web_app=WebAppInfo(url=guest_url))
        
        await message.answer(
            "👋 Привет! Вас пригласили посмотреть витрину желаний.\n\nНажмите на кнопку ниже, чтобы открыть её:",
            reply_markup=builder.as_markup()
        )
        return

    # ОБЫЧНЫЙ СТАРТ (Для владельца)
    print(f"👉 Владелец {message.from_user.first_name} нажал /start")
    builder = InlineKeyboardBuilder()
    builder.button(text="Мой Wishlist 🎁", web_app=WebAppInfo(url=WEB_APP_URL))
    
    welcome_text = (
        f"Привет, {message.from_user.first_name}! 🛍\n\n"
        "Я твой личный **Wishlist**. Просто отправляй мне ссылки на товары, и я их сохраню.\n\n"
        "🌟 **Как поделиться списком с друзьями?**\n"
        "Просто отправь команду /share, и я дам тебе специальную ссылку-приглашение!"
    )
    
    await message.answer(text=welcome_text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# НОВАЯ КОМАНДА: Генерация ссылки для друзей
@dp.message(Command("share"))
async def share_cmd(message: Message):
    # Генерируем специальный Deep Link Telegram
    my_link = f"https://t.me/{BOT_USERNAME}?start=wishlist_{message.from_user.id}"
    
    await message.answer(
        f"🔗 **Твоя личная ссылка на витрину желаний:**\n\n`{my_link}`\n\n"
        "Скопируй и отправь её друзьям! Они смогут посмотреть твой список, но не смогут ничего удалить или изменить.",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

# Обработка ЛЮБЫХ текстов и ссылок (Осталась без изменений)
@dp.message()
async def handle_text(message: Message):
    if message.text and (message.text.startswith('/start') or message.text.startswith('/share')):
        return

    print(f"\n📩 Получено сообщение: {message.text}")
    text = message.text or ""
    urls = re.findall(r'(https?://\S+)', text)
    
    if not urls:
        await message.answer("Я не нашел ссылку в твоем сообщении. Отправь мне ссылку на товар 🔗")
        return
        
    url_to_save = urls[0]
    msg = await message.answer("⏳ Анализирую ссылку и сохраняю товар...")
    
    async with aiohttp.ClientSession() as session:
        try:
            payload = {"user_id": message.from_user.id, "url": url_to_save}
            async with session.post(f"{API_URL}/api/wishlist", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    safe_title = data.get("title", "Товар").replace('*', '').replace('_', '').replace('`', '')
                    await msg.edit_text(f"✅ **Успешно сохранено!**\n\n📦 {safe_title}", parse_mode="Markdown")
                else:
                    await msg.edit_text("❌ Ошибка при сохранении товара на сервере.")
        except Exception as e:
            await msg.edit_text("❌ Не удалось связаться с сервером API.")

async def main():
    print("Бот Wishlist запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
