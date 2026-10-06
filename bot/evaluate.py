"""Проверка качества бота на наборе тестовых вопросов. Запуск: python -m bot.evaluate

Файл tests/questions.csv:
  question     — вопрос клиента;
  expected     — заголовок фрагмента базы, где лежит ответ, или «—», если ответа в базе нет;
  must_contain — что должно быть в ответе: «&» — все условия, «|» — любой из вариантов.
                 Регистр и пробелы в числах не важны: «25000» найдёт и «25 000 ₽».

Метрики:
  поиск   — доля вопросов, где нужный фрагмент попал в найденные (top-k);
  ответы  — доля ответов на вопросы из базы, где есть нужные факты;
  отказы  — доля вопросов вне базы, где бот честно не стал выдумывать ответ.
Отчёт сохраняется в data/eval_report.md.
"""

import csv
import re

from . import config, kb, llm, prompts

TESTS_PATH = config.ROOT / "tests" / "questions.csv"
REPORT_PATH = config.ROOT / "data" / "eval_report.md"


def _normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    return re.sub(r"(?<=\d)[\s  ](?=\d)", "", text)


def contains(answer: str, rule: str) -> bool:
    answer = _normalize(answer)
    return all(
        any(_normalize(option) in answer for option in group.split("|"))
        for group in rule.split("&")
    )


def main() -> None:
    index = kb.load_index()
    with TESTS_PATH.open(encoding="utf-8") as f:
        cases = list(csv.DictReader(f, delimiter=";"))

    rows, retrieval_hits, answer_hits, refusal_hits = [], 0, 0, 0
    in_kb = [c for c in cases if c["expected"] != "—"]
    out_kb = [c for c in cases if c["expected"] == "—"]

    for number, case in enumerate(cases, 1):
        _, found = kb.retrieve(index, case["question"])
        answer = llm.complete(prompts.build_messages([], case["question"], found))
        answer_ok = contains(answer, case["must_contain"])

        if case["expected"] == "—":
            retrieval_ok = None
            refusal_hits += answer_ok
        else:
            retrieval_ok = any(chunk.title == case["expected"] for _, chunk in found)
            retrieval_hits += retrieval_ok
            answer_hits += answer_ok

        rows.append((case, retrieval_ok, answer_ok, answer))
        mark = "✓" if answer_ok and retrieval_ok is not False else "✗"
        print(f"{number:>2}/{len(cases)} {mark} {case['question']}")

    def pct(hits: int, total: int) -> str:
        return f"{hits}/{total} ({hits / total:.0%})" if total else "—"

    summary = [
        f"Поиск нужного фрагмента (top-{config.TOP_K}): {pct(retrieval_hits, len(in_kb))}",
        f"Ответы с нужными фактами: {pct(answer_hits, len(in_kb))}",
        f"Честные отказы на вопросы вне базы: {pct(refusal_hits, len(out_kb))}",
    ]
    print("\n" + "\n".join(summary))

    lines = ["# Отчёт о проверке качества", "", *[f"- {s}" for s in summary], "", "## Ошибки", ""]
    for case, retrieval_ok, answer_ok, answer in rows:
        if answer_ok and retrieval_ok is not False:
            continue
        problems = []
        if retrieval_ok is False:
            problems.append(f"не найден фрагмент «{case['expected']}»")
        if not answer_ok:
            problems.append(f"в ответе нет «{case['must_contain']}»")
        lines += [f"**{case['question']}**", f"- Проблема: {'; '.join(problems)}", f"- Ответ бота: {answer}", ""]
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nОтчёт: {REPORT_PATH}")


if __name__ == "__main__":
    main()
