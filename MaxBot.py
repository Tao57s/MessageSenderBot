import asyncio
import logging
import os
from dotenv import load_dotenv
from maxapi import Bot, Dispatcher, F
from maxapi.enums.format import Format
from maxapi.types import (
    BotStarted,
    Command,
    MessageCreated,
    CallbackButton,
    MessageCallback,
    BotAdded,
    ChatTitleChanged,
    MessageEdited,
    MessageRemoved,
    UserAdded,
    UserRemoved,
    BotStopped,
    DialogCleared,
    DialogMuted,
    DialogUnmuted,
    AttachmentPayload,
    AttachmentUpload,
    ChatButton,  # deprecated: 0.9.14
    MessageChatCreated,  # deprecated: 0.9.14
)

logging.basicConfig(level=logging.INFO)

# Импортируем общую логику БД
from database import (
    init_db, is_allowed, add_user, remove_user, get_all_users,
    add_chat, remove_chat, toggle_chat, get_active_chats, get_all_chats
)

load_dotenv()
# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.getenv("MAX_BOT_TOKEN")
ADMIN_MAX_ID = int(os.getenv("ADMIN_MAX_ID"))

if not BOT_TOKEN:
    raise ValueError("❌ MAX_BOT_TOKEN не найден!")
if not ADMIN_MAX_ID:
    raise ValueError("❌ ADMIN_MAX_ID не найден!")

# ========== НАСТРОЙКА БОТА ==========
PLATFORM = "max"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ========== КОМАНДЫ ==========
@dp.bot_added()
async def on_bot_added(event: BotAdded):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id
    chat = await event.fetch_chat()

    text = (
        f"ID чата/канала куда добавили бота: <{chat.chat_id}>"
    )
    
    print("trigger")

    await bot.send_message(
                user_id=ADMIN_MAX_ID,
                text=text       
            )



@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    from_user = await event.fetch_from_user()
    if await is_allowed(PLATFORM, from_user.user_id):
        await event.message.reply(
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
            "/getid - получение Id чата"
        )
    else:
        await event.message.reply("❌ У вас нет прав. Обратитесь к администратору.")

