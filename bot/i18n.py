"""Тексты интерфейса на русском и узбекском.

База знаний остаётся на русском: бот переводит вопрос клиента на русский для поиска,
находит ответ в русской базе и отвечает на языке клиента. Переводить базу не нужно.
Узбекские тексты сделаны машинным переводом — перед реальным запуском их должен проверить носитель языка.
"""

LANGUAGES = {"ru": "Русский", "uz": "O'zbekcha"}
CHOOSE_LANGUAGE = "Выберите язык / Tilni tanlang"

TEXTS = {
    "ru": {
        "greeting": (
            "Здравствуйте! Я онлайн-консультант по списанию долгов через банкротство (демо-версия).\n\n"
            "Спросите, например:\n"
            "• Сколько стоит банкротство через МФЦ?\n"
            "• Заберут ли единственную квартиру?\n"
            "• Можно ли брать кредиты после банкротства?\n\n"
            "Чтобы записаться на бесплатную консультацию, нажмите кнопку внизу."
        ),
        "apply_button": "Записаться на консультацию",
        "cancel_button": "Отменить заявку",
        "share_number_button": "Отправить мой номер",
        "share_telegram_button": "Связаться в Telegram",
        "first_question": "Хорошо, оформлю заявку на бесплатную консультацию. {question}",
        "retry": "Не совсем поняла ответ. {question}",
        "retry_contact": "Напишите, пожалуйста, сам номер телефона (например, +7 999 123-45-67) "
                         "или ник в Telegram (например, @ivan_petrov).",
        "thanks": "Спасибо{name}! Заявка принята. Юрист перезвонит вам в рабочее время: пн–пт, 9:00–20:00 по Москве.",
        "cancelled": "Заявку отменила. Если появятся вопросы о списании долгов, задавайте.",
        "already_applied": "Ваша заявка уже принята, юрист свяжется с вами в рабочее время. "
                           "А пока можете задать мне любой вопрос о списании долгов.",
        "error": "Извините, сейчас не получается ответить. Попробуйте через пару минут.",
    },
    "uz": {
        "greeting": (
            "Assalomu alaykum! Men bankrotlik orqali qarzlarni hisobdan chiqarish bo'yicha onlayn maslahatchiman "
            "(demo-versiya).\n\n"
            "Masalan, so'rang:\n"
            "• MFC orqali bankrotlik qancha turadi?\n"
            "• Yagona kvartiramni olib qo'yishadimi?\n"
            "• Bankrotlikdan keyin kredit olsa bo'ladimi?\n\n"
            "Bepul konsultatsiyaga yozilish uchun pastdagi tugmani bosing."
        ),
        "apply_button": "Konsultatsiyaga yozilish",
        "cancel_button": "Arizani bekor qilish",
        "share_number_button": "Raqamimni yuborish",
        "share_telegram_button": "Telegram orqali bog'lanish",
        "first_question": "Yaxshi, bepul konsultatsiyaga ariza rasmiylashtiraman. {question}",
        "retry": "Javobingizni tushunmadim. {question}",
        "retry_contact": "Iltimos, telefon raqamingizni (masalan, +7 999 123-45-67) "
                         "yoki Telegram'dagi nikingizni (masalan, @ivan_petrov) yozing.",
        "thanks": "Rahmat{name}! Ariza qabul qilindi. Yurist ish vaqtida siz bilan bog'lanadi: "
                  "dushanba–juma, Moskva vaqti bilan 9:00–20:00.",
        "cancelled": "Ariza bekor qilindi. Qarzlar bo'yicha savollaringiz bo'lsa, bemalol so'rang.",
        "already_applied": "Arizangiz allaqachon qabul qilingan, yurist ish vaqtida siz bilan bog'lanadi. "
                           "Hozircha qarzlar bo'yicha istalgan savolingizni berishingiz mumkin.",
        "error": "Kechirasiz, hozir javob bera olmayapman. Bir necha daqiqadan so'ng qayta urinib ko'ring.",
    },
}

# Вопросы заявки на каждом языке (порядок и смысл полей задаёт qualify.FIELDS)
QUESTIONS = {
    "ru": {
        "name": "Как к вам обращаться?",
        "debt": "Какая примерно общая сумма долгов?",
        "creditors": "Кому вы должны: банкам, МФО, налоговой, за ЖКХ, частным лицам?",
        "property": "Есть ли у вас имущество: квартира или дом (в ипотеке или нет), машина, доля в недвижимости?",
        "contact": "Оставьте номер телефона или ник в Telegram, по которому юрист с вами свяжется.",
    },
    "uz": {
        "name": "Sizga qanday murojaat qilsam bo'ladi?",
        "debt": "Qarzlaringizning umumiy miqdori taxminan qancha?",
        "creditors": "Kimlardan qarzdorsiz: banklar, mikromoliya tashkilotlari, soliq, kommunal to'lovlar, xususiy shaxslar?",
        "property": "Mol-mulkingiz bormi: kvartira yoki uy (ipotekada yoki yo'q), mashina, ko'chmas mulkdagi ulush?",
        "contact": "Yurist siz bilan bog'lanishi uchun telefon raqamingiz yoki Telegram'dagi nikingizni qoldiring.",
    },
}

# Добавка к системному промпту: на каком языке отвечать клиенту
ANSWER_LANGUAGE = {
    "ru": "",
    "uz": (
        "Клиент пишет на узбекском. Отвечай ТОЛЬКО на узбекском языке (латиница), простыми словами. "
        "Суммы, сроки и названия (МФЦ, ЕФРСБ, Госуслуги) бери из базы знаний, цифры не меняй. "
        "Валюту НЕ переводи: все суммы в базе в российских рублях, пиши их как «rubl» (например, «15 000 rubl»), "
        "никогда не пиши «so'm». "
        "Если ответа нет в базе, скажи на узбекском, что уточнишь у юриста, и предложи бесплатную консультацию: "
        "для записи клиенту нужно нажать кнопку «Konsultatsiyaga yozilish»."
    ),
}


def t(lang: str, key: str, **values) -> str:
    return TEXTS.get(lang, TEXTS["ru"])[key].format(**values)


def question(lang: str, field: str) -> str:
    return QUESTIONS.get(lang, QUESTIONS["ru"])[field]
