"""Текст → абзацы с номерами и смещениями. Абзац = непустая строка
(в учебном формате каждый пункт договора записан одной строкой)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from ..models import Paragraph

CLAUSE_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s")
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
# 1 200 000 / 1 200 000 / 840000, необязательные копейки «,00», пропись в скобках, затем «руб» / «₽»
MONEY_RE = re.compile(r"(\d{1,3}(?:[  ]\d{3})+|\d{4,})(?:[,.](\d{2}))?\s*(?:\([^)]*\)\s*)?(?:руб|₽)", re.I)
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


def parse_money(s: str) -> Decimal | None:
    """Сумма в рублях; копейки сохраняются, «,00» отбрасывается: 2 450 500,00 → 2450500."""
    m = MONEY_RE.search(s)
    if not m:
        return None
    v = Decimal(re.sub(r"\D", "", m.group(1)) + "." + (m.group(2) or "00"))
    return v.quantize(Decimal(1)) if v == v.to_integral_value() else v


def fmt_money(v: Decimal | int) -> str:
    v = Decimal(v)
    whole = f"{int(v):,}".replace(",", " ")
    frac = v - int(v)
    return whole if not frac else f"{whole},{str(frac.quantize(Decimal('0.01')))[2:]}"


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")
