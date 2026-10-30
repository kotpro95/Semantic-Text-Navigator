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
    understood: str = ""            # как понят вопрос: «STN-102 · сумма · на 10.03.2026»
    parsed_by: str = "правила"      # кто разобрал вопрос: правила или LLM


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


# ---------- разбор свободного вопроса ----------
# Не чат: фраза сводится к структурному запросу (договор + поле + дата), ответ строят
# те же правила с цитатами. Сначала правила (синонимы, словоформы, поставщик → договор),
# если не хватило — LLM (llm.parse_question), если и она не уверена — просим уточнить.

FIELD_SYNONYMS = [  # сначала сильные признаки, затем слабые: «сумма поставки» — сумма, «сколько до поставки» — срок
    ("penalty", r"неустойк|\bпен[иья]\b|штраф"),
    ("supplier", r"поставщик|контрагент|кто\s+поставля|с\s+кем"),
    ("amount", r"сумм|стоимост|\bцен[аыуе]?\b|плат|деньг|\bруб"),
    ("delivery", r"срок|привез|доставк|отгруз|\bкогда\b"),
    ("delivery", r"постав(?!щик)"),
    ("amount", r"сколько|стоит|обойд|затрат"),
]
FIELD_NAMES = {"amount": "сумма", "delivery": "срок поставки", "penalty": "неустойка", "supplier": "поставщик"}
BEFORE_RE = re.compile(r"раньше|ранее|прежде|не\s+позднее|\bдо\b", re.I)
MONTH_ONLY_RE = re.compile(r"(?:до|раньше|ранее|к)\s+(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*(?:\s+(\d{4}))?", re.I)


def _stem(w: str) -> str:
    return w[:5] if len(w) > 5 else w


def supplier_index(views: list[ContractView]) -> dict[str, list[str]]:
    """номер договора → значимые основы слов из названия поставщика («контур», «элект»)."""
    out = {}
    for v in views:
        name = (v.fields["supplier"].display or "")
        inner = re.findall(r"«([^»]+)»", name) or [name]
        words = [w for w in re.findall(r"[а-яёa-z]+", inner[0].lower()) if len(w) > 3]
        if words:
            out[v.number] = [_stem(w) for w in words]
    return out


def parse_question(text: str, default_as_of: date, suppliers: dict[str, list[str]] | None = None) -> dict:
    low = text.lower()
    dates: list[date] = []
    for m in TEXT_DATE_RE.finditer(low):
        mon = next(v for k, v in MONTHS.items() if m.group(2).startswith(k))
        dates.append(date(int(m.group(3)), mon, int(m.group(1))))
    if d := parse_date(text):
        dates.append(d)
    if not dates and (mm := MONTH_ONLY_RE.search(low)):  # «до апреля» → 01.04 того же года
        mon = next(v for k, v in MONTHS.items() if mm.group(1).startswith(k))
        dates.append(date(int(mm.group(2) or default_as_of.year), mon, 1))

    num = CONTRACT_NO_RE.search(text.upper())
    contract = num.group(1) if num else None
    if not contract and suppliers:
        words = re.findall(r"[а-яёa-z]+", low)
        hits = [n for n, stems in suppliers.items() if any(any(w.startswith(st) for w in words) for st in stems)]
        if len(hits) == 1:
            contract = hits[0]
    field = next((f for f, rx in FIELD_SYNONYMS if re.search(rx, low)), None)

    if not contract and dates and BEFORE_RE.search(low) and field in (None, "delivery"):
        return {"type": "delivery_before", "date": dates[0], "as_of": default_as_of, "ok": True}
    as_of = dates[0] if (dates and contract) else default_as_of
    return {"type": "field", "contract": contract, "field": field, "as_of": as_of, "ok": bool(contract and field)}


def describe(p: dict) -> str:
    from .parsing.segment import fmt_date as fd
    if p["type"] == "delivery_before":
        return f"договоры со сроком поставки раньше {fd(p['date'])} · на {fd(p['as_of'])}"
    return f"{p['contract']} · {FIELD_NAMES.get(p['field'], p['field'])} · на {fd(p['as_of'])}"
