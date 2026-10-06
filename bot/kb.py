"""База знаний и поиск по ней — буква R (Retrieval) в RAG.

1. Документы из папки knowledge/ режутся на фрагменты по заголовкам «## ».
2. Каждый фрагмент превращается в вектор (эмбеддинг) и сохраняется в data/index.json.
3. Вопрос пользователя тоже превращается в вектор, и мы берём фрагменты с самыми близкими векторами.

Запуск `python -m bot.kb` пересобирает индекс и показывает, какие фрагменты получились.
"""

import hashlib
import json
import math
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


def _fingerprint(chunks: list[Chunk]) -> str:
    raw = "\n".join(c.title + c.text for c in chunks)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_index(chunks: list[Chunk]) -> dict:
    vectors = llm.embed([c.as_context() for c in chunks])
    index = {
        "fingerprint": _fingerprint(chunks),
        "items": [{"chunk": c.__dict__, "vector": v} for c, v in zip(chunks, vectors)],
    }
    config.INDEX_PATH.parent.mkdir(exist_ok=True)
    config.INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index


def load_index() -> dict:
    """Загружает индекс. Если база знаний изменилась, пересобирает его автоматически."""
    chunks = load_chunks()
    if config.INDEX_PATH.exists():
        index = json.loads(config.INDEX_PATH.read_text(encoding="utf-8"))
        if index.get("fingerprint") == _fingerprint(chunks):
            return index
    print("База знаний изменилась, пересобираю индекс…")
    return build_index(chunks)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def search(index: dict, query: str, k: int = config.TOP_K) -> list[tuple[float, Chunk]]:
    """Возвращает k самых близких по смыслу фрагментов с оценкой сходства от 0 до 1."""
    query_vector = llm.embed([query])[0]
    scored = [
        (_cosine(query_vector, item["vector"]), Chunk(**item["chunk"]))
        for item in index["items"]
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:k]


if __name__ == "__main__":
    chunks = load_chunks()
    for c in chunks:
        print(f"• {c.title} ({len(c.text)} симв.)")
    print(f"\nВсего фрагментов: {len(chunks)}")
    if config.GIGACHAT_CREDENTIALS:
        build_index(chunks)
        print(f"Индекс сохранён: {config.INDEX_PATH}")
    else:
        print("Ключ GigaChat не задан, индекс не строю.")
