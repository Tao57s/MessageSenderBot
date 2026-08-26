import os
import asyncio
import vk_api
import signal
import sys
from types import SimpleNamespace
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from dotenv import load_dotenv
from database import (
    init_db, is_allowed, add_user, remove_user, get_all_users,
    add_chat, remove_chat, toggle_chat, get_active_chats, get_all_chats
)

load_dotenv()

# Основной asyncio loop (устанавливается Run.py перед запуском longpoll)
MAIN_LOOP = None

# ========== НАСТРОЙКИ ==========
VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN")
ADMIN_VK_ID = int(os.getenv("ADMIN_VK_ID", 0))
VK_API_VERSION = os.getenv("VK_API_VERSION")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", 0))

if not VK_GROUP_TOKEN:
    raise ValueError("❌ VK_GROUP_TOKEN не найден!")
if not ADMIN_VK_ID:
    raise ValueError("❌ ADMIN_VK_ID не найден!")
if not VK_GROUP_ID:
    raise ValueError("❌ VK_GROUP_ID не найден!")

PLATFORM = "vk"


# ========== КЛИЕНТ ДЛЯ VK ==========
class VKBot:
    def __init__(self, token: str, api_version: str, group_id: int):
        self.token = token
        self.api_version = api_version
        self.group_id = group_id
        self.vk_session = None
        self.vk = None
        self.longpoll = None
    
    def init(self):
        """Инициализация VK сессии"""
        try:
            self.vk_session = vk_api.VkApi(token=self.token)
            self.vk = self.vk_session.get_api()
            self.longpoll = VkBotLongPoll(self.vk_session, self.group_id)
            return self
        except Exception as e:
            print(f"❌ Ошибка инициализации VK: {e}")
            return None
    
    def send_message(self, user_id: int, text: str, attachment: str = None):
        """Отправка сообщения в VK"""
        params = {
            'user_id': user_id,
            'message': text,
            'random_id': 0
        }
        if attachment:
            params['attachment'] = attachment
        return self.vk.messages.send(**params)
    
    def forward_message(self, peer_id: int, from_peer_id: int, message_id: int):
        """Пересылка сообщения методом VK forward.

        peer_id - целевой peer_id (куда переслать),
        from_peer_id - исходный peer_id (откуда переслать),
        message_id - id сообщения в исходном диалоге.
        """
        # Используем параметр forward_messages и from_peer_id
        return self.vk.messages.send(
            peer_id=peer_id,
            forward_messages=str(message_id),
            from_peer_id=from_peer_id,
            random_id=0
        )

    def forward_message_to_chat_with_attachments(self, user_message, user_id, target_chat_id, attachments=None):
        """
        Пересылает сообщение с вложениями в указанную беседу

        Args:
            user_message (str): Текст сообщения
            user_id (int): ID пользователя
            target_chat_id (int): ID беседы для пересылки
            attachments (list): Список вложений из события
        """

        # Получаем имя пользователя
        try:
            user = self.vk.users.get(user_ids=user_id)[0]
            user_name = f"{user['first_name']} {user['last_name']}"
        except Exception:
            user_name = f"Пользователь {user_id}"

        # Формируем текст сообщения
        message_text = f"📨 От {user_name}:\n{user_message}"

        # Обработка вложений
        attachment_strings = []
        if attachments:
            for attachment in attachments:
                try:
                    atype = attachment.get('type')
                    if atype == 'photo':
                        photo = attachment['photo']
                        attachment_str = f"photo{photo['owner_id']}_{photo['id']}"
                        attachment_strings.append(attachment_str)
                    elif atype == 'video':
                        video = attachment['video']
                        attachment_str = f"video{video['owner_id']}_{video['id']}"
                        attachment_strings.append(attachment_str)
                    elif atype == 'doc':
                        doc = attachment['doc']
                        attachment_str = f"doc{doc['owner_id']}_{doc['id']}"
                        attachment_strings.append(attachment_str)
                    elif atype == 'audio':
                        audio = attachment['audio']
                        attachment_str = f"audio{audio['owner_id']}_{audio['id']}"
                        attachment_strings.append(attachment_str)
                    elif atype == 'wall':
                        wall = attachment['wall']
                        attachment_str = f"wall{wall['owner_id']}_{wall['id']}"
                        attachment_strings.append(attachment_str)
                except Exception:
                    continue

        # Отправляем в целевой чат
        try:
            params = {
                'peer_id': target_chat_id,
                'message': message_text,
                'random_id': 0
            }
            if attachment_strings:
                params['attachment'] = ','.join(attachment_strings)

            self.vk.messages.send(**params)
            print(f"✅ Сообщение от {user_name} переслано в чат {target_chat_id}")
            return True
        except Exception as e:
            print(f"❌ Ошибка при пересылке: {e}")
            raise


    def get_chat_info(self, peer_id: int):
        """Получение информации о чате"""
        return self.vk.messages.getConversationsById(peer_ids=peer_id)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
