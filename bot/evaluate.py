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
import sys

from . import config, kb, llm, prompts

# Язык → (файл с вопросами, файл отчёта). Запуск на узбекском: python -m bot.evaluate uz
TEST_SETS = {
    "ru": (config.ROOT / "tests" / "questions.csv", config.ROOT / "data" / "eval_report.md"),
    "uz": (config.ROOT / "tests" / "questions_uz.csv", config.ROOT / "data" / "eval_report_uz.md"),
}


def _normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    return re.sub(r"(?<=\d)[\s  ](?=\d)", "", text)


def contains(answer: str, rule: str) -> bool:
    answer = _normalize(answer)
    return all(
        any(_normalize(option) in answer for option in group.split("|"))
        for group in rule.split("&")
    )


def main(lang: str = "ru") -> None:
    tests_path, report_path = TEST_SETS[lang]
    index = kb.load_index()
    with tests_path.open(encoding="utf-8") as f:
        cases = list(csv.DictReader(f, delimiter=";"))

    rows, retrieval_hits, answer_hits, refusal_hits = [], 0, 0, 0
    in_kb = [c for c in cases if c["expected"] != "—"]
    out_kb = [c for c in cases if c["expected"] == "—"]

    for number, case in enumerate(cases, 1):
        _, found = kb.retrieve(index, case["question"], lang=lang)
        answer = llm.complete(prompts.build_messages([], case["question"], found, lang))
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

    title = "# Отчёт о проверке качества" + (f" ({lang})" if lang != "ru" else "")
    lines = [title, "", *[f"- {s}" for s in summary], "", "## Ошибки", ""]
    for case, retrieval_ok, answer_ok, answer in rows:
        if answer_ok and retrieval_ok is not False:
            continue
        problems = []
        if retrieval_ok is False:
            problems.append(f"не найден фрагмент «{case['expected']}»")
        if not answer_ok:
            problems.append(f"в ответе нет «{case['must_contain']}»")
        lines += [f"**{case['question']}**", f"- Проблема: {'; '.join(problems)}", f"- Ответ бота: {answer}", ""]
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nОтчёт: {report_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ru")
