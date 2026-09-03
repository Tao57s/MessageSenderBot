import os
import asyncio
from dotenv import load_dotenv
from aiogram import Router, Bot, Dispatcher, types
from aiogram.filters import Command,ChatMemberUpdatedFilter, MEMBER, ADMINISTRATOR, LEFT, KICKED
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

# Импортируем общую логику БД
from database import (
    init_db, is_allowed, add_user, remove_user, get_all_users,
    add_chat, remove_chat, toggle_chat, get_active_chats, get_all_chats
)

load_dotenv()

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", 0))
PROXY_URL = os.getenv("PROXY_URL")  # Опционально

if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN не найден!")
if not ADMIN_TELEGRAM_ID:
    raise ValueError("❌ ADMIN_TELEGRAM_ID не найден!")

# ========== НАСТРОЙКА БОТА ==========
PLATFORM = "telegram"

bot = None
if PROXY_URL:
    try:
        # Попытка создать сессию с прокси. Если прокси некорректен, AiohttpSession
        # выбросит исключение (например ValueError для неправильного порта).
        session = AiohttpSession(proxy=PROXY_URL)
        bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties())
    except Exception as e:
        # В случае ошибки логируем и продолжаем без прокси
        print(f"⚠️ Не удалось подключить прокси ({PROXY_URL}): {e}\nЗапускаю без прокси.")
        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties())
else:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties())

dp = Dispatcher()
router = Router()  # <-- Добавьте эту строку
dp.include_router(router)  # <-- И эту
# ========== КОМАНДЫ ==========

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=(LEFT | KICKED) >> (MEMBER | ADMINISTRATOR)))
async def on_bot_added(event: types.ChatMemberUpdated):
    # Получаем ID чата
    chat_id = event.chat.id
    await bot.send_message(ADMIN_TELEGRAM_ID, f"🤖 Бот успешно добавлен в этот чат/канал {chat_id}!")
    await bot.send_message(ADMIN_TELEGRAM_ID, f"/add_chat {chat_id}")
        # Здесь лучше всего сохранять chat_id в базу данных или файл
    print(f"✅ Бот добавлен в чат/канал с ID: {chat_id}") 

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if await is_allowed(PLATFORM, user_id):
        await message.reply(
            "✅ Вы в белом списке!\n\n"
            "📤 Отправляйте мне сообщения, и я перешлю их во все активные чаты.\n\n"
            "🔧 Команды для админа:\n"
            "/add_user <ID> - добавить пользователя\n"
            "/remove_user <ID> - удалить пользователя\n"
            "/list_users - список пользователей\n"
            "/add_chat <ID> [название] - добавить чат\n"
            "/remove_chat <ID> - удалить чат\n"
            "/toggle_chat <ID> - включить/выключить чат\n"
            "/list_chats - список чатов"
        )
    else:
        await message.reply("❌ У вас нет прав. Обратитесь к администратору.")

