"""Параметризованные запросы к реестру + разбор простого текстового вопроса.

Ответы строятся только из ContractView — никаких вшитых значений.
"""
from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from .extractors import REGISTRY
from .models import ContractView, Evidence, FieldStatus, FieldView, PendingChange
from .parsing.segment import fmt_date, parse_date
from .parsing.classify import CONTRACT_NO_RE

MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7,
          "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
TEXT_DATE_RE = re.compile(r"(\d{1,2})\s+(январ|феврал|март|апрел|ма|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*\s+(\d{4})", re.I)


class Answer(BaseModel):
    kind: str
    question: str
    text: str                       # короткий ответ человеческим языком
    as_of: date
    contract: str | None = None
    field: FieldView | None = None
    pending: list[PendingChange] = Field(default_factory=list)
    matches: list[dict] = Field(default_factory=list)
    excluded: list[dict] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


def _find(views: list[ContractView], number: str) -> ContractView | None:
    return next((v for v in views if v.number.upper() == number.upper()), None)


def field_answer(views: list[ContractView], number: str, field: str, as_of: date) -> Answer:
    label = REGISTRY[field].label if field in REGISTRY else field
    q = f"{label} по договору {number} на {fmt_date(as_of)}"
    v = _find(views, number)
    if v is None:
        return Answer(kind="field", question=q, as_of=as_of, contract=number,
                      text=f"Договор {number} не загружен — нет данных.")
    f = v.fields[field]
    pend = [p for p in v.pending if p.field == field]
    if f.status == FieldStatus.missing:
        text = f"{label} по {number}: нет данных. {f.note or ''}".strip()
    else:
        text = f"{label} по {number}: {f.display}"
        if f.changed_by:
            text += f" (изменено: {f.changed_by})"
        if f.status == FieldStatus.review:
            text += f". Требует проверки: {f.note}"
    if pend:
        text += ". Не согласовано: " + "; ".join(f"{p.doc_label} предлагает {p.proposed_display}" for p in pend)
    return Answer(kind="field", question=q, as_of=as_of, contract=number, field=f, pending=pend,
                  text=text, evidence=f.evidence)


def delivery_before(views: list[ContractView], before: date, as_of: date) -> Answer:
    q = f"Поставка раньше {fmt_date(before)} и несогласованные изменения срока (на {fmt_date(as_of)})"
    matches, excluded = [], []
    for v in views:
        f = v.fields["delivery"]
        pend = [p for p in v.pending if p.field == "delivery"]
        row = {"contract": v.number, "display": f.display, "status": f.status.value,
               "evidence": [e.model_dump() for e in f.evidence],
               "pending": [p.model_dump() for p in pend]}
        if not f.value:
            row["reason"] = "срок поставки: нет данных — проверьте вручную"
            excluded.append(row)
        elif date.fromisoformat(f.value) < before:
            matches.append(row)
        else:
            row["reason"] = f"срок {f.display} — не раньше {fmt_date(before)}"
            excluded.append(row)
    if matches:
        parts = []
        for m in matches:
            s = f"{m['contract']} — {m['display']}"
            if m["pending"]:
                s += " (есть несогласованное изменение срока: " + "; ".join(
                    f"{p['doc_label']} → {p['proposed_display']}" for p in m["pending"]) + ")"
            parts.append(s)
        text = f"Раньше {fmt_date(before)}: " + "; ".join(parts) + "."
    else:
        text = f"Договоров со сроком поставки раньше {fmt_date(before)} нет."
    other_pending = [r for r in excluded if r["pending"]]
    if other_pending:
        text += " Несогласованные изменения срока есть также по: " + ", ".join(r["contract"] for r in other_pending) + "."
    if any(r["status"] == "missing" for r in excluded):
        text += " По части договоров срок неизвестен — см. исключённые."
    return Answer(kind="delivery_before", question=q, as_of=as_of, matches=matches, excluded=excluded, text=text)


def parse_question(text: str, default_as_of: date) -> dict:
    """Очень простой разбор текстового вопроса в параметры запроса. Не чат: только шаблоны."""
    low = text.lower()
    dates = []
    for m in TEXT_DATE_RE.finditer(low):
        mon = next(v for k, v in MONTHS.items() if m.group(2).startswith(k))
        dates.append(date(int(m.group(3)), mon, int(m.group(1))))
    if d := parse_date(text):
        dates.append(d)
    num = CONTRACT_NO_RE.search(text.upper())
    if re.search(r"раньше|до\s|ранее", low) and "постав" in low and not num:
        return {"type": "delivery_before", "date": dates[0] if dates else None, "as_of": default_as_of}
    field = None
    if re.search(r"сумм|стоимост|цен", low):
        field = "amount"
    elif re.search(r"срок|постав", low):
        field = "delivery"
    elif "неустойк" in low or "пен" in low:
        field = "penalty"
    elif "поставщик" in low:
        field = "supplier"
    return {"type": "field", "contract": num.group(1) if num else None, "field": field,
            "as_of": dates[0] if (dates and field) else default_as_of}
