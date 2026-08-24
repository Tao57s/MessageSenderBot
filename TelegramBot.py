import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession  # <-- ПРАВИЛЬНЫЙ ИМПОРТ
from aiogram.client.default import DefaultBotProperties
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, select, delete

# ========== ЗАГРУЗКА ПЕРЕМЕННЫХ ==========
load_dotenv()

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("klvhat_sender_bot")
YOUR_TELEGRAM_ID = os.getenv("TelegramId")
DATABASE_URL = os.getenv("klvhat_sender_db")

# ========== ПРОВЕРКА ПЕРЕМЕННЫХ ==========
print("📊 Проверка переменных:")
print(f"klvhat_sender_bot: {'✅' if BOT_TOKEN else '❌'}")
print(f"TelegramId: {'✅' if YOUR_TELEGRAM_ID else '❌'}")
print(f"klvhat_sender_db: {'✅' if DATABASE_URL else '❌'}")

if not BOT_TOKEN:
    raise ValueError("❌ klvhat_sender_bot не найден!")

if not YOUR_TELEGRAM_ID:
    raise ValueError("❌ TelegramId не найден!")
else:
    YOUR_TELEGRAM_ID = 1651725645

if not DATABASE_URL:
    raise ValueError("❌ klvhat_sender_db не найден!")

print("✅ Все переменные загружены!")

# ========== НАСТРОЙКА ПРОКСИ ==========
PROXY_URL = 'socks5://147.45.221.112:1082'  # Ваш прокси

# Правильный способ для aiogram 3.x
session = AiohttpSession(proxy=PROXY_URL)
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties())
dp = Dispatcher()



# ========== ПОДКЛЮЧЕНИЕ К БД ==========
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# ========== МОДЕЛИ БД ==========
class AllowedUser(Base):
    __tablename__ = "allowed_users"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)

class ForwardChat(Base):
    __tablename__ = "forward_chats"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, nullable=False)
    chat_name = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1)

