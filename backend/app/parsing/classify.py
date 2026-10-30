"""Определение типа и статуса документа по тексту (не по имени файла)."""
from __future__ import annotations

import hashlib
import re

from ..models import DocKind, Document, Evidence, Paragraph
from .segment import fmt_date, normalize, parse_date, segment

CONTRACT_NO_RE = re.compile(r"\b([A-ZА-ЯЁ]{2,6}-\d{2,})\b")
NUMBER_RE = re.compile(r"№\s*(\d+)")
DATE_LINE_RE = re.compile(r"^Дата(?:\s+проекта)?\s*:\s*(\d{2}\.\d{2}\.\d{4})", re.I)
STATUS_LINE_RE = re.compile(r"^Статус\s*:\s*(.+)$", re.I)
EFFECTIVE_RE = re.compile(r"вступа\w*\s+в\s+силу\s+(?:с\s+)?(\d{2}\.\d{2}\.\d{4})", re.I)
NEGATIVE_SIGN_RE = re.compile(r"\bне\s+подписан|\bпроект\b|на\s+согласовании", re.I)
SIGNED_BOTH_RE = re.compile(r"подписан\w*\s+обеими\s+сторонами", re.I)


def _ev(doc_id: str, filename: str, p: Paragraph, quote: str | None = None, label: str = "") -> Evidence:
    q = quote if quote is not None else p.text
    assert q in p.text, "цитата должна быть подстрокой абзаца"
    return Evidence(doc_id=doc_id, filename=filename, paragraph=p.n, quote=q, doc_label=label)


def doc_id_for(filename: str, text: str) -> str:
    return hashlib.sha1((filename + "\0" + text).encode("utf-8")).hexdigest()[:10]


def parse_document(filename: str, raw: str) -> Document:
    text = normalize(raw)
    paras = segment(text)
    did = doc_id_for(filename, text)
    title = paras[0].text if paras else ""
    up = title.upper()
    issues: list[str] = []

    has_from_to = any(p.text.startswith(("От:", "Кому:")) for p in paras[:6])
    if "СОГЛАШЕНИ" in up and "ПРОЕКТ" in up:
        kind = DocKind.amendment_draft
    elif "ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ" in up or "ДОП. СОГЛАШЕНИЕ" in up:
        kind = DocKind.amendment
    elif up.startswith("ДОГОВОР"):
        kind = DocKind.contract
    elif "ПИСЬМО" in up or has_from_to:
        kind = DocKind.letter
    else:
        kind = DocKind.unknown
        issues.append("Тип документа не распознан")

    m = CONTRACT_NO_RE.search(title)
    if not m:  # письмо: номер в теме или теле
        for p in paras:
            m = CONTRACT_NO_RE.search(p.text)
            if m:
                break
    contract_number = m.group(1) if m else None
    if not contract_number:
        issues.append("Не найден номер договора")

    amendment_number = None
    if kind in (DocKind.amendment, DocKind.amendment_draft):
        nm = NUMBER_RE.search(title)
        amendment_number = nm.group(1) if nm else None

    doc_date = None
    status_text = None
    status_p = None
    eff_date = None
    eff_p = None
    eff_quote = None
    for p in paras:
        if doc_date is None and (dm := DATE_LINE_RE.match(p.text)):
            doc_date = parse_date(dm.group(1))
        if status_text is None and (sm := STATUS_LINE_RE.match(p.text)):
            status_text, status_p = sm.group(1).strip(), p
        if eff_date is None and (em := EFFECTIVE_RE.search(p.text)):
            eff_date, eff_p, eff_quote = parse_date(em.group(1)), p, em.group(0)

    signed = False
    signed_date = None
    if status_text:
        if SIGNED_BOTH_RE.search(status_text) and not NEGATIVE_SIGN_RE.search(status_text):
            signed = True
            signed_date = parse_date(status_text) or doc_date
    elif kind in (DocKind.contract, DocKind.amendment):
        issues.append("Нет строки статуса — подписание не подтверждено")

    if kind == DocKind.amendment and not signed:
        # заголовок «ДС», но статус не «подписано обеими сторонами» — обращаемся как с проектом
        issues.append("Допсоглашение не подписано обеими сторонами")
    if kind == DocKind.contract and not signed:
        issues.append("Договор не подписан обеими сторонами")

    cn = contract_number or "?"
    if kind == DocKind.contract:
        label = f"Договор {cn}"
    elif kind == DocKind.amendment:
        label = f"ДС № {amendment_number or '?'} к {cn}"
    elif kind == DocKind.amendment_draft:
        label = f"Проект ДС № {amendment_number or '?'} к {cn}"
    elif kind == DocKind.letter:
        label = f"Письмо{(' от ' + fmt_date(doc_date)) if doc_date else ''} по {cn}"
    else:
        label = f"Документ {filename}"

    doc = Document(
        id=did, filename=filename, text=text, paragraphs=paras, kind=kind, label=label,
        contract_number=contract_number, amendment_number=amendment_number, doc_date=doc_date,
        signed=signed, signed_date=signed_date, effective_date=eff_date, status_text=status_text,
        issues=issues,
    )
    if status_p:
        doc.status_evidence = _ev(did, filename, status_p, label=label)
    if eff_p:
        doc.effective_evidence = _ev(did, filename, eff_p, eff_quote, label=label)
    return doc
