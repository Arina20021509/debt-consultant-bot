"""Консольный чат с ботом. Запуск: python -m bot.chat

Команды:
  /debug  — показать или скрыть найденные фрагменты базы знаний и разбор заявки
  /заявка — оформить заявку на консультацию
  /new    — начать новый диалог
  /exit   — выйти
"""

from . import config, kb, llm, prompts
from .qualify import Qualification, wants_to_apply


def main() -> None:
    index = kb.load_index()
    history: list[dict] = []
    qualification: Qualification | None = None
    debug = False

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
            debug = not debug
            print(f"[режим отладки {'включён' if debug else 'выключен'}]\n")
            continue
        if text == "/new":
            history, qualification = [], None
            print("[новый диалог]\n")
            continue

        # Идёт оформление заявки: ответ клиента обрабатывает workflow, а не консультант
        if qualification:
            reply, finished = qualification.handle(text)
            if debug:
                print(f"  [данные заявки] {qualification.lead}\n")
            print(f"Бот: {reply}\n")
            if finished:
                print("  [заявка сохранена в data/leads.xlsx]\n")
                qualification = None
            continue

        if wants_to_apply(text):
            qualification = Qualification()
            print(f"Бот: {qualification.first_question()}\n")
            continue

        previous = history[-2]["content"] if history else ""
        query, found = kb.retrieve(index, text, previous)
        if debug:
            print(f"  [запрос для поиска] {query}")
            for score, chunk in found:
                print(f"  {score:.3f}  {chunk.title}")
            print()

        answer = llm.complete(prompts.build_messages(history, text, found))
        print(f"Бот: {answer}\n")

        history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        history = history[-config.HISTORY_MESSAGES:]


if __name__ == "__main__":
    main()