vk_bot = None

# Пытаемся инициализировать VK бота сразу
try:
    vk_bot = VKBot(VK_GROUP_TOKEN, VK_API_VERSION, VK_GROUP_ID).init()
    if vk_bot != None:
        print("✅ VK бот инициализирован успешно")
    else:
        print("❌ Ошибка инициализации VK бота")
except Exception as e:
    print(f"❌ Ошибка инициализации VK: {e}")
    
#============ проверка на права администратора =========

def check_admin(user_id, vk_bot_instance):
    if user_id != ADMIN_VK_ID:
        vk_bot_instance.send_message(user_id, "❌ Только Администратор может использовать данные команды.")
        return False
    return True

#============ проверка на наличие пользователя в бд ===============
def allowed_check(user_id):
    if MAIN_LOOP:
        return asyncio.run_coroutine_threadsafe(is_allowed(PLATFORM, user_id), MAIN_LOOP).result()
    else:
        return asyncio.run(is_allowed(PLATFORM, user_id))

    # ========== ОБРАБОТЧИК КОМАНД ==========
def cmd_start(event, vk_bot_instance):
    """Обработка команды /start"""
    user_id = event.user_id
    # Проверяем через основной asyncio loop, если он установлен
    vk_bot_instance.send_message(
            user_id,
            "✅ Вы в белом списке!\n\n"
            "📤 Отправляйте сообщения, и я перешлю их во все активные чаты.\n\n"
            "🔧 Команды для админа:\n"
            "/add_user <ID> - добавить пользователя\n"
            "/remove_user <ID> - удалить пользователя\n"
            "/list_users - список пользователей\n"
            "/add_chat <ID> [название] - добавить чат\n"
            "/peer_id - показать реальный peer_id текущего диалога\n"
            "/remove_chat <ID> - удалить чат\n"
            "/toggle_chat <ID> - включить/выключить чат\n"
            "/list_chats - список чатов"
        )    
    
def cmd_add_user(event, vk_bot_instance):
    """Обработка команды /add_user"""
    user_id = event.user_id

    if not check_admin(user_id, vk_bot_instance):
        return

    command_parts = event.text.split()
    if len(command_parts) < 2:
        vk_bot_instance.send_message(user_id, "ℹ️ Использование: /add_user <ID>")
        return
    try:

        new_user_id = int(command_parts[1])
        
        allowed = allowed_check(new_user_id)

        if not allowed:
            if MAIN_LOOP:
                result = asyncio.run_coroutine_threadsafe(add_user(PLATFORM, new_user_id), MAIN_LOOP).result()
            else:
                result = asyncio.run(add_user(PLATFORM, new_user_id))
        
            vk_bot_instance.send_message(user_id, f"✅ Пользователь {new_user_id} добавлен!")
            return

        vk_bot_instance.send_message(user_id, f"⚠️ Пользователь {new_user_id} уже в белом списке.")

    except ValueError:
        vk_bot_instance.send_message(user_id, "❌ ID должен быть числом.")
        


