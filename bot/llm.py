"""Работа с GigaChat: ответы модели и эмбеддинги (векторы смысла текста)."""

import time

import httpx
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from . import config

_ROLES = {
    "system": MessagesRole.SYSTEM,
    "user": MessagesRole.USER,
    "assistant": MessagesRole.ASSISTANT,
}

_client = None


def _giga() -> GigaChat:
    global _client
    if _client is None:
        if not config.GIGACHAT_CREDENTIALS:
            raise RuntimeError(
                "Не задан ключ GigaChat. Скопируйте .env.example в .env "
                "и вставьте ключ авторизации в GIGACHAT_CREDENTIALS."
            )
        ssl = (
            {"ca_bundle_file": config.GIGACHAT_CA_BUNDLE}
            if config.GIGACHAT_CA_BUNDLE
            else {"verify_ssl_certs": False}
        )
        _client = GigaChat(
            credentials=config.GIGACHAT_CREDENTIALS,
            scope=config.GIGACHAT_SCOPE,
            model=config.GIGACHAT_MODEL,
            # GigaChat иногда отвечает медленно: ждём дольше и повторяем запрос при сбое
            timeout=60,
            max_retries=2,
            **ssl,
        )
    return _client


def _with_retries(call, attempts: int = 3):
    """GigaChat иногда обрывает соединение. Встроенные повторы библиотеки срабатывают только на коды ошибок,
    поэтому сетевые сбои повторяем сами: до трёх попыток с паузой."""
    for attempt in range(attempts):
        try:
            return call()
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


def complete(messages: list[dict], temperature: float = 0.2) -> str:
    """Отправляет диалог модели и возвращает текст ответа.

    messages — список вида [{"role": "system" | "user" | "assistant", "content": "..."}].
    Низкая temperature делает ответы точнее и стабильнее: для консультанта это важнее креатива.
    """
    chat = Chat(
        messages=[Messages(role=_ROLES[m["role"]], content=m["content"]) for m in messages],
        temperature=temperature,
    )
    response = _with_retries(lambda: _giga().chat(chat))
    return response.choices[0].message.content


def embed(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """Превращает тексты в векторы. Похожие по смыслу тексты получают близкие векторы."""
    vectors = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = _with_retries(lambda: _giga().embeddings(batch))
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
    return vectors
