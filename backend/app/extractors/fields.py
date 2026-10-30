"""Экстракторы: поставщик, сумма договора, срок поставки, неустойка."""
from __future__ import annotations

import re

from ..models import Document, Extracted, Paragraph, Rejected
from ..parsing.segment import all_dates, fmt_date, fmt_money, parse_money, sentences
from .base import ev, register

# ---------- поставщик ----------
SUPPLIER_RE = re.compile(r"Поставщик\s*:\s*((?:ООО|АО|ПАО|ЗАО|ИП)?\s*«[^»]+»|[^.;\n]+)")


@register("supplier", "Поставщик")
def supplier(doc: Document, paras: list[Paragraph]) -> Extracted:
    found: dict[str, tuple] = {}
    for p in paras:
        if m := SUPPLIER_RE.search(p.text):
            name = m.group(1).strip()
            found.setdefault(name, (p, m.group(0).strip()))
    if not found:
        return Extracted(field="supplier", missing_reason="Строка «Поставщик:» не найдена")
    name, (p, quote) = next(iter(found.items()))
    return Extracted(field="supplier", value=name, display=name, evidence=[ev(doc, p, quote)],
                     ambiguous=len(found) > 1)


# ---------- сумма договора ----------
AMOUNT_TRIGGER = re.compile(r"(общ\w+|итогов\w+)\s+стоимост\w*|цена\s+договора", re.I)
AMOUNT_NOT_PRICE = {
    "аванс": "это авансовый платёж, а не стоимость договора",
    "лимит": "это бюджетный лимит, а не согласованная стоимость",
    "входит в общую": "часть общей стоимости, а не сама стоимость",
}
AMOUNT_ABSENT = re.compile(r"не\s+указан|определяется\s+спецификаци|в\s+приложени\w*\s+№|не\s+входит", re.I)


@register("amount", "Сумма, ₽ с НДС")
def amount(doc: Document, paras: list[Paragraph]) -> Extracted:
    accepted: list[tuple[int, Paragraph, str]] = []
    rejected: list[Rejected] = []
    absent: list[tuple[Paragraph, str]] = []
    for p in paras:
        for s in sentences(p.text):
            low = s.lower()
            money = parse_money(s)
            bad = next((why for key, why in AMOUNT_NOT_PRICE.items() if key in low), None)
            if money is not None and (bad or not AMOUNT_TRIGGER.search(s)):
                rejected.append(Rejected(display=fmt_money(money),
                                         reason=bad or "сумма не названа стоимостью договора",
                                         evidence=ev(doc, p, s)))
                continue
            if AMOUNT_TRIGGER.search(s):
                if money is not None:
                    accepted.append((money, p, s))
                elif AMOUNT_ABSENT.search(s):
                    absent.append((p, s))
    if accepted:
        values = {a[0] for a in accepted}
        v, p, s = accepted[0]
        return Extracted(field="amount", value=str(v), display=fmt_money(v),
                         evidence=[ev(doc, x[1], x[2]) for x in accepted],
                         ambiguous=len(values) > 1, rejected=rejected)
    if absent:
        p, s = absent[0]
        reason = ("Стоимость указана в приложении, его текста нет в комплекте"
                  if re.search(r"приложени", s, re.I) else "Стоимость в тексте не указана")
        return Extracted(field="amount", missing_reason=reason,
                         evidence=[ev(doc, p, s) for p, s in absent], rejected=rejected)
    return Extracted(field="amount", missing_reason="Стоимость договора в тексте не найдена",
                     rejected=rejected)


# ---------- срок поставки ----------
DELIVERY_TRIGGER = re.compile(r"\bпостав\w*", re.I)
DEADLINE_RE = re.compile(r"не\s+позднее\s+(\d{2}\.\d{2}\.\d{4})", re.I)
DELIVERY_NOT = {"оплат": "это срок оплаты, а не поставки", "приемк": "это дата приёмки", "приёмк": "это дата приёмки"}


@register("delivery", "Срок поставки")
def delivery(doc: Document, paras: list[Paragraph]) -> Extracted:
    accepted, rejected = [], []
    for p in paras:
        for s in sentences(p.text):
            m = DEADLINE_RE.search(s)
            if not m:
                continue
            low = s.lower()
            bad = next((why for key, why in DELIVERY_NOT.items() if key in low), None)
            if bad or not DELIVERY_TRIGGER.search(s):
                rejected.append(Rejected(display=m.group(1), reason=bad or "срок не относится к поставке",
                                         evidence=ev(doc, p, s)))
                continue
            accepted.append((all_dates(m.group(0))[0], p, s))
    if not accepted:
        return Extracted(field="delivery", missing_reason="Срок поставки в тексте не найден", rejected=rejected)
    d, p, s = accepted[0]
    return Extracted(field="delivery", value=d.isoformat(), display=fmt_date(d),
                     evidence=[ev(doc, x[1], x[2]) for x in accepted],
                     ambiguous=len({a[0] for a in accepted}) > 1, rejected=rejected)


# ---------- неустойка ----------
PENALTY_TRIGGER = re.compile(r"неустойк|пен[яи]\b|штраф", re.I)
PCT_RE = re.compile(r"(\d+(?:[,.]\d+)?)\s*%")
CAP_RE = re.compile(r"не\s+более\s+(\d+(?:[,.]\d+)?)\s*%", re.I)
PENALTY_ABSENT = re.compile(r"не\s+установлен|не\s+предусмотрен|не\s+указан", re.I)


@register("penalty", "Неустойка за просрочку", in_registry=False)
def penalty(doc: Document, paras: list[Paragraph]) -> Extracted:
    for p in paras:
        for s in sentences(p.text):
            if not PENALTY_TRIGGER.search(s):
                continue
            pcts = PCT_RE.findall(s)
            if pcts:
                rate = pcts[0]
                cap = CAP_RE.search(s)
                per_day = bool(re.search(r"кажд\w*\s+(?:календарн\w*\s+)?(?:день|дн)", s, re.I))
                disp = f"{rate}%" + (" в день" if per_day else "") + (f", не более {cap.group(1)}%" if cap else "")
                val = f"{rate}|{cap.group(1) if cap else ''}"
                return Extracted(field="penalty", value=val, display=disp, evidence=[ev(doc, p, s)])
            if PENALTY_ABSENT.search(s):
                return Extracted(field="penalty", missing_reason="Ставка неустойки в тексте не установлена",
                                 evidence=[ev(doc, p, s)])
    return Extracted(field="penalty", missing_reason="Условие о неустойке не найдено")


__all__ = ["supplier", "amount", "delivery", "penalty"]