def cmd_remove_user(event, vk_bot_instance):
    """Обработка команды /remove_user"""

    user_id = event.user_id

    if not check_admin(user_id, vk_bot_instance):
        return

    command_parts = event.text.split()
    if len(command_parts) < 2:
        vk_bot_instance.send_message(user_id, "ℹ️ Использование: /remove_user <ID>")
        return
    try:
        remove_user_id = int(command_parts[1])
        allowed = allowed_check(remove_user_id)

        if not allowed:
            vk_bot_instance.send_message(user_id, f"❌ Пользователь {remove_user_id} не найден.")
            return

        if MAIN_LOOP:
            result = asyncio.run_coroutine_threadsafe(remove_user(PLATFORM, remove_user_id), MAIN_LOOP).result()
        else:
            result = asyncio.run(remove_user(PLATFORM, remove_user_id))
        
        vk_bot_instance.send_message(user_id, f"✅ Пользователь {remove_user_id} удалён.")

    except ValueError:
        vk_bot_instance.send_message(user_id, "❌ ID должен быть числом.")

def cmd_list_users(event, vk_bot_instance):
    """Обработка команды /list_users"""
    user_id = event.user_id

    if not check_admin(user_id, vk_bot_instance):
        return

    if MAIN_LOOP:
        users = asyncio.run_coroutine_threadsafe(get_all_users(PLATFORM), MAIN_LOOP).result()
    else:
        users = asyncio.run(get_all_users(PLATFORM))

    if not users:
        vk_bot_instance.send_message(user_id, "📭 Белый список пуст.")
    else:
        users_text = "\n".join([f"• {uid}" for uid in users])
        vk_bot_instance.send_message(user_id, f"📋 Разрешённые пользователи:\n{users_text}")

def cmd_add_chat(event, vk_bot_instance):
    """Обработчик команды /add_chat"""
    user_id = event.user_id

    if not check_admin(user_id, vk_bot_instance):
        return

    command_parts = event.text.split(maxsplit=2)
    if len(command_parts) < 2:
        vk_bot_instance.send_message(user_id,
            "ℹ️ Использование: /add_chat <ID_чата> [название]\nПример: /add_chat -1001234567890 Моя группа")
        return

    try:
        chat_id = int(command_parts[1])
        chat_name = command_parts[2] if len(command_parts) > 2 else None

        if MAIN_LOOP:
            result = asyncio.run_coroutine_threadsafe(add_chat(PLATFORM, chat_id, chat_name), MAIN_LOOP).result()
        else:
            result = asyncio.run(add_chat(PLATFORM, chat_id, chat_name))

        if result:
            vk_bot_instance.send_message(user_id, f"✅ Чат {chat_id} добавлен для пересылки!")
        else:
            vk_bot_instance.send_message(user_id, f"⚠️ Чат {chat_id} уже есть в списке.")
    except ValueError:
        vk_bot_instance.send_message(user_id, "❌ ID чата должен быть числом.")


def cmd_get_peer_id(event, vk_bot_instance):
    """Вывод реального peer_id текущего диалога VK."""
    message = f"ℹ️ Реальный peer_id этого диалога: {event.peer_id}"
    if event.peer_id == event.user_id:
        vk_bot_instance.send_message(event.user_id, message)
    else:
        vk_bot_instance.vk.messages.send(
            peer_id=event.peer_id,
            message=message,
            random_id=0
        )


def cmd_remove_chat(event, vk_bot_instance):
    """Обработчик команды /remove_chat"""
    user_id = event.user_id

    if not check_admin(user_id, vk_bot_instance):
        return

    command_parts = event.text.split()
    if len(command_parts) < 2:
        vk_bot_instance.send_message(user_id, "ℹ️ Использование: /remove_chat <ID_чата>")
        return

    try:
        chat_id = int(command_parts[1])
        if MAIN_LOOP:
            result = asyncio.run_coroutine_threadsafe(remove_chat(PLATFORM, chat_id), MAIN_LOOP).result()
        else:
            result = asyncio.run(remove_chat(PLATFORM, chat_id))

        if result:
            vk_bot_instance.send_message(user_id, f"✅ Чат {chat_id} удалён из списка.")
        else:
            vk_bot_instance.send_message(user_id, f"❌ Чат {chat_id} не найден.")
    except ValueError:
        vk_bot_instance.send_message(user_id, "❌ ID чата должен быть числом.")