@dp.message(Command("add_user"))
async def cmd_add_user(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может добавлять пользователей.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /add_user <ID_пользователя>")
        return
    
    try:
        new_user_id = int(args[1])
        if await add_user(PLATFORM, new_user_id):
            await message.reply(f"✅ Пользователь {new_user_id} добавлен!")
        else:
            await message.reply(f"⚠️ Пользователь {new_user_id} уже в списке.")
    except ValueError:
        await message.reply("❌ ID должен быть числом.")

@dp.message(Command("remove_user"))
async def cmd_remove_user(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может удалять пользователей.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /remove_user <ID_пользователя>")
        return
    
    try:
        remove_user_id = int(args[1])
        if await remove_user(PLATFORM, remove_user_id):
            await message.reply(f"✅ Пользователь {remove_user_id} удалён.")
        else:
            await message.reply(f"❌ Пользователь {remove_user_id} не найден.")
    except ValueError:
        await message.reply("❌ ID должен быть числом.")

@dp.message(Command("list_users"))
async def cmd_list_users(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может просматривать список.")
        return
    
    users = await get_all_users(PLATFORM)
    if not users:
        await message.reply("📭 Белый список пуст.")
        return
    
    users_text = "\n".join([f"• `{uid}`" for uid in users])
    await message.reply(f"📋 Разрешённые пользователи:\n{users_text}", parse_mode="Markdown")

@dp.message(Command("add_chat"))
async def cmd_add_chat(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может добавлять чаты.")
        return
    
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.reply(
            "ℹ️ Использование: /add_chat <ID_чата> [название]\n"
            "Пример: /add_chat -1001234567890 Моя группа"
        )
        return
    
    try:
        chat_id = int(args[1])
        chat_name = args[2] if len(args) > 2 else None
        
        if await add_chat(PLATFORM, chat_id, chat_name):
            await message.reply(f"✅ Чат {chat_id} добавлен для пересылки!")
        else:
            await message.reply(f"⚠️ Чат {chat_id} уже есть в списке.")
    except ValueError:
        await message.reply("❌ ID чата должен быть числом.")

@dp.message(Command("remove_chat"))
async def cmd_remove_chat(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может удалять чаты.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /remove_chat <ID_чата>")
        return
    
    try:
        chat_id = int(args[1])
        if await remove_chat(PLATFORM, chat_id):
            await message.reply(f"✅ Чат {chat_id} удалён из списка.")
        else:
            await message.reply(f"❌ Чат {chat_id} не найден.")
    except ValueError:
        await message.reply("❌ ID чата должен быть числом.")

@dp.message(Command("toggle_chat"))
async def cmd_toggle_chat(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может управлять чатами.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /toggle_chat <ID_чата>")
        return
    
    try:
        chat_id = int(args[1])
        chats = await get_all_chats(PLATFORM)
        chat_exists = any(c[0] == chat_id for c in chats)
        
        if not chat_exists:
            await message.reply(f"❌ Чат {chat_id} не найден.")
            return
        
        # Получаем текущий статус
        for c_id, _, is_active in chats:
            if c_id == chat_id:
                new_status = not is_active
                break
        
        if await toggle_chat(PLATFORM, chat_id, new_status):
            status_text = "включён" if new_status else "выключен"
            await message.reply(f"✅ Чат {chat_id} {status_text}.")
        else:
            await message.reply(f"❌ Ошибка при изменении статуса чата.")
    except ValueError:
        await message.reply("❌ ID чата должен быть числом.")

@dp.message(Command("list_chats"))
async def cmd_list_chats(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может просматривать список.")
        return
    
    chats = await get_all_chats(PLATFORM)
    if not chats:
        await message.reply("📭 Список чатов пуст.")
        return
    
    chats_text = []
    for chat_id, name, is_active in chats:
        status = "🟢 Активен" if is_active else "🔴 Неактивен"
        chats_text.append(f"• {name}\n  ID: `{chat_id}`\n  Статус: {status}")
    
    await message.reply(
        f"📋 Список чатов для пересылки:\n\n" + "\n".join(chats_text),
        parse_mode="Markdown"
    )

# ========== ОСНОВНАЯ ЛОГИКА ПЕРЕСЫЛКИ ==========

@dp.message()
async def forward_message(message: types.Message):
    user_id = message.from_user.id
    
    if not await is_allowed(PLATFORM, user_id):
        await message.reply("❌ У вас нет прав на использование этого бота.")
        return
    
    active_chats = await get_active_chats(PLATFORM)
    
    if not active_chats:
        await message.reply("⚠️ Нет активных чатов для пересылки. Добавьте чат через /add_chat")
        return
    
    success_count = 0
    error_chats = []
    
    for chat_id, chat_name in active_chats:
        try:
            await bot.forward_message(
                chat_id=chat_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success_count += 1
        except Exception as e:
            error_chats.append(f"{chat_name} (ID: {chat_id}) - {str(e)[:50]}")
    
    if success_count > 0:
        report = f"✅ Переслано в {success_count} чатов"
        if error_chats:
            report += f"\n\n⚠️ Ошибки:\n" + "\n".join(error_chats)
        await message.reply(report)
    else:
        await message.reply(f"❌ Не удалось переслать ни в один чат.\n\nОшибки:\n" + "\n".join(error_chats))

# ========== ЗАПУСК ==========

async def main():
    await init_db()
    print("🤖 Telegram бот запущен!")
    print(f"👥 Админ: {ADMIN_TELEGRAM_ID}")
    
    chats = await get_active_chats(PLATFORM)
    print(f"📤 Активных чатов для пересылки: {len(chats)}")
    for chat_id, name in chats:
        print(f"   - {name} (ID: {chat_id})")
  
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print("🔄 Перезапустите бота через несколько секунд")

if __name__ == "__main__":
    asyncio.run(main())