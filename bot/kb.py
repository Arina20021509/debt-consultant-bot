"""База знаний и поиск по ней — буква R (Retrieval) в RAG.

1. Документы из папки knowledge/ режутся на фрагменты по заголовкам «## ».
2. По вопросу пользователя ищутся самые подходящие фрагменты. Есть два способа поиска:
   - bm25 (по умолчанию) — поиск по ключевым словам с учётом их редкости. Работает локально и бесплатно;
   - embeddings — поиск по смыслу через векторы GigaChat. Точнее на перефразированных вопросах,
     но в бесплатном тарифе GigaChat недоступен. Включается через RETRIEVER=embeddings в .env.

Запуск `python -m bot.kb` показывает фрагменты и строит индекс.
"""

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass

from . import config, llm


@dataclass
class Chunk:
    source: str  # имя файла
    title: str   # «Документ → раздел»
    text: str

    def as_context(self) -> str:
        return f"[{self.title}]\n{self.text}"


def load_chunks() -> list[Chunk]:
    chunks = []
    for path in sorted(config.KNOWLEDGE_DIR.glob("*.md")):
        doc_title, section, lines = path.stem, None, []

        def flush():
            body = "\n".join(lines).strip()
            if body:
                title = f"{doc_title} → {section}" if section else doc_title
                chunks.append(Chunk(source=path.name, title=title, text=body))

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                doc_title = line[2:].strip()
            elif line.startswith("## "):
                flush()
                section, lines = line[3:].strip(), []
            else:
                lines.append(line)
        flush()
    return chunks


# ---------- BM25: поиск по ключевым словам ----------

_STOP_WORDS = set(
    "и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот "
    "от меня еще о из ему теперь когда даже ну ли если уже или ни быть был него до вас вам ведь там потом "
    "себя ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без чего раз тоже себе под "
    "будет ж тогда кто этот того потому этого какой ним здесь этом один мой тем чтобы нее сейчас были куда "
    "зачем всех при об хоть над тот через эти нас про всего них какая эту моя этой перед том им ваш ваши "
    "ваша вашу ваших мою мои это ли же".split()
)
_WORD = re.compile(r"[a-zа-я0-9]+")


# Слова обрезаются до первых букв, чтобы разные формы совпадали: «подарила» и «подарено» → «пода».
# 4 буквы выбраны по замеру на tests/questions.csv: 4 → 85% попаданий, 5 → 78%, 6 → 74%.
STEM_LENGTH = 4


def _tokens(text: str) -> list[str]:
    words = _WORD.findall(text.lower().replace("ё", "е"))
    return [w if w.isdigit() else w[:STEM_LENGTH] for w in words if w not in _STOP_WORDS and len(w) > 1]


def _build_bm25(chunks: list[Chunk]) -> dict:
    docs = [_tokens(c.as_context()) for c in chunks]
    doc_freq = Counter(token for doc in docs for token in set(doc))
    return {
        "retriever": "bm25",
        "chunks": chunks,
        "docs": [Counter(doc) for doc in docs],
        "lengths": [len(doc) for doc in docs],
        "avg_length": sum(len(doc) for doc in docs) / len(docs),
        "idf": {t: math.log(1 + (len(docs) - n + 0.5) / (n + 0.5)) for t, n in doc_freq.items()},
    }


def _search_bm25(index: dict, query: str, k: int, k1: float = 1.5, b: float = 0.75) -> list[tuple[float, Chunk]]:
    query_tokens = _tokens(query)
    scored = []
    for chunk, doc, length in zip(index["chunks"], index["docs"], index["lengths"]):
        score = 0.0
        for token in query_tokens:
            tf = doc.get(token, 0)
            if tf:
                norm = tf + k1 * (1 - b + b * length / index["avg_length"])
                score += index["idf"][token] * tf * (k1 + 1) / norm
        scored.append((score, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:k]


# ---------- Эмбеддинги: поиск по смыслу (платно в GigaChat) ----------

def _fingerprint(chunks: list[Chunk]) -> str:
    raw = "\n".join(c.title + c.text for c in chunks)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_embeddings(chunks: list[Chunk]) -> dict:
    """Векторы кэшируются в data/index.json и пересчитываются, только если база знаний изменилась."""
    if config.INDEX_PATH.exists():
        cached = json.loads(config.INDEX_PATH.read_text(encoding="utf-8"))
        if cached.get("fingerprint") == _fingerprint(chunks):
            return {"retriever": "embeddings", "chunks": chunks, "vectors": cached["vectors"]}
    print("Строю векторный индекс базы знаний…")
    vectors = llm.embed([c.as_context() for c in chunks])
    config.INDEX_PATH.parent.mkdir(exist_ok=True)
    config.INDEX_PATH.write_text(
        json.dumps({"fingerprint": _fingerprint(chunks), "vectors": vectors}), encoding="utf-8"
    )
    return {"retriever": "embeddings", "chunks": chunks, "vectors": vectors}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def _search_embeddings(index: dict, query: str, k: int) -> list[tuple[float, Chunk]]:
    query_vector = llm.embed([query])[0]
    scored = [(_cosine(query_vector, v), c) for c, v in zip(index["chunks"], index["vectors"])]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:k]


# ---------- Переформулирование запроса ----------

REWRITE_PROMPT = """Ты помогаешь искать по базе знаний юридической компании о банкротстве граждан.
Перепиши вопрос клиента в поисковый запрос: перечисли через пробел ключевые слова, их синонимы
и юридические термины, которые могут встречаться в тексте базы знаний.
Например, «сколько платить управляющему» → «стоимость расходы вознаграждение финансовый управляющий депозит».
Если вопрос уточняющий, учти предыдущий вопрос клиента.
Верни только слова, без пояснений.

Предыдущий вопрос: {previous}
Вопрос: {question}"""


def rewrite_query(question: str, previous: str = "") -> str:
    """Клиент пишет «сколько платить управляющему», а в базе «вознаграждение финансового управляющего».
    Модель дополняет вопрос синонимами и терминами, и поиск по ключевым словам находит нужный фрагмент.
    Замер: без переформулирования 85% попаданий, с ним 96%."""
    prompt = REWRITE_PROMPT.format(previous=previous or "нет", question=question)
    return question + " " + llm.complete([{"role": "user", "content": prompt}], temperature=0.1)


# ---------- Общий интерфейс ----------

def load_index() -> dict:
    chunks = load_chunks()
    if config.RETRIEVER == "embeddings":
        return _build_embeddings(chunks)
    return _build_bm25(chunks)


def search(index: dict, query: str, k: int = config.TOP_K) -> list[tuple[float, Chunk]]:
    """Возвращает k самых подходящих фрагментов с оценкой (чем больше, тем лучше)."""
    if index["retriever"] == "embeddings":
        return _search_embeddings(index, query, k)
    return _search_bm25(index, query, k)


def retrieve(index: dict, question: str, previous: str = "") -> tuple[str, list[tuple[float, Chunk]]]:
    """Полный шаг поиска: для BM25 сначала переформулирует вопрос. Возвращает (запрос, фрагменты)."""
    query = rewrite_query(question, previous) if index["retriever"] == "bm25" else question
    return query, search(index, query)


if __name__ == "__main__":
    index = load_index()
    for c in index["chunks"]:
        print(f"• {c.title} ({len(c.text)} симв.)")
    print(f"\nВсего фрагментов: {len(index['chunks'])}, способ поиска: {index['retriever']}")