def cmd_toggle_chat(event, vk_bot_instance):
    """Обработчик команды /toggle_chat"""
    user_id = event.user_id

    if not check_admin(user_id, vk_bot_instance):
        return

    command_parts = event.text.split()
    if len(command_parts) < 2:
        vk_bot_instance.send_message(user_id, "ℹ️ Использование: /toggle_chat <ID_чата>")
        return

    try:
        chat_id = int(command_parts[1])

        if MAIN_LOOP:
            chats = asyncio.run_coroutine_threadsafe(get_all_chats(PLATFORM), MAIN_LOOP).result()
        else:
            chats = asyncio.run(get_all_chats(PLATFORM))

        chat_exists = any(c[0] == chat_id for c in chats)
        if not chat_exists:
            vk_bot_instance.send_message(user_id, f"❌ Чат {chat_id} не найден.")
            return

        if MAIN_LOOP:
            result = asyncio.run_coroutine_threadsafe(toggle_chat(PLATFORM, chat_id), MAIN_LOOP).result()
        else:
            result = asyncio.run(toggle_chat(PLATFORM, chat_id))

        if result:
            vk_bot_instance.send_message(user_id, f"✅ Статус чата {chat_id} изменён.")
        else:
            vk_bot_instance.send_message(user_id, f"❌ Не удалось изменить статус чата {chat_id}.")
    except ValueError:
        vk_bot_instance.send_message(user_id, "❌ ID чата должен быть числом.")


def cmd_list_chats(event, vk_bot_instance):
    """Обработчик команды /list_chats"""
    user_id = event.user_id

    if not check_admin(user_id, vk_bot_instance):
        return

    if MAIN_LOOP:
        chats = asyncio.run_coroutine_threadsafe(get_all_chats(PLATFORM), MAIN_LOOP).result()
    else:
        chats = asyncio.run(get_all_chats(PLATFORM))

    if not chats:
        vk_bot_instance.send_message(user_id, "📭 Список чатов пуст.")
        return

    lines = []
    for cid, name, is_active in chats:
        status = "активен" if is_active else "выключен"
        display_name = name if name else str(cid)
        lines.append(f"• {display_name} (ID: {cid}) — {status}")

    vk_bot_instance.send_message(user_id, "📋 Чаты для пересылки:\n" + "\n".join(lines))

    



