"""Текст → абзацы с номерами и смещениями. Абзац = непустая строка
(в учебном формате каждый пункт договора записан одной строкой)."""
from __future__ import annotations

import re
from datetime import date

from ..models import Paragraph

CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s")
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
# 1 200 000 / 1 200 000 / 840000, необязательная пропись в скобках, затем «руб»
MONEY_RE = re.compile(r"(\d{1,3}(?:[  ]\d{3})+|\d{4,})\s*(?:\([^)]*\)\s*)?(?:руб|₽)", re.I)
# Предложение заканчивается точкой перед пробелом и заглавной буквой/кавычкой/цифрой,
# но не внутри даты "15.04.2026" и не в номере пункта "2.1."
SENTENCE_END_RE = re.compile(r"(?<=[.!?»])\s+(?=[А-ЯЁA-Z«\d])")


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")


def segment(text: str) -> list[Paragraph]:
    paras: list[Paragraph] = []
    pos = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            start = pos + line.index(stripped)
            m = CLAUSE_RE.match(stripped)
            paras.append(Paragraph(n=len(paras) + 1, clause=m.group(1) if m else None,
                                   text=stripped, start=start, end=start + len(stripped)))
        pos += len(line) + 1
    return paras


def sentences(text: str) -> list[str]:
    """Предложения абзаца; каждое — точная подстрока text. Префикс пункта ("2.1. ") отбрасывается."""
    m = CLAUSE_RE.match(text)
    body = text[m.end():] if m else text
    return [s for s in SENTENCE_END_RE.split(body) if s.strip()]


def parse_date(s: str) -> date | None:
    m = DATE_RE.search(s)
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def all_dates(s: str) -> list[date]:
    out = []
    for m in DATE_RE.finditer(s):
        try:
            out.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    return out


def parse_money(s: str) -> int | None:
    m = MONEY_RE.search(s)
    if not m:
        return None
    return int(re.sub(r"\D", "", m.group(1)))


def fmt_money(v: int) -> str:
    return f"{v:,}".replace(",", " ")


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")
