"""Изменения условий из ДС, проектов и писем.

Два шаблона:
1) «Пункт X.Y договора изложить в следующей редакции: «…»» — на новой редакции
   запускаются те же экстракторы, что и на договоре;
2) предложение с глаголом изменения («изменить … на …», «перенести … с … на …»)
   и ключевым словом поля — новое значение берётся после последнего «на».
"""
from __future__ import annotations

import re

from .extractors import REGISTRY
from .extractors.base import ev
from .models import Change, Document, Paragraph
from .parsing.segment import all_dates, fmt_date, fmt_money, parse_money, sentences

REDACTION_RE = re.compile(r"[Пп]ункт\s+(\d+(?:\.\d+)*)\s+договора\s+изложить\s+в\s+(?:следующей\s+)?редакции\s*:\s*«(.+)»")
CHANGE_VERB_RE = re.compile(r"\b(изменить|изложить|перенести|установить|увеличить|уменьшить|продлить|сдвинуть)\b", re.I)
FIELD_KEYWORDS = {
    "amount": re.compile(r"стоимост|цен[аыу]\b|сумм", re.I),
    "delivery": re.compile(r"срок\w*\s+поставк|поставк\w*.*\bсрок|дат\w+\s+поставк", re.I),
    "penalty": re.compile(r"неустойк|пен[ия]", re.I),
}


def _redaction_changes(doc: Document, p: Paragraph) -> list[Change]:
    m = REDACTION_RE.search(p.text)
    if not m:
        return []
    inner = m.group(2)
    pseudo = Paragraph(n=p.n, clause=m.group(1), text=inner, start=p.start, end=p.end)
    out = []
    for name, spec in REGISTRY.items():
        r = spec.fn(doc, [pseudo])
        if r.value is not None:
            # цитата экстрактора — подстрока inner, а значит и абзаца ДС
            out.append(Change(field=name, value=r.value, display=r.display,
                              evidence=ev(doc, p, r.evidence[0].quote)))
    return out


def _sentence_changes(doc: Document, p: Paragraph) -> list[Change]:
    out = []
    for s in sentences(p.text):
        if not CHANGE_VERB_RE.search(s):
            continue
        tail = s[s.lower().rfind(" на ") + 4:] if " на " in s.lower() else s
        if FIELD_KEYWORDS["delivery"].search(s):
            dates = all_dates(tail) or all_dates(s)
            if dates:
                d = dates[-1]
                out.append(Change(field="delivery", value=d.isoformat(), display=fmt_date(d), evidence=ev(doc, p, s)))
                continue
        if FIELD_KEYWORDS["amount"].search(s):
            v = parse_money(tail) or parse_money(s)
            if v:
                out.append(Change(field="amount", value=str(v), display=fmt_money(v), evidence=ev(doc, p, s)))
                continue
        if FIELD_KEYWORDS["penalty"].search(s):
            r = REGISTRY["penalty"].fn(doc, [Paragraph(n=p.n, text=s, start=p.start, end=p.end)])
            if r.value:
                out.append(Change(field="penalty", value=r.value, display=r.display, evidence=ev(doc, p, s)))
    return out


def extract_changes(doc: Document) -> list[Change]:
    changes: list[Change] = []
    for p in doc.paragraphs[1:]:  # заголовок пропускаем
        if p.text.startswith(("Дата", "Статус", "От:", "Кому:", "Тема:")):
            continue
        found = _redaction_changes(doc, p) or _sentence_changes(doc, p)
        changes.extend(found)
    # одно поле — одно изменение на документ (первое по тексту)
    seen, uniq = set(), []
    for c in changes:
        if c.field not in seen:
            seen.add(c.field)
            uniq.append(c)
    return uniq
