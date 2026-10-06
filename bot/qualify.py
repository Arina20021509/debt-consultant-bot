"""Квалификация заявки: workflow + LLM.

Порядок вопросов задан кодом (workflow). LLM только понимает свободный ответ клиента
и превращает его в данные: «должна банкам около 700 тысяч» → 700000.
Предварительную оценку для юриста считает код по правилам, а не модель:
решение о банкротстве принимает юрист, бот только собирает данные.
"""

import json
import re
from datetime import datetime

from openpyxl import Workbook, load_workbook

from . import config, llm

LEADS_PATH = config.ROOT / "data" / "leads.xlsx"

# (поле, вопрос клиенту, что извлечь из ответа)
QUESTIONS = [
    ("name", "Как к вам обращаться?", "имя клиента, строка"),
    ("debt", "Какая примерно общая сумма долгов?", "общая сумма долгов в рублях, целое число"),
    ("creditors", "Кому вы должны: банкам, МФО, налоговой, за ЖКХ, частным лицам?",
     "список кредиторов через запятую, строка"),
    ("property", "Есть ли у вас имущество: квартира или дом (в ипотеке или нет), машина, доля в недвижимости?",
     "имущество клиента кратко, строка; если имущества нет, верни «нет»"),
    ("contact", "Как юристу с вами связаться: телефон или Telegram?", "телефон или ник в Telegram, строка"),
]

# Фразы, по которым бот понимает, что клиент хочет оставить заявку
INTENT = re.compile(
    r"/заявка|запишите|запиши меня|записаться|оставить заявку|хочу на консультацию|перезвоните",
    re.IGNORECASE,
)

EXTRACT_PROMPT = """Извлеки из ответа клиента значение поля и верни ТОЛЬКО JSON вида {{"value": ...}}.
Поле: {description}.
Если в ответе нет нужной информации, верни {{"value": null}}.

Вопрос: {question}
Ответ клиента: {answer}"""


def wants_to_apply(text: str) -> bool:
    return bool(INTENT.search(text))


def _to_int(value) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"\D", "", value)
        return int(digits) if digits else None
    return None


def extract(field: str, question: str, description: str, answer: str):
    prompt = EXTRACT_PROMPT.format(description=description, question=question, answer=answer)
    raw = llm.complete([{"role": "user", "content": prompt}], temperature=0.1)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        value = json.loads(match.group(0))["value"] if match else None
    except (json.JSONDecodeError, KeyError):
        value = None
    return _to_int(value) if field == "debt" else value


def assess(lead: dict) -> str:
    """Предварительная оценка для юриста. Клиенту она не показывается."""
    notes = []
    debt = lead.get("debt")
    if debt is None:
        notes.append("сумма долга не указана")
    elif debt < 25_000:
        notes.append("долг меньше 25 000 ₽, банкротство, скорее всего, нецелесообразно")
    else:
        if debt <= 1_000_000:
            notes.append("сумма подходит для внесудебного банкротства, проверить исполнительные производства на сайте ФССП")
        if debt > 500_000:
            notes.append("долг больше 500 000 ₽: при просрочке больше 3 месяцев обязан подать на судебное банкротство")
    property_text = str(lead.get("property") or "").lower()
    if "ипотек" in property_text:
        notes.append("есть ипотека, жильё может быть реализовано")
    if re.search(r"машин|авто|дол[яиюе]", property_text):
        notes.append("есть имущество, которое может войти в конкурсную массу")
    return "; ".join(notes)


def save_lead(lead: dict) -> None:
    header = ["Дата", "Имя", "Сумма долга, ₽", "Кредиторы", "Имущество", "Контакт", "Оценка для юриста"]
    if LEADS_PATH.exists():
        workbook = load_workbook(LEADS_PATH)
        sheet = workbook.active
    else:
        LEADS_PATH.parent.mkdir(exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Заявки"
        sheet.append(header)
    sheet.append([
        datetime.now().strftime("%d.%m.%Y %H:%M"),
        lead.get("name"), lead.get("debt"), lead.get("creditors"),
        lead.get("property"), lead.get("contact"), lead.get("assessment"),
    ])
    workbook.save(LEADS_PATH)


class Qualification:
    """Ведёт клиента по вопросам заявки. Если ответ не удалось разобрать, переспрашивает один раз."""

    def __init__(self):
        self.step = 0
        self.lead: dict = {}
        self.retried = False

    def first_question(self) -> str:
        return f"Хорошо, оформлю заявку на бесплатную консультацию. {QUESTIONS[0][1]}"

    def handle(self, answer: str) -> tuple[str, bool]:
        """Принимает ответ клиента. Возвращает (реплика бота, заявка завершена)."""
        field, question, description = QUESTIONS[self.step]
        value = extract(field, question, description, answer)
        if value is None and not self.retried:
            self.retried = True
            return f"Не совсем поняла ответ. {question}", False
        self.lead[field] = value if value is not None else answer
        self.step, self.retried = self.step + 1, False

        if self.step < len(QUESTIONS):
            return QUESTIONS[self.step][1], False

        self.lead["assessment"] = assess(self.lead)
        save_lead(self.lead)
        name = self.lead.get("name")
        thanks = f"Спасибо, {name}!" if name else "Спасибо!"
        return (
            f"{thanks} Заявка принята. Юрист перезвонит вам в рабочее время: "
            "пн–пт, 9:00–20:00 по Москве."
        ), True
