"""Настройки бота. Секреты берутся из файла .env (он не попадает в Git)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

KNOWLEDGE_DIR = ROOT / "knowledge"
INDEX_PATH = ROOT / "data" / "index.json"

# Ключ авторизации из личного кабинета GigaChat API (developers.sber.ru)
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-3-Pro")
# Путь к сертификату НУЦ Минцифры. Если пусто, проверка сертификата отключается (только для демо).
GIGACHAT_CA_BUNDLE = os.getenv("GIGACHAT_CA_BUNDLE", "")

# Telegram-бот: токен от @BotFather и (необязательно) чат, куда приходят новые заявки
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

# Способ поиска по базе знаний: bm25 (бесплатно, локально) или embeddings (платно в GigaChat)
RETRIEVER = os.getenv("RETRIEVER", "bm25")

# Сколько фрагментов базы знаний передавать модели вместе с вопросом
TOP_K = 4
# Сколько последних реплик диалога помнит бот
HISTORY_MESSAGES = 6
