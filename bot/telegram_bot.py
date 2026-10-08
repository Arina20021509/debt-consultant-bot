"""Telegram-бот. Запуск: python -m bot.telegram_bot

Бот работает, пока запущен этот скрипт. У каждого пользователя свой диалог и своя заявка.
Если в .env указан TELEGRAM_ADMIN_CHAT_ID, новые заявки приходят в этот чат.

Команды в боте:
  /start  — выбор языка (русский или узбекский) и новый диалог
  /lang   — сменить язык
  /zayavka — оформить заявку на консультацию
  /debug  — показать, какие фрагменты базы знаний нашёл поиск (только для администратора)
  /leads  — последние заявки и файл Excel (только для администратора)
  /myid   — узнать ID своего чата, чтобы получать заявки
"""

import asyncio
import logging

from openpyxl import load_workbook
from telegram import BotCommand, BotCommandScopeChat, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, PicklePersistence, filters

from . import config, i18n, kb
from .dialog import Dialog
from .qualify import LEADS_PATH

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

INDEX = kb.load_index()
LANGUAGE_KEYBOARD = ReplyKeyboardMarkup([list(i18n.LANGUAGES.values())], resize_keyboard=True)
LANGUAGE_BY_BUTTON = {name: code for code, name in i18n.LANGUAGES.items()}
SHARE_TELEGRAM_BUTTONS = {i18n.t(code, "share_telegram_button") for code in i18n.LANGUAGES}


def _dialog(context: ContextTypes.DEFAULT_TYPE) -> Dialog:
    if "dialog" not in context.user_data:
        context.user_data["dialog"] = Dialog(INDEX, channel="Telegram")
    dialog = context.user_data["dialog"]
    if dialog.index is None:  # диалог восстановлен с диска после перезапуска
        dialog.index = INDEX
    return dialog


def _keyboard(dialog: Dialog):
    """Кнопки зависят от этапа и языка: вопросы → запись; заявка → отмена; контакт → поделиться номером."""
    lang = dialog.lang
    cancel = [i18n.t(lang, "cancel_button")]
    if dialog.qualification:
        if dialog.qualification.current_field == "contact":
            return ReplyKeyboardMarkup(
                [[KeyboardButton(i18n.t(lang, "share_number_button"), request_contact=True)],
                 [i18n.t(lang, "share_telegram_button")], cancel],
                resize_keyboard=True,
            )
        return ReplyKeyboardMarkup([cancel], resize_keyboard=True)
    if dialog.applied:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup([[i18n.t(lang, "apply_button")]], resize_keyboard=True)


def _format_debt(debt, currency: str | None) -> str:
    sign = i18n.CURRENCY_SIGN.get(currency or "RUB", "₽")
    return f"{debt:,} {sign}".replace(",", " ") if isinstance(debt, int) else str(debt)


def _format_lead(lead: dict, user) -> str:
    debt = _format_debt(lead.get("debt"), lead.get("currency"))
    contact = str(lead.get("contact"))
    if user.username and f"@{user.username}" != contact:
        contact += f" (в Telegram: @{user.username})"
    return (
        "Новая заявка\n\n"
        f"Канал: {lead.get('channel')}\n"
        f"Имя: {lead.get('name')}\n"
        f"Сумма долга: {debt}\n"
        f"Кредиторы: {lead.get('creditors')}\n"
        f"Имущество: {lead.get('property')}\n"
        f"Контакт: {contact}\n\n"
        f"Оценка для юриста: {lead.get('assessment')}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Новый диалог начинается с выбора языка."""
    dialog = _dialog(context)
    dialog.reset()
    # Клиент не может оформить заявку повторно, а администратору для тестов /start сбрасывает и эту отметку
    if _is_admin(update):
        dialog.applied = False
    await update.message.reply_text(i18n.CHOOSE_LANGUAGE, reply_markup=LANGUAGE_KEYBOARD)


async def _set_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> None:
    dialog = _dialog(context)
    dialog.lang = lang
    dialog.reset()
    await update.message.reply_text(i18n.t(lang, "greeting"), reply_markup=_keyboard(dialog))


async def apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dialog = _dialog(context)
    reply = dialog.start_application()
    await update.message.reply_text(reply.text, reply_markup=_keyboard(dialog))


def _is_admin(update: Update) -> bool:
    return bool(config.TELEGRAM_ADMIN_CHAT_ID) and str(update.effective_chat.id) == config.TELEGRAM_ADMIN_CHAT_ID.strip()


async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Режим отладки доступен только администратору: клиентам технические подробности не нужны."""
    if not _is_admin(update):
        await update.message.reply_text("Такой команды нет. Задайте вопрос о списании долгов или запишитесь на консультацию.")
        return
    dialog = _dialog(context)
    dialog.debug = not dialog.debug
    await update.message.reply_text(
        "Режим отладки включён: перед ответом покажу, что нашёл поиск по базе знаний."
        if dialog.debug else "Режим отладки выключен."
    )


async def leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Последние заявки и файл Excel — только для администратора."""
    if not _is_admin(update):
        await update.message.reply_text("Такой команды нет. Задайте вопрос о списании долгов или запишитесь на консультацию.")
        return
    if not LEADS_PATH.exists():
        await update.message.reply_text("Заявок пока нет.")
        return
    rows = list(load_workbook(LEADS_PATH, read_only=True).active.iter_rows(min_row=2, values_only=True))
    lines = [f"Всего заявок: {len(rows)}. Последние:"]
    for row in rows[-5:]:
        # Столбцы: дата, канал, имя, сумма, кредиторы, имущество, контакт, оценка, валюта
        date, channel, name, debt, _, _, contact, _, currency = (list(row) + [None] * 9)[:9]
        lines.append(f"• {date} — {name}, {_format_debt(debt, currency)}, {contact} ({channel})")
    await update.message.reply_text("\n".join(lines))
    with LEADS_PATH.open("rb") as file:
        await update.message.reply_document(file, filename="Заявки.xlsx")


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"ID этого чата: {update.effective_chat.id}\n"
        "Чтобы получать сюда заявки, впишите его в .env в TELEGRAM_ADMIN_CHAT_ID и перезапустите бота."
    )


