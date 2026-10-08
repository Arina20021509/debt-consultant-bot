"""Консольный чат с ботом. Запуск: python -m bot.chat

Команды:
  /debug  — показать или скрыть найденные фрагменты базы знаний и разбор заявки
  /заявка — оформить заявку на консультацию
  /new    — начать новый диалог
  /ru, /uz — переключить язык ответов (русский или узбекский)
  /exit   — выйти
"""

from . import i18n, kb
from .dialog import Dialog


def main() -> None:
    dialog = Dialog(kb.load_index(), channel="Консоль")

    print("Бот-консультант по списанию долгов (демо). Команды: /debug, /заявка, /new, /exit\n")
    print("Бот: Здравствуйте! Я помогу разобраться, как списать долги. Что вас беспокоит?\n")

    while True:
        try:
            text = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/exit":
            break
        if text == "/debug":
            dialog.debug = not dialog.debug
            print(f"[режим отладки {'включён' if dialog.debug else 'выключен'}]\n")
            continue
        if text == "/new":
            dialog.reset()
            print("[новый диалог]\n")
            continue
        if text in ("/ru", "/uz"):
            dialog.lang = text[1:]
            dialog.reset()
            print(f"[язык: {i18n.LANGUAGES[dialog.lang]}]\n")
            continue

        reply = dialog.reply(text)
        if dialog.debug and reply.debug:
            print(f"  {reply.debug.replace(chr(10), chr(10) + '  ')}\n")
        print(f"Бот: {reply.text}\n")
        if reply.lead:
            print("  [заявка сохранена в data/leads.xlsx]\n")


if __name__ == "__main__":
    main()