def forward_message_to_chats(event, vk_bot_instance):
    """Пересылка сообщения в активные чаты"""
    user_id = getattr(event, 'user_id', None)
    peer_id = getattr(event, 'peer_id', user_id)
    message_text = getattr(event, 'text', '')
    attachments = getattr(event, 'attachments', None)

    if user_id is None:
        return

    if MAIN_LOOP:
        allowed = asyncio.run_coroutine_threadsafe(is_allowed(PLATFORM, user_id), MAIN_LOOP).result()
    else:
        allowed = asyncio.run(is_allowed(PLATFORM, user_id))
    if not allowed:
        vk_bot_instance.send_message(peer_id, "❌ У вас нет прав на использование этого бота.")
        return

    if MAIN_LOOP:
        active_chats = asyncio.run_coroutine_threadsafe(get_active_chats(PLATFORM), MAIN_LOOP).result()
    else:
        active_chats = asyncio.run(get_active_chats(PLATFORM))

    if not active_chats:
        vk_bot_instance.send_message(peer_id, "⚠️ Нет активных чатов для пересылки. Добавьте чат через /add_chat")
        return

    success_count = 0
    error_chats = []

    for chat_id, chat_name in active_chats:
        try:
            # Убедимся, что передаём корректный peer_id в VK: для бесед добавляем 2_000_000_000
            target_peer_id = chat_id if chat_id >= 2000000000 else (2000000000 + chat_id)

            print(
                f"🔎 Проверка VK-чата: db_chat_id={chat_id}, "
                f"target_peer_id={target_peer_id}, name={chat_name}"
            )
            try:
                chat_info = vk_bot_instance.vk.messages.getConversationsById(
                    peer_ids=target_peer_id
                )
                print(f"✅ Доступ к чату подтверждён: {chat_info}")
            except Exception as check_error:
                print(f"❌ Проверка доступа к чату завершилась ошибкой: {check_error}")

            # Отправляем новое сообщение, чтобы не требовать доступа к исходному диалогу.
            vk_bot_instance.forward_message_to_chat_with_attachments(
                message_text or '', user_id, target_peer_id, attachments
            )
            success_count += 1
        except Exception as e:
            # Если ошибка доступа (917) — сообщаем администратору, что бот не добавлен в беседу
            err_text = str(e)
            error_chats.append(f"{chat_name} (ID: {chat_id}) - {err_text[:200]}")
            if "917" in err_text or "You don't have access" in err_text:
                try:
                    vk_bot_instance.send_message(ADMIN_VK_ID, f"⚠️ Нет доступа к чату {chat_name} (ID: {chat_id}). Добавьте бота в беседу или используйте правильный peer_id.")
                except Exception:
                    pass

    if success_count > 0:
        report = f"✅ Переслано в {success_count} чатов"
        if error_chats:
            report += f"\n\n⚠️ Ошибки:\n" + "\n".join(error_chats)
        vk_bot_instance.send_message(user_id, report)
    else:
        vk_bot_instance.send_message(
            user_id,
            f"❌ Не удалось переслать ни в один чат.\n\nОшибки:\n" + "\n".join(error_chats)
        )

    return
    
    
# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
def normalize_vk_event(event):
    """Преобразует событие Bot Long Poll в формат текущих обработчиков."""
    message = event.message or event.object
    print(
        f"📥 VK MESSAGE_NEW: peer_id={message.peer_id}, "
        f"from_id={message.from_id}, message_id={message.id}, "
        f"text={message.text!r}, attachments={len(message.attachments or [])}"
    )
    return SimpleNamespace(
        user_id=message.from_id,
        peer_id=message.peer_id,
        text=message.text or "",
        attachments=message.attachments,
        message_id=message.id,
    )


def handle_vk_message(event, vk_bot_instance):
    """Обработка входящего сообщения из VK"""
    event = normalize_vk_event(event)
    user_id = event.user_id
    message_text = event.text
    attachments = event.attachments if hasattr(event, 'attachments') else None
    
    if not message_text and not attachments:
        return True
    
    allowed = allowed_check(user_id)

    if not allowed:
        vk_bot_instance.send_message(user_id, "❌ У вас нет прав. Обратитесь к администратору.")


    # Проверка на команды
    if message_text and message_text.startswith("/"):
        # Обработка команд как в телеграм
        command_parts = message_text.split()
        command = command_parts[0].lower()
        
        # Обработка команды через встроенный разбор
        if command == "/start":
            cmd_start(event, vk_bot_instance)
        elif command == "/add_user":
            cmd_add_user(event, vk_bot_instance)
        elif command == "/remove_user":
            cmd_remove_user(event, vk_bot_instance)
        elif command == "/list_users":
            cmd_list_users(event, vk_bot_instance)
        elif command == "/add_chat":
            cmd_add_chat(event, vk_bot_instance)
        elif command in ("/peer_id", "/get_peer_id"):
            cmd_get_peer_id(event, vk_bot_instance)
        elif command == "/remove_chat":
            cmd_remove_chat(event, vk_bot_instance)
        elif command == "/toggle_chat":
            cmd_toggle_chat(event, vk_bot_instance)
        elif command == "/list_chats":
            cmd_list_chats(event, vk_bot_instance)
        else:
            vk_bot_instance.send_message(event.user_id, "❌ Неизвестная команда.")
    else:
        if event.peer_id != user_id:
            print(
                f"⏭️ Пересылка пропущена: сообщение пришло из беседы "
                f"peer_id={event.peer_id}, а не из личного диалога"
            )
            return True
        forward_message_to_chats(event, vk_bot_instance)
