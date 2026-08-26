import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, select, delete, update
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не найден в .env файле!")

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class AllowedUser(Base):
    __tablename__ = "allowed_users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=True)
    max_id = Column(BigInteger, unique=True, nullable=True)
    vk_id = Column(BigInteger, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ForwardChat(Base):
    __tablename__ = "forward_chats"
    
    id = Column(Integer, primary_key=True)
    telegram_chat_id = Column(BigInteger, unique=True, nullable=True)
    max_chat_id = Column(BigInteger, unique=True, nullable=True)
    vk_chat_id = Column(BigInteger, unique=True, nullable=True)
    chat_name = Column(String(255), nullable=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ========== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ==========

async def is_allowed(platform: str, user_id: int) -> bool:
    """
    Проверка наличия пользователя в БД для конкретной платформы
    platform: 'telegram', 'max', 'vk'
    """
    async with async_session() as session:
        field = getattr(AllowedUser, f"{platform}_id")
        result = await session.execute(
            select(AllowedUser).where(field == user_id)
        )
        return result.scalar_one_or_none() is not None

async def add_user(platform: str, user_id: int) -> bool:
    """Добавление пользователя для конкретной платформы"""
    async with async_session() as session:
        field = getattr(AllowedUser, f"{platform}_id")
        
        # Проверяем существование
        existing = await session.execute(
            select(AllowedUser).where(field == user_id)
        )
        if existing.scalar_one_or_none():
            return False
        
        # Проверяем, есть ли запись с другими полями
        result = await session.execute(
            select(AllowedUser).where(
                (AllowedUser.telegram_id == user_id) |
                (AllowedUser.max_id == user_id) |
                (AllowedUser.vk_id == user_id)
            )
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Обновляем существующую запись
            setattr(user, f"{platform}_id", user_id)
            await session.commit()
            return True
        else:
            # Создаем новую запись
            new_user = AllowedUser(**{f"{platform}_id": user_id})
            session.add(new_user)
            await session.commit()
            return True

async def remove_user(platform: str, user_id: int) -> bool:
    """Удаление пользователя для конкретной платформы"""
    async with async_session() as session:
        field = getattr(AllowedUser, f"{platform}_id")
        result = await session.execute(
            delete(AllowedUser).where(field == user_id)
        )
        await session.commit()
        return result.rowcount > 0

async def get_all_users(platform: str) -> list[int]:
    """Получение всех ID пользователей для конкретной платформы"""
    async with async_session() as session:
        field = getattr(AllowedUser, f"{platform}_id")
        result = await session.execute(
            select(AllowedUser).where(field.isnot(None))
        )
        users = result.scalars().all()
        return [getattr(user, f"{platform}_id") for user in users]

# ========== РАБОТА С ЧАТАМИ ==========

async def add_chat(platform: str, chat_id: int, chat_name: str = None) -> bool:
    """Добавление чата для конкретной платформы"""
    async with async_session() as session:
        field = getattr(ForwardChat, f"{platform}_chat_id")
        
        # Проверяем существование
        existing = await session.execute(
            select(ForwardChat).where(field == chat_id)
        )
        if existing.scalar_one_or_none():
            return False
        
        # Проверяем, есть ли запись с другими полями
        result = await session.execute(
            select(ForwardChat).where(
                (ForwardChat.telegram_chat_id == chat_id) |
                (ForwardChat.max_chat_id == chat_id) |
                (ForwardChat.vk_chat_id == chat_id)
            )
        )
        chat = result.scalar_one_or_none()
        
        if chat:
            # Обновляем существующую запись
            setattr(chat, f"{platform}_chat_id", chat_id)
            if chat_name:
                chat.chat_name = chat_name
            await session.commit()
            return True
        else:
            # Создаем новую запись
            new_chat = ForwardChat(**{f"{platform}_chat_id": chat_id, "chat_name": chat_name})
            session.add(new_chat)
            await session.commit()
            return True

async def remove_chat(platform: str, chat_id: int) -> bool:
    """Удаление чата для конкретной платформы"""
    async with async_session() as session:
        field = getattr(ForwardChat, f"{platform}_chat_id")
        result = await session.execute(
            delete(ForwardChat).where(field == chat_id)
        )
        await session.commit()
        return result.rowcount > 0

async def toggle_chat(platform: str, chat_id: int, active: bool) -> bool:
    """Включение/выключение чата"""
    async with async_session() as session:
        field = getattr(ForwardChat, f"{platform}_chat_id")
        result = await session.execute(
            select(ForwardChat).where(field == chat_id)
        )
        chat = result.scalar_one_or_none()
        if not chat:
            return False
        
        chat.is_active = 1 if active else 0
        await session.commit()
        return True

async def get_active_chats(platform: str) -> list[tuple[int, str]]:
    """Получение активных чатов для конкретной платформы"""
    async with async_session() as session:
        field = getattr(ForwardChat, f"{platform}_chat_id")
        result = await session.execute(
            select(ForwardChat).where(
                (ForwardChat.is_active == 1) &
                (field.isnot(None))
            )
        )
        chats = result.scalars().all()
        return [(getattr(chat, f"{platform}_chat_id"), chat.chat_name or f"Chat {getattr(chat, f'{platform}_chat_id')}") for chat in chats]

async def get_all_chats(platform: str) -> list[tuple[int, str, bool]]:
    """Получение всех чатов для конкретной платформы"""
    async with async_session() as session:
        field = getattr(ForwardChat, f"{platform}_chat_id")
        result = await session.execute(
            select(ForwardChat).where(field.isnot(None))
        )
        chats = result.scalars().all()
        return [(getattr(chat, f"{platform}_chat_id"), chat.chat_name or f"Chat {getattr(chat, f'{platform}_chat_id')}", bool(chat.is_active)) for chat in chats]