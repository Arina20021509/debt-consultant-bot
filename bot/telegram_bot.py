"""Telegram-бот. Запуск: python -m bot.telegram_bot

Бот работает, пока запущен этот скрипт. У каждого пользователя свой диалог и своя заявка.
Если в .env указан TELEGRAM_ADMIN_CHAT_ID, новые заявки приходят в этот чат.

Команды в боте:
  /start  — приветствие и новый диалог
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

from . import config, kb
from .dialog import Dialog
from .qualify import LEADS_PATH

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

INDEX = kb.load_index()
APPLY_KEYBOARD = ReplyKeyboardMarkup([["Записаться на консультацию"]], resize_keyboard=True)
CANCEL_KEYBOARD = ReplyKeyboardMarkup([["Отменить заявку"]], resize_keyboard=True)
SHARE_TELEGRAM = "Связаться в Telegram"
CONTACT_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("Отправить мой номер", request_contact=True)], [SHARE_TELEGRAM], ["Отменить заявку"]],
    resize_keyboard=True,
)
GREETING = (
    "Здравствуйте! Я онлайн-консультант по списанию долгов через банкротство (демо-версия).\n\n"
    "Спросите, например:\n"
    "• Сколько стоит банкротство через МФЦ?\n"
    "• Заберут ли единственную квартиру?\n"
    "• Можно ли брать кредиты после банкротства?\n\n"
    "Чтобы записаться на бесплатную консультацию, нажмите кнопку внизу."
)


def _dialog(context: ContextTypes.DEFAULT_TYPE) -> Dialog:
    if "dialog" not in context.user_data:
        context.user_data["dialog"] = Dialog(INDEX, channel="Telegram")
    dialog = context.user_data["dialog"]
    if dialog.index is None:  # диалог восстановлен с диска после перезапуска
        dialog.index = INDEX
    return dialog


def _keyboard(dialog: Dialog):
    """Кнопки зависят от этапа: вопросы → запись; заявка → отмена; контакт → поделиться номером."""
    if dialog.qualification:
        return CONTACT_KEYBOARD if dialog.qualification.current_field == "contact" else CANCEL_KEYBOARD
    return ReplyKeyboardRemove() if dialog.applied else APPLY_KEYBOARD


def _format_lead(lead: dict, user) -> str:
    debt = f"{lead['debt']:,} ₽".replace(",", " ") if isinstance(lead.get("debt"), int) else lead.get("debt")
    return (
        "Новая заявка из Telegram\n\n"
        f"Имя: {lead.get('name')}\n"
        f"Сумма долга: {debt}\n"
        f"Кредиторы: {lead.get('creditors')}\n"
        f"Имущество: {lead.get('property')}\n"
        f"Контакт: {lead.get('contact')}"
        + (f" (@{user.username})" if user.username else "")
        + f"\n\nОценка для юриста: {lead.get('assessment')}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dialog = _dialog(context)
    dialog.reset()
    await update.message.reply_text(GREETING, reply_markup=_keyboard(dialog))


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
        # Столбцы: дата, канал, имя, сумма, кредиторы, имущество, контакт, оценка
        date, channel, name, debt, _, _, contact, _ = (list(row) + [None] * 8)[:8]
        debt_text = f"{debt:,} ₽".replace(",", " ") if isinstance(debt, int) else debt
        lines.append(f"• {date} — {name}, {debt_text}, {contact} ({channel})")
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
    if message.text == SHARE_TELEGRAM:
        return f"@{user.username}" if user.username else f"Telegram, id {user.id}"
    return message.text


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dialog = _dialog(context)
    stage = dialog.qualification.current_field if dialog.qualification else "вопросы"
    log.info("Сообщение от %s, этап: %s", update.effective_user.id, stage)

    # Кнопку контакта нажали, а заявки нет (например, она была отменена) — предлагаем оформить заново
    is_contact_button = update.message.contact or update.message.text == SHARE_TELEGRAM
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
        await update.message.reply_text("Извините, сейчас не получается ответить. Попробуйте через пару минут.")
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
        BotCommand("start", "Начать заново"),
        BotCommand("zayavka", "Записаться на бесплатную консультацию"),
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
    app.add_handler(CommandHandler(["start", "new"], start))
    app.add_handler(CommandHandler("zayavka", apply))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("myid", my_id))
    app.add_handler(CommandHandler("leads", leads))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.CONTACT, on_text))
    log.info("Бот запущен. Остановить: Ctrl+C")
    app.run_polling()


if __name__ == "__main__":
    main()