#     """Обработка входящего сообщения из VK"""
#     user_id = event.user_id
#     peer_id = event.peer_id
#     message_text = event.text
    
#     if not message_text:
#         return True
    
#     # Проверка на команды
#     if message_text.startswith("/"):
#         # Обработка команд как в телеграм
#         command_parts = message_text.split()
#         command = command_parts[0].lower()
        
#         if command == "/start":
#             # Проверяем через основной asyncio loop, если он установлен
#             if MAIN_LOOP:
#                 allowed = asyncio.run_coroutine_threadsafe(is_allowed(PLATFORM, user_id), MAIN_LOOP).result()
#             else:
#                 allowed = asyncio.run(is_allowed(PLATFORM, user_id))
#             if allowed:
#                 vk_bot_instance.send_message(
#                     peer_id,
#                     "✅ Вы в белом списке!\n\n"
#                     "📤 Отправляйте сообщения, и я перешлю их во все активные чаты.\n\n"
#                     "🔧 Команды для админа:\n"
#                     "/add_user <ID> - добавить пользователя\n"
#                     "/remove_user <ID> - удалить пользователя\n"
#                     "/list_users - список пользователей\n"
#                     "/add_chat <ID> [название] - добавить чат\n"
#                     "/remove_chat <ID> - удалить чат\n"
#                     "/toggle_chat <ID> - включить/выключить чат\n"
#                     "/list_chats - список чатов"
#                 )
#             else:
#                 vk_bot_instance.send_message(peer_id, "❌ У вас нет прав. Обратитесь к администратору.")
#             return True
        
#         # Админские команды
#         if user_id == ADMIN_VK_ID:
#             if command == "/add_user":
#                 parts = command_parts
#                 if len(parts) >= 2:
#                     try:
#                         new_user_id = int(parts[1])
#                         if MAIN_LOOP:
#                             result = asyncio.run_coroutine_threadsafe(add_user(PLATFORM, new_user_id), MAIN_LOOP).result()
#                         else:
#                             result = asyncio.run(add_user(PLATFORM, new_user_id))
#                         if result:
#                             vk_bot_instance.send_message(peer_id, f"✅ Пользователь {new_user_id} добавлен!")
#                         else:
#                             vk_bot_instance.send_message(peer_id, f"⚠️ Пользователь {new_user_id} уже в списке.")
#                     except ValueError:
#                         vk_bot_instance.send_message(peer_id, "❌ ID должен быть числом.")
#                 else:
#                     vk_bot_instance.send_message(peer_id, "ℹ️ Использование: /add_user <ID>")
#                 return True
            
#             elif command == "/remove_user":
#                 parts = command_parts
#                 if len(parts) >= 2:
#                     try:
#                         remove_user_id = int(parts[1])
#                         if MAIN_LOOP:
#                             result = asyncio.run_coroutine_threadsafe(remove_user(PLATFORM, remove_user_id), MAIN_LOOP).result()
#                         else:
#                             result = asyncio.run(remove_user(PLATFORM, remove_user_id))
#                         if result:
#                             vk_bot_instance.send_message(peer_id, f"✅ Пользователь {remove_user_id} удалён.")
#                         else:
#                             vk_bot_instance.send_message(peer_id, f"❌ Пользователь {remove_user_id} не найден.")
#                     except ValueError:
#                         vk_bot_instance.send_message(peer_id, "❌ ID должен быть числом.")
#                 else:
#                     vk_bot_instance.send_message(peer_id, "ℹ️ Использование: /remove_user <ID>")
#                 return True
            