# ========== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ==========
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def is_allowed(user_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(AllowedUser).where(AllowedUser.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None

async def add_user(user_id: int) -> bool:
    async with async_session() as session:
        existing = await session.execute(
            select(AllowedUser).where(AllowedUser.user_id == user_id)
        )
        if existing.scalar_one_or_none():
            return False
        
        new_user = AllowedUser(user_id=user_id)
        session.add(new_user)
        await session.commit()
        return True

async def remove_user(user_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(
            delete(AllowedUser).where(AllowedUser.user_id == user_id)
        )
        await session.commit()
        return result.rowcount > 0

async def get_all_users() -> list[int]:
    async with async_session() as session:
        result = await session.execute(select(AllowedUser))
        users = result.scalars().all()
        return [user.user_id for user in users]

# ========== РАБОТА С ЧАТАМИ ==========
async def add_chat(chat_id: int, chat_name: str = None) -> bool:
    async with async_session() as session:
        existing = await session.execute(
            select(ForwardChat).where(ForwardChat.chat_id == chat_id)
        )
        if existing.scalar_one_or_none():
            return False
        
        new_chat = ForwardChat(chat_id=chat_id, chat_name=chat_name)
        session.add(new_chat)
        await session.commit()
        return True

async def remove_chat(chat_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(
            delete(ForwardChat).where(ForwardChat.chat_id == chat_id)
        )
        await session.commit()
        return result.rowcount > 0

async def toggle_chat(chat_id: int, active: bool) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(ForwardChat).where(ForwardChat.chat_id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if not chat:
            return False
        
        chat.is_active = 1 if active else 0
        await session.commit()
        return True

async def get_active_chats() -> list[tuple[int, str]]:
    async with async_session() as session:
        result = await session.execute(
            select(ForwardChat).where(ForwardChat.is_active == 1)
        )
        chats = result.scalars().all()
        return [(chat.chat_id, chat.chat_name or f"Chat {chat.chat_id}") for chat in chats]

async def get_all_chats() -> list[tuple[int, str, bool]]:
    async with async_session() as session:
        result = await session.execute(select(ForwardChat))
        chats = result.scalars().all()
        return [(chat.chat_id, chat.chat_name or f"Chat {chat.chat_id}", bool(chat.is_active)) for chat in chats]

# ========== КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if await is_allowed(user_id):
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
    
    if user_id != YOUR_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может добавлять пользователей.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /add_user <ID_пользователя>")
        return
    
    try:
        new_user_id = int(args[1])
        if await add_user(new_user_id):
            await message.reply(f"✅ Пользователь {new_user_id} добавлен!")
        else:
            await message.reply(f"⚠️ Пользователь {new_user_id} уже в списке.")
    except ValueError:
        await message.reply("❌ ID должен быть числом.")

@dp.message(Command("remove_user"))
async def cmd_remove_user(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != YOUR_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может удалять пользователей.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /remove_user <ID_пользователя>")
        return
    
    try:
        remove_user_id = int(args[1])
        if await remove_user(remove_user_id):
            await message.reply(f"✅ Пользователь {remove_user_id} удалён.")
        else:
            await message.reply(f"❌ Пользователь {remove_user_id} не найден.")
    except ValueError:
        await message.reply("❌ ID должен быть числом.")

@dp.message(Command("list_users"))
async def cmd_list_users(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != YOUR_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может просматривать список.")
        return
    
    users = await get_all_users()
    if not users:
        await message.reply("📭 Белый список пуст.")
        return
    
    users_text = "\n".join([f"• `{uid}`" for uid in users])
    await message.reply(f"📋 Разрешённые пользователи:\n{users_text}", parse_mode="Markdown")

@dp.message(Command("add_chat"))
async def cmd_add_chat(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != YOUR_TELEGRAM_ID:
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
        
        if await add_chat(chat_id, chat_name):
            await message.reply(f"✅ Чат {chat_id} добавлен для пересылки!")
        else:
            await message.reply(f"⚠️ Чат {chat_id} уже есть в списке.")
    except ValueError:
        await message.reply("❌ ID чата должен быть числом.")

@dp.message(Command("remove_chat"))
async def cmd_remove_chat(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != YOUR_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может удалять чаты.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /remove_chat <ID_чата>")
        return
    
    try:
        chat_id = int(args[1])
        if await remove_chat(chat_id):
            await message.reply(f"✅ Чат {chat_id} удалён из списка.")
        else:
            await message.reply(f"❌ Чат {chat_id} не найден.")
    except ValueError:
        await message.reply("❌ ID чата должен быть числом.")

@dp.message(Command("toggle_chat"))
async def cmd_toggle_chat(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != YOUR_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может управлять чатами.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /toggle_chat <ID_чата>")
        return
    
    try:
        chat_id = int(args[1])
        
        async with async_session() as session:
            result = await session.execute(
                select(ForwardChat).where(ForwardChat.chat_id == chat_id)
            )
            chat = result.scalar_one_or_none()
            if not chat:
                await message.reply(f"❌ Чат {chat_id} не найден.")
                return
            
            new_status = not bool(chat.is_active)
        
        if await toggle_chat(chat_id, new_status):
            status_text = "включён" if new_status else "выключен"
            await message.reply(f"✅ Чат {chat_id} {status_text}.")
        else:
            await message.reply(f"❌ Ошибка при изменении статуса чата.")
    except ValueError:
        await message.reply("❌ ID чата должен быть числом.")

@dp.message(Command("list_chats"))
async def cmd_list_chats(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != YOUR_TELEGRAM_ID:
        await message.reply("❌ Только владелец бота может просматривать список.")
        return
    
    chats = await get_all_chats()
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
    
    if not await is_allowed(user_id):
        await message.reply("❌ У вас нет прав на использование этого бота.")
        return
    
    active_chats = await get_active_chats()
    
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
    print("🤖 Бот запущен!")
    print(f"👥 Админ: {YOUR_TELEGRAM_ID}")
    
    chats = await get_active_chats()
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