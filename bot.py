import asyncio
import re
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

# 1. Вставьте токен вашего бота
BOT_TOKEN = "8962380300:AAHjm3VlqgUT--ATCQcU6p0wPAreGOMsXNM"


# 2. Вставьте имя (username) вашего бота БЕЗ @ (например: my_wishlist_bot)
BOT_USERNAME = "hotelochkki_bot"


# 3. Вставьте ссылку на ваш API на Render (БЕЗ слэша на конце!)
# Пример: "https://wishlist-api-a3wl.onrender.com"
API_URL = "https://hotelochkki.onrender.com"

# 3. Ссылка на будущий фронтенд (Mini App)
# Пока фронтенда нет, можете вставить любую заглушку, например "https://google.com". 
# На следующем шаге мы заменим ее на реальную ссылку с Netlify/GitHub Pages.
WEB_APP_URL = "https://lilpe4enka.github.io/hotelochkki/?=v1.3"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Обработка команды /start (умеет отличать владельца от гостя)
@dp.message(CommandStart())
async def start_cmd(message: Message):
    # Разбиваем текст команды, чтобы проверить, есть ли скрытые параметры (Deep Link)
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
        "Я твой личный <b>Wishlist</b>. Просто отправляй мне ссылки на товары, и я их сохраню.\n\n"
        "🌟 <b>Как поделиться списком с друзьями?</b>\n"
        "Просто отправь команду /share, и я дам тебе специальную ссылку-приглашение!"
    )
    
    await message.answer(text=welcome_text, reply_markup=builder.as_markup(), parse_mode="HTML")

# КОМАНДА: Генерация ссылки для друзей (с надежной HTML разметкой)
@dp.message(Command("share"))
async def share_cmd(message: Message):
    # Генерируем специальный Deep Link Telegram
    my_link = f"https://t.me/{BOT_USERNAME}?start=wishlist_{message.from_user.id}"
    
    await message.answer(
        f"🔗 <b>Твоя личная ссылка на витрину желаний:</b>\n\n<code>{my_link}</code>\n\n"
        "Скопируй и отправь её друзьям! Они смогут посмотреть твой список, но не смогут ничего удалить или изменить.",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# Обработка ЛЮБЫХ текстов и ссылок
@dp.message()
async def handle_text(message: Message):
    # Если это системные команды, игнорируем их здесь
    if message.text and (message.text.startswith('/start') or message.text.startswith('/share')):
        return

    print(f"\n📩 Получено сообщение от {message.from_user.first_name}: {message.text}")
    text = message.text or ""
    
    # Ищем ссылки в тексте
    urls = re.findall(r'(https?://\S+)', text)
    
    if not urls:
        await message.answer("Я не нашел ссылку в твоем сообщении. Отправь мне ссылку на товар 🔗")
        return
        
    url_to_save = urls[0]
    msg = await message.answer("⏳ Анализирую ссылку и сохраняю товар...")
    
    # Отправляем ссылку на наш бэкенд на Render
    async with aiohttp.ClientSession() as session:
        try:
            payload = {"user_id": message.from_user.id, "url": url_to_save}
            async with session.post(f"{API_URL}/api/wishlist", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Очищаем название от HTML тегов, чтобы не сломать разметку
                    safe_title = data.get("title", "Товар").replace('<', '').replace('>', '') 
                    await msg.edit_text(f"✅ <b>Успешно сохранено!</b>\n\n📦 {safe_title}", parse_mode="HTML")
                    print("✅ Товар успешно сохранен!")
                else:
                    await msg.edit_text("❌ Ошибка при сохранении товара на сервере.")
        except Exception as e:
            print(f"❌ Критическая ошибка соединения с Render: {e}")
            await msg.edit_text("❌ Не удалось связаться с сервером API.")

async def main():
    print("Бот Wishlist запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