def _incoming_text(update: Update) -> str:
    """Кнопки «Отправить мой номер» и «Связаться в Telegram» превращаем в обычный текст с контактом."""
    message, user = update.message, update.effective_user
    if message.contact:
        return message.contact.phone_number
    if message.text in SHARE_TELEGRAM_BUTTONS:
        return f"@{user.username}" if user.username else f"Telegram, id {user.id}"
    return message.text


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dialog = _dialog(context)
    stage = dialog.qualification.current_field if dialog.qualification else "вопросы"
    log.info("Сообщение от %s, язык: %s, этап: %s", update.effective_user.id, dialog.lang, stage)

    if update.message.text in LANGUAGE_BY_BUTTON:
        await _set_language(update, context, LANGUAGE_BY_BUTTON[update.message.text])
        return

    # Кнопку контакта нажали, а заявки нет (например, она была отменена) — предлагаем оформить заново
    is_contact_button = update.message.contact or update.message.text in SHARE_TELEGRAM_BUTTONS
    if is_contact_button and not dialog.qualification:
        reply = dialog.start_application()
        await update.message.reply_text(reply.text, reply_markup=_keyboard(dialog))
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        # GigaChat вызывается синхронно, поэтому уводим его в отдельный поток, чтобы бот не «замирал» для других
        reply = await asyncio.to_thread(dialog.reply, _incoming_text(update))
    except Exception:
        log.exception("Ошибка при ответе")
        await update.message.reply_text(i18n.t(dialog.lang, "error"))
        return

    if dialog.debug and reply.debug and _is_admin(update):
        await update.message.reply_text(reply.debug)
    await update.message.reply_text(reply.text, reply_markup=_keyboard(dialog))

    if reply.lead:
        log.info("Новая заявка сохранена в data/leads.xlsx")
        if config.TELEGRAM_ADMIN_CHAT_ID:
            await context.bot.send_message(config.TELEGRAM_ADMIN_CHAT_ID, _format_lead(reply.lead, update.effective_user))


async def _set_menu(app: Application) -> None:
    """Клиенты видят в меню две команды, администратор — ещё и /debug."""
    client_commands = [
        BotCommand("start", "Начать заново / Qaytadan boshlash"),
        BotCommand("zayavka", "Записаться на консультацию / Konsultatsiyaga yozilish"),
        BotCommand("lang", "Сменить язык / Tilni o'zgartirish"),
    ]
    await app.bot.set_my_commands(client_commands)
    if config.TELEGRAM_ADMIN_CHAT_ID:
        await app.bot.set_my_commands(
            client_commands + [
                BotCommand("leads", "Последние заявки и файл Excel"),
                BotCommand("debug", "Показать, как бот ищет ответ"),
            ],
            scope=BotCommandScopeChat(int(config.TELEGRAM_ADMIN_CHAT_ID)),
        )


def main() -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN. Получите токен у @BotFather и впишите его в .env.")
    # Диалоги пользователей хранятся в файле и переживают перезапуск бота
    persistence = PicklePersistence(filepath=config.ROOT / "data" / "bot_state.pickle", update_interval=5)
    app = (
        Application.builder().token(config.TELEGRAM_BOT_TOKEN)
        .persistence(persistence).post_init(_set_menu).build()
    )
    app.add_handler(CommandHandler(["start", "new", "lang"], start))
    app.add_handler(CommandHandler("zayavka", apply))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("myid", my_id))
    app.add_handler(CommandHandler("leads", leads))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.CONTACT, on_text))
    log.info("Бот запущен. Остановить: Ctrl+C")
    app.run_polling()


if __name__ == "__main__":
    main()
