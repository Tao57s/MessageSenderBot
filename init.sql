-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS allowed_users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    max_id BIGINT UNIQUE,
    vk_id BIGINT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы чатов
CREATE TABLE IF NOT EXISTS forward_chats (
    id SERIAL PRIMARY KEY,
    telegram_chat_id BIGINT UNIQUE,
    max_chat_id BIGINT UNIQUE,
    vk_chat_id BIGINT UNIQUE,
    chat_name VARCHAR(255),
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для ускорения поиска
CREATE INDEX IF NOT EXISTS idx_allowed_users_telegram_id ON allowed_users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_allowed_users_max_id ON allowed_users(max_id);
CREATE INDEX IF NOT EXISTS idx_allowed_users_vk_id ON allowed_users(vk_id);
CREATE INDEX IF NOT EXISTS idx_forward_chats_telegram_chat_id ON forward_chats(telegram_chat_id);
CREATE INDEX IF NOT EXISTS idx_forward_chats_max_chat_id ON forward_chats(max_chat_id);
CREATE INDEX IF NOT EXISTS idx_forward_chats_vk_chat_id ON forward_chats(vk_chat_id);