#             elif command == "/list_users":
#                 if MAIN_LOOP:
#                     users = asyncio.run_coroutine_threadsafe(get_all_users(PLATFORM), MAIN_LOOP).result()
#                 else:
#                     users = asyncio.run(get_all_users(PLATFORM))
#                 if not users:
#                     vk_bot_instance.send_message(peer_id, "📭 Белый список пуст.")
#                 else:
#                     users_text = "\n".join([f"• {uid}" for uid in users])
#                     vk_bot_instance.send_message(peer_id, f"📋 Разрешённые пользователи:\n{users_text}")
#                 return True
            
#             elif command == "/add_chat":
#                 parts = command_parts
#                 if len(parts) >= 2:
#                     try:
#                         chat_id = int(parts[1])
#                         chat_name = parts[2] if len(parts) > 2 else None
#                         if MAIN_LOOP:
#                             result = asyncio.run_coroutine_threadsafe(add_chat(PLATFORM, chat_id, chat_name), MAIN_LOOP).result()
#                         else:
#                             result = asyncio.run(add_chat(PLATFORM, chat_id, chat_name))
#                         if result:
#                             vk_bot_instance.send_message(peer_id, f"✅ Чат {chat_id} добавлен для пересылки!")
#                         else:
#                             vk_bot_instance.send_message(peer_id, f"⚠️ Чат {chat_id} уже есть в списке.")
#                     except ValueError:
#                         vk_bot_instance.send_message(peer_id, "❌ ID чата должен быть числом.")
#                 else:
#                     vk_bot_instance.send_message(peer_id, "ℹ️ Использование: /add_chat <ID> [название]")
#                 return True
            
#             elif command == "/remove_chat":
#                 parts = command_parts
#                 if len(parts) >= 2:
#                     try:
#                         chat_id = int(parts[1])
#                         if MAIN_LOOP:
#                             result = asyncio.run_coroutine_threadsafe(remove_chat(PLATFORM, chat_id), MAIN_LOOP).result()
#                         else:
#                             result = asyncio.run(remove_chat(PLATFORM, chat_id))
#                         if result:
#                             vk_bot_instance.send_message(peer_id, f"✅ Чат {chat_id} удалён из списка.")
#                         else:
#                             vk_bot_instance.send_message(peer_id, f"❌ Чат {chat_id} не найден.")
#                     except ValueError:
#                         vk_bot_instance.send_message(peer_id, "❌ ID чата должен быть числом.")
#                 else:
#                     vk_bot_instance.send_message(peer_id, "ℹ️ Использование: /remove_chat <ID>")
#                 return True
            
#             elif command == "/toggle_chat":
#                 parts = command_parts
#                 if len(parts) >= 2:
#                     try:
#                         chat_id = int(parts[1])
#                         if MAIN_LOOP:
#                             chats = asyncio.run_coroutine_threadsafe(get_all_chats(PLATFORM), MAIN_LOOP).result()
#                         else:
#                             chats = asyncio.run(get_all_chats(PLATFORM))
#                         chat_exists = any(c[0] == chat_id for c in chats)
                        
#                         if not chat_exists:
#                             vk_bot_instance.send_message(peer_id, f"❌ Чат {chat_id} не найден.")
#                             return True
                        
#                         for c_id, _, is_active in chats:
#                             if c_id == chat_id:
#                                 new_status = not is_active
#                                 break
                        
