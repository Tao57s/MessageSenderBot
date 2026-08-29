#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Multi-Platform Message Forwarding Bot System
Единый запуск всех ботов (Telegram, Max, VK)
"""

import os
import sys
import asyncio
from aiohttp import ClientError
import signal
import logging
from datetime import datetime
from dotenv import load_dotenv

# Импорт общих модулей
from database import init_db, add_user, get_active_chats

# Импорт ботов
from TelegramBot import (
    bot as telegram_bot,
    dp as telegram_dp,
    PLATFORM as TG_PLATFORM,
    ADMIN_TELEGRAM_ID,
)
from MaxBot import (
    bot as max_bot,
    dp as max_dp,
    PLATFORM as MAX_PLATFORM,
    ADMIN_MAX_ID,
)
from VkBot import vk_bot, PLATFORM as VK_PLATFORM, ADMIN_VK_ID

# Настройка логирования
# Попробуем принудительно перевести stdout в UTF-8, чтобы избежать ошибок
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    # reconfigure может быть недоступен в некоторых окружениях — игнорируем
    pass

# Создаём обработчики логирования с указанием кодировки для файла
file_handler = logging.FileHandler(
    os.getenv('LOG_FILE', 'bot_system.log'),
    encoding='utf-8'
)
stream_handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger(__name__)

load_dotenv()

# ========== НАСТРОЙКИ ==========
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM_BOT", "true").lower() == "true"
ENABLE_MAX = os.getenv("ENABLE_MAX_BOT", "true").lower() == "true"
ENABLE_VK = os.getenv("ENABLE_VK_BOT", "true").lower() == "true"

# ========== КЛАСС ДЛЯ УПРАВЛЕНИЯ БОТАМИ ==========

class BotManager:
    """Менеджер для управления всеми ботами"""
    
    def __init__(self):
        self.bots = {}
        self.tasks = []
        self.shutdown_event = asyncio.Event()
        self.start_time = datetime.now()
        
    async def initialize(self):
        """Инициализация всех компонентов"""
        logger.info("🚀 Инициализация системы...")
        
        # Инициализация БД
        await init_db()
        logger.info("✅ База данных инициализирована")

        # Администраторы должны быть доступны сразу после запуска,
        # иначе они не смогут пользоваться командами до ручного добавления.
        admins = (
            (TG_PLATFORM, ADMIN_TELEGRAM_ID),
            (MAX_PLATFORM, ADMIN_MAX_ID),
            (VK_PLATFORM, ADMIN_VK_ID),
        )
        for platform, admin_id in admins:
            added = await add_user(platform, admin_id)
            if added:
                logger.info(f"✅ Администратор {admin_id} добавлен в БД ({platform})")
            else:
                logger.info(f"ℹ️ Администратор {admin_id} уже есть в БД ({platform})")
        
        # Регистрация ботов
        if ENABLE_TELEGRAM:
            self.bots['telegram'] = {
                'name': 'Telegram',
                'bot': telegram_bot,
                'dp': telegram_dp,
                'platform': TG_PLATFORM,
                'status': 'ready'
            }
            logger.info("✅ Telegram бот зарегистрирован")
        
        if ENABLE_MAX:
            self.bots['max'] = {
                'name': 'Max',
                'bot': max_bot,
                'dp': max_dp,
                'platform': MAX_PLATFORM,
                'status': 'ready'
            }
            logger.info("✅ Max бот зарегистрирован")
        
        if ENABLE_VK:
            if vk_bot is None:
                raise RuntimeError(
                    "VK бот не инициализирован. Проверьте VK_GROUP_TOKEN, "
                    "VK_GROUP_ID и доступ к API VK."
                )
            self.bots['vk'] = {
                'name': 'VK',
                'bot': vk_bot,
                'platform': VK_PLATFORM,
                'status': 'ready'
            }
            logger.info("✅ VK бот зарегистрирован")
        
        if not self.bots:
            logger.error("❌ Не зарегистрировано ни одного бота!")
            sys.exit(1)
        
        # Вывод информации о чатах
        await self.show_chats_info()
        
        logger.info(f"✅ Система инициализирована. Запущено ботов: {len(self.bots)}")
        
    async def show_chats_info(self):
        """Вывод информации о активных чатах для каждого бота"""
        logger.info("📊 Информация о чатах:")
        
        for bot_key, bot_info in self.bots.items():
            platform = bot_info['platform']
            try:
                chats = await get_active_chats(platform)
                logger.info(f"   📤 {bot_info['name']}: {len(chats)} активных чатов")
                for chat_id, name in chats[:5]:  # Показываем первые 5
                    logger.info(f"      - {name} (ID: {chat_id})")
                if len(chats) > 5:
                    logger.info(f"      ... и еще {len(chats) - 5} чатов")
            except Exception as e:
                logger.error(f"   ❌ {bot_info['name']}: Ошибка получения чатов - {e}")
    
    async def run_telegram_bot(self):
        """Запуск Telegram бота"""
        bot_info = self.bots.get('telegram')
        if not bot_info:
            return
        
        logger.info("🔄 Запуск Telegram бота...")
        try:
            await telegram_dp.start_polling(telegram_bot)
        except (ClientError, asyncio.TimeoutError, OSError) as e:
            # Специальный лог для ошибок подключения к серверам Telegram
            logger.error(f"❌ Не удалось подключиться к серверам Telegram: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Telegram бот остановлен с ошибкой: {e}")
            raise
    
    async def run_max_bot(self):
        """Запуск Max бота"""
        bot_info = self.bots.get('max')
        if not bot_info:
            return
        
        logger.info("🔄 Запуск Max бота...")
        try:
            await max_dp.start_polling(max_bot)
        except Exception as e:
            logger.error(f"❌ Max бот остановлен с ошибкой: {e}")
            raise
    
    async def run_vk_bot(self):
        """Запуск VK бота"""
        bot_info = self.bots.get('vk')
        if not bot_info:
            return
        
        logger.info("🔄 Запуск VK бота...")
        try:
            # Инициализация VK бота уже выполнена в VkBot.py
            # VK longpoll — блокирующая операция. Запускаем слушатель в отдельном потоке,
            # чтобы не блокировать основной asyncio loop. В этом потоке синхронные хендлеры
            # могут использовать asyncio.run() без ошибок вложенного loop.
            from VkBot import vk_bot as vk_instance, MAIN_LOOP as VK_MAIN_LOOP
            # Перед запуском longpoll устанавливаем основной loop в модуле VkBot,
            # чтобы синхронные обработчики могли безопасно планировать
            # выполнение асинхронных корутин в этом loop через
            # asyncio.run_coroutine_threadsafe
            VK_MAIN_LOOP = asyncio.get_running_loop()
            try:
                # Попытка присвоить в модуль
                import VkBot as _vkmod
                _vkmod.MAIN_LOOP = asyncio.get_running_loop()
            except Exception:
                pass
            if vk_instance and vk_instance.longpoll:
                def _vk_listen_loop(vk_inst):
                    from VkBot import VkBotEventType, handle_vk_message
                    for event in vk_inst.longpoll.listen():
                        # Попытка корректно завершить цикл при установке shutdown_event
                        try:
                            if self.shutdown_event.is_set():
                                break
                        except Exception:
                            pass
                        if event.type == VkBotEventType.MESSAGE_NEW:
                            handle_vk_message(event, vk_inst)

                # Запускаем блокирующий слушатель в отдельном потоке
                await asyncio.to_thread(_vk_listen_loop, vk_instance)
            else:
                raise RuntimeError("VK Long Poll не инициализирован.")
        except Exception as e:
            logger.error(f"❌ VK бот остановлен с ошибкой: {e}")
            raise
    
    async def run_all(self):
        """Запуск всех ботов параллельно"""
        logger.info("=" * 60)
        logger.info(f"🤖 ЗАПУСК ВСЕХ БОТОВ")
        logger.info(f"📅 Время запуска: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"📊 Всего ботов: {len(self.bots)}")
        logger.info("=" * 60)
        
        tasks = []
        
        # Создаем задачи для каждого бота
        if 'telegram' in self.bots:
            tasks.append(asyncio.create_task(self.run_telegram_bot()))
        
        if 'max' in self.bots:
            tasks.append(asyncio.create_task(self.run_max_bot()))
        
        if 'vk' in self.bots:
            tasks.append(asyncio.create_task(self.run_vk_bot()))
        
        if not tasks:
            logger.error("❌ Нет задач для выполнения!")
            return
        
        # Ждем завершения любой задачи (или всех)
        try:
            # Используем wait с return_first=True чтобы отслеживать ошибки
            done, pending = await asyncio.wait(
                tasks, 
                return_when=asyncio.FIRST_EXCEPTION
            )
            
            # Проверяем, не было ли ошибок
            for task in done:
                if task.exception():
                    logger.error(f"❌ Бот завершился с ошибкой: {task.exception()}")
                    # Отменяем все остальные задачи
                    for p in pending:
                        p.cancel()
            
            # Ждем отмены всех задач
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
                
        except asyncio.CancelledError:
            logger.info("🛑 Получен сигнал остановки, завершаем работу...")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            raise
        
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("🛑 Завершение работы системы...")
        
        # Устанавливаем флаг остановки
        self.shutdown_event.set()
        
        # Закрываем сессии ботов
        for bot_key, bot_info in self.bots.items():
            try:
                if bot_key == 'telegram':
                    await bot_info['bot'].session.close()
                    logger.info(f"✅ {bot_info['name']} сессия закрыта")
                elif bot_key == 'vk':
                    if bot_info['bot'] and hasattr(bot_info['bot'], 'vk_session'):
                        # VK сессия закрывается автоматически
                        logger.info(f"✅ {bot_info['name']} сессия закрыта")
            except Exception as e:
                logger.error(f"❌ Ошибка при закрытии {bot_info['name']}: {e}")
        
        # Выводим статистику
        uptime = datetime.now() - self.start_time
        logger.info(f"⏱️ Время работы: {uptime}")
        logger.info("👋 Система остановлена")

# ========== ОБРАБОТЧИКИ СИГНАЛОВ ==========

async def signal_handler(signum, frame, manager):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"📡 Получен сигнал {signum}")
    await manager.shutdown()
    sys.exit(0)

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

async def main():
    """Главная функция"""
    # Создаем менеджер
    manager = BotManager()
    
    # Настраиваем обработчики сигналов
    loop = asyncio.get_running_loop()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        try:
            # На Unix-подобных системах работает add_signal_handler
            loop.add_signal_handler(
                sig,
                lambda s=sig, m=manager: asyncio.create_task(signal_handler(s, None, m))
            )
        except NotImplementedError:
            # На Windows (и некоторых loop) add_signal_handler может быть не реализован.
            # В этом случае используем signal.signal и планируем корутину в loop.
            def _sync_handler(signum, frame, m=manager, l=loop):
                l.call_soon_threadsafe(lambda: asyncio.create_task(signal_handler(signum, frame, m)))
            signal.signal(sig, _sync_handler)
            logger.warning(f"⚠️ add_signal_handler недоступен для {sig}; использую signal.signal")
    
    try:
        # Инициализация
        await manager.initialize()
        
        # Запуск всех ботов
        await manager.run_all()
        
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал прерывания")
        await manager.shutdown()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        await manager.shutdown()
        sys.exit(1)

# ========== ТОЧКА ВХОДА ==========

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Программа завершена пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Необработанная ошибка: {e}")
        sys.exit(1)