@dp.message_created(Command("add_user"))
async def cmd_add_user(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id
    
    if user_id != ADMIN_MAX_ID:
        await event.message.reply("❌ Только владелец бота может добавлять пользователей.")
        return
    
    args = event.message.body.text.split()
    
    if len(args) < 2:
        await event.message.reply("ℹ️ Использование: /add_user <ID_пользователя>")
        return
    
    try:
        new_user_id = int(args[1])
        if await add_user(PLATFORM, new_user_id):
            await event.message.reply(f"✅ Пользователь {new_user_id} добавлен!")
        else:
            await event.message.reply(f"⚠️ Пользователь {new_user_id} уже в списке.")
    except ValueError:
        await event.message.reply("❌ ID должен быть числом.")

@dp.message_created(Command("remove_user"))
async def cmd_remove_user(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id

    if user_id != ADMIN_MAX_ID:
        await event.message.reply("❌ Только владелец бота может удалять пользователей.")
        return
    
    args = event.message.body.text.split()
    if len(args) < 2:
        await event.message.reply("ℹ️ Использование: /remove_user <ID_пользователя>")
        return
    
    try:
        remove_user_id = int(args[1])
        if await remove_user(PLATFORM, remove_user_id):
            await event.message.reply(f"✅ Пользователь {remove_user_id} удалён.")
        else:
            await event.message.reply(f"❌ Пользователь {remove_user_id} не найден.")
    except ValueError:
        await event.message.reply("❌ ID должен быть числом.")

@dp.message_created(Command("list_users"))
async def cmd_list_users(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id

    if user_id != ADMIN_MAX_ID:
        await event.message.reply("❌ Только владелец бота может просматривать список.")
        return
    users = await get_all_users(PLATFORM)
    if not users:
        await event.message.reply("📭 Белый список пуст.")
        return
    
    users_text = "\n".join([f"• `{uid}`" for uid in users])
    await event.message.reply(f"📋 Разрешённые пользователи:\n{users_text}", format=Format.MARKDOWN)

@dp.message_created(Command("add_chat"))
async def cmd_add_chat(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id

    if user_id != ADMIN_MAX_ID:
        await event.message.reply("❌ Только владелец бота может добавлять чаты.")
        return

    args = event.message.body.text.split(maxsplit=2)
    if len(args) < 2:
        await event.message.reply(
            "ℹ️ Использование: /add_chat <ID_чата> [название]\n"
            "Пример: /add_chat -1001234567890 Моя группа"
        )
        return
    try:
        chat_id = int(args[1])
        chat_name = args[2] if len(args) > 2 else None
        
        if await add_chat(PLATFORM, chat_id, chat_name):
            await event.message.reply(f"✅ Чат {chat_id} добавлен для пересылки!")
        else:
            await event.message.reply(f"⚠️ Чат {chat_id} уже есть в списке.")
    except ValueError:
        await event.message.reply("❌ ID чата должен быть числом.")


@dp.message_created(Command("remove_chat"))
async def cmd_remove_chat(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id

    if user_id != ADMIN_MAX_ID:
        await event.message.reply("❌ Только владелец бота может удалять пользователей.")
        return

    args = event.message.body.text.split(maxsplit=2)
    if len(args) < 2:
        await event.message.reply("ℹ️ Использование: /remove_chat <ID_чата>")    
        return

    try:
        chat_id = int(args[1])
        if await remove_chat(PLATFORM, chat_id):
            await event.message.reply(f"✅ Чат {chat_id} удалён из списка.")
        else:
            await event.message.reply(f"❌ Чат {chat_id} не найден.")
    except ValueError:
        await event.message.reply("❌ ID чата должен быть числом.")

@dp.message_created(Command("toggle_chat"))
async def cmd_toggle_chat(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id

    if user_id != ADMIN_MAX_ID:
        await event.message.reply("❌ Только владелец бота может управлять чатами.")
        return
    args = event.message.body.text.split()
    if len(args) < 2:
        await event.message.reply("ℹ️ Использование: /toggle_chat <ID_чата>")
        return
    
    try:
        chat_id = int(args[1])
        chats = await get_all_chats(PLATFORM)
        chat_exists = any(c[0] == chat_id for c in chats)
        
        if not chat_exists:
            await event.message.reply(f"❌ Чат {chat_id} не найден.")
            return
        
        # Получаем текущий статус
        for c_id, _, is_active in chats:
            if c_id == chat_id:
                new_status = not is_active
                break
        
        if await toggle_chat(PLATFORM, chat_id, new_status):
            status_text = "включён" if new_status else "выключен"
            await event.message.reply(f"✅ Чат {chat_id} {status_text}.")
        else:
            await event.message.reply(f"❌ Ошибка при изменении статуса чата.")
    except ValueError:
        await event.message.reply("❌ ID чата должен быть числом.")


@dp.message_created(Command("list_chats"))
async def cmd_list_chats(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id

    if user_id != ADMIN_MAX_ID:
        await event.message.reply("❌ Только владелец бота может просматривать список.")
        return

    chats = await get_all_chats(PLATFORM)
    if not chats:
        await event.message.reply("📭 Список чатов пуст.")
        return

    chats_text = []
    for chat_id, name, is_active in chats:
        status = "🟢 Активен" if is_active else "🔴 Неактивен"
        chats_text.append(f"• {name}\n  ID: `{chat_id}`\n  Статус: {status}")
    
    await event.message.reply(
        f"📋 Список чатов для пересылки:\n\n" + "\n".join(chats_text)
    )

@dp.message_created(Command("getid"))
async def get_ids(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id
    chat = await event.fetch_chat()

    if not await is_allowed(PLATFORM, user_id):
        await event.message.reply("❌ У вас нет прав на использование этого бота.")
        return
    chat = await event.fetch_chat()

    text = (
        f"ID этого чата: <b>{chat.chat_id}</b>"
    )
    await event.message.answer(text, format=Format.HTML)

@dp.message_created(F.message.body.text[0] =='/')
async def cmd_unexpected(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id
    chat = await event.fetch_chat()

    if not await is_allowed(PLATFORM, user_id):
        await event.message.reply("❌ У вас нет прав на использование этого бота.")
        return

    await event.message.reply("❌ Команды не существует")
    

@dp.message_created()
async def forward_message(event: MessageCreated):
    from_user = await event.fetch_from_user()
    user_id = from_user.user_id
    chat = await event.fetch_chat()

    if not await is_allowed(PLATFORM, user_id):
        await event.message.reply("❌ У вас нет прав на использование этого бота.")
        return

    active_chats = await get_active_chats(PLATFORM)

    if not active_chats:
        await event.message.reply("⚠️ Нет активных чатов для пересылки. Добавьте чат через /add_chat")
        return

    success_count = 0
    error_chats = []
    message_text = event.message.body.text
    message_attachments = []
    for attachment in event.message.body.attachments or []:
        attachment_type = getattr(attachment.type, "value", attachment.type)
        payload = attachment.payload

        if (
            attachment_type in {"image", "video", "audio", "file"}
            and payload
            and hasattr(payload, "token")
            and payload.token
        ):
            message_attachments.append(
                AttachmentUpload(
                    type=attachment_type,
                    payload=AttachmentPayload(token=payload.token),
                )
            )
        else:
            message_attachments.append(attachment)

    message_attachments = message_attachments or None
    
    for chat_id, chat_name in active_chats:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                attachments=message_attachments,
            )
            success_count += 1
        except Exception as e:
            error_chats.append(f"{chat_name} (ID: {chat_id}) - {str(e)[:50]}")

    if success_count > 0:
        report = f"✅ Переслано в {success_count} чатов"
        if error_chats:
            report += f"\n\n⚠️ Ошибки:\n" + "\n".join(error_chats)
        await event.message.reply(report)
    else:
        await event.message.reply(f"❌ Не удалось переслать ни в один чат.\n\nОшибки:\n" + "\n".join(error_chats))




async def main():
    await init_db()
    print("🤖 MAX бот запущен!")
    print(f"👥 Админ: {ADMIN_MAX_ID}")


    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print("🔄 Перезапустите бота через несколько секунд")


if __name__ == "__main__":
    asyncio.run(main())