#                         if MAIN_LOOP:
#                             result = asyncio.run_coroutine_threadsafe(toggle_chat(PLATFORM, chat_id, new_status), MAIN_LOOP).result()
#                         else:
#                             result = asyncio.run(toggle_chat(PLATFORM, chat_id, new_status))
#                         if result:
#                             status_text = "включён" if new_status else "выключен"
#                             vk_bot_instance.send_message(peer_id, f"✅ Чат {chat_id} {status_text}.")
#                         else:
#                             vk_bot_instance.send_message(peer_id, f"❌ Ошибка при изменении статуса чата.")
#                     except ValueError:
#                         vk_bot_instance.send_message(peer_id, "❌ ID чата должен быть числом.")
#                 else:
#                     vk_bot_instance.send_message(peer_id, "ℹ️ Использование: /toggle_chat <ID>")
#                 return True
#             elif command == "/list_chats":
#                 if MAIN_LOOP:
#                     chats = asyncio.run_coroutine_threadsafe(get_all_chats(PLATFORM), MAIN_LOOP).result()
#                 else:
#                     chats = asyncio.run(get_all_chats(PLATFORM))
#                 if not chats:
#                     vk_bot_instance.send_message(peer_id, "📭 Список чатов пуст.")
#                 else:
#                     chats_text = []
#                     for chat_id, name, is_active in chats:
#                         status = "🟢 Активен" if is_active else "🔴 Неактивен"
#                         chats_text.append(f"• {name}\n  ID: {chat_id}\n  Статус: {status}")
#                     vk_bot_instance.send_message(
#                         peer_id,
#                         f"📋 Список чатов для пересылки:\n\n" + "\n".join(chats_text)
#                     )
#                 return True
        
#         return False
    
#     # Если не команда - пересылаем
#     return forward_vk_message(event, vk_bot_instance)

# def forward_vk_message(event, vk_bot_instance):
#     """Пересылка сообщения в активные чаты"""
#     user_id = event.user_id
    
#     if MAIN_LOOP:
#         allowed = asyncio.run_coroutine_threadsafe(is_allowed(PLATFORM, user_id), MAIN_LOOP).result()
#     else:
#         allowed = asyncio.run(is_allowed(PLATFORM, user_id))
#     if not allowed:
#         vk_bot_instance.send_message(event.peer_id, "❌ У вас нет прав на использование этого бота.")
#         return True
    
#     if MAIN_LOOP:
#         active_chats = asyncio.run_coroutine_threadsafe(get_active_chats(PLATFORM), MAIN_LOOP).result()
#     else:
#         active_chats = asyncio.run(get_active_chats(PLATFORM))
    
#     if not active_chats:
#         vk_bot_instance.send_message(event.peer_id, "⚠️ Нет активных чатов для пересылки. Добавьте чат через /add_chat")
#         return True
    
#     success_count = 0
#     error_chats = []
    
#     for chat_id, chat_name in active_chats:
#         try:
#             # Пересылка сообщения
#             vk_bot_instance.forward_message(
#                 peer_id=chat_id,
#                 from_peer_id=event.peer_id,
#                 message_id=event.message_id
#             )
#             success_count += 1
#         except Exception as e:
#             error_chats.append(f"{chat_name} (ID: {chat_id}) - {str(e)[:50]}")
    
#     if success_count > 0:
#         report = f"✅ Переслано в {success_count} чатов"
#         if error_chats:
#             report += f"\n\n⚠️ Ошибки:\n" + "\n".join(error_chats)
#         vk_bot_instance.send_message(event.peer_id, report)
#     else:
#         vk_bot_instance.send_message(
#             event.peer_id,
#             f"❌ Не удалось переслать ни в один чат.\n\nОшибки:\n" + "\n".join(error_chats)
#         )
    
#     return True

# ========== ЗАПУСК (если запускается отдельно) ==========
def signal_handler(sig, frame):
    """Обработчик сигнала прерывания"""
    print("\n🛑 Получен сигнал остановки. Завершаем работу...")
    sys.exit(0)

# Регистрируем обработчик Ctrl+C
signal.signal(signal.SIGINT, signal_handler)


async def main_vk():
    """Запуск VK бота отдельно"""
    await init_db()

    print("🤖 VK бот запущен!")
    print(f"👥 Админ: {ADMIN_VK_ID}")
    
    print("🔄 Слушаем сообщения VK...")

    try:
        for event in vk_bot.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                 handle_vk_message(event, vk_bot)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main_vk())