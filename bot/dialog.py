"""Диалог с одним клиентом. Один и тот же код работает и в консоли, и в Telegram."""

from dataclasses import dataclass

from . import config, i18n, kb, llm, prompts
from .qualify import CANCEL, Qualification, wants_to_apply


@dataclass
class Reply:
    text: str
    debug: str = ""           # что нашёл поиск или что извлечено из ответа клиента
    lead: dict | None = None  # заполняется, когда заявка оформлена


class Dialog:
    lang = "ru"  # значение по умолчанию для диалогов, сохранённых до появления языков

    def __init__(self, index: dict, channel: str, lang: str = "ru"):
        self.index = index
        self.channel = channel
        self.lang = lang
        self.debug = False
        self.applied = False  # заявка уже отправлена — повторно не оформляем
        self.reset()

    def reset(self) -> None:
        self.history: list[dict] = []
        self.qualification: Qualification | None = None

    # Диалог сохраняется на диск, чтобы перезапуск бота не обрывал заявку.
    # Индекс базы знаний большой и общий для всех, поэтому его не сохраняем, а подставляем заново.
    def __getstate__(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if key != "index"}

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self.index = None

    def start_application(self) -> Reply:
        if self.applied:
            return Reply(i18n.t(self.lang, "already_applied"))
        # Юрист видит язык клиента прямо в поле «Канал»
        channel = f"{self.channel}, {i18n.LANGUAGES[self.lang]}" if self.lang != "ru" else self.channel
        self.qualification = Qualification(channel=channel, lang=self.lang)
        return Reply(self.qualification.first_question())

    def reply(self, text: str) -> Reply:
        # Идёт оформление заявки: ответ клиента обрабатывает workflow, а не консультант
        if self.qualification:
            if CANCEL.match(text.strip()):
                self.qualification = None
                return Reply(i18n.t(self.lang, "cancelled"))
            answer, finished = self.qualification.handle(text)
            reply = Reply(answer, debug=f"[данные заявки] {self.qualification.lead}")
            if finished:
                reply.lead, self.qualification, self.applied = self.qualification.lead, None, True
            return reply

        if wants_to_apply(text):
            return self.start_application()

        previous = self.history[-2]["content"] if self.history else ""
        query, found = kb.retrieve(self.index, text, previous, self.lang)
        debug = "\n".join(
            [f"[запрос для поиска] {query}"] + [f"{score:.1f}  {chunk.title}" for score, chunk in found]
        )

        answer = llm.complete(prompts.build_messages(self.history, text, found, self.lang))
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        self.history = self.history[-config.HISTORY_MESSAGES:]
        return Reply(answer, debug=debug)
