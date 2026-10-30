"""Действующие условия на дату проверки.

Правило задания: условие меняет только допсоглашение, подписанное обеими
сторонами и вступившее в силу к дате проверки. Проекты, письма и ДС с будущей
датой — «не согласовано / не вступило», показываются отдельно. Порядок
применения — по дате вступления в силу и номеру ДС, не по имени файла.
"""
from __future__ import annotations

from datetime import date

from .amendments import extract_changes
from .extractors import REGISTRY, extract_all
from .models import (Change, ContractView, DocKind, Document, FieldStatus, FieldView, Flag,
                     HistoryStep, PendingChange, StepState)
from .parsing.segment import fmt_date


def _applicability(doc: Document, as_of: date) -> tuple[bool, str]:
    """(применяется ли, объяснение)."""
    if doc.kind == DocKind.letter:
        return False, "предложение в письме, не оформлено подписанным ДС"
    if doc.kind == DocKind.amendment_draft or not doc.signed:
        return False, "проект: не подписан обеими сторонами"
    if doc.signed_date and doc.signed_date > as_of:
        return False, f"подписано {fmt_date(doc.signed_date)} — после даты проверки"
    if doc.effective_date is None:
        return False, "не указана дата вступления в силу — требуется проверка"
    if doc.effective_date > as_of:
        return False, f"вступает в силу {fmt_date(doc.effective_date)} — после даты проверки"
    return True, f"подписано обеими сторонами, в силе с {fmt_date(doc.effective_date)}"


def _amend_sort_key(doc: Document):
    num = int(doc.amendment_number) if (doc.amendment_number or "").isdigit() else 0
    return (doc.effective_date or date.max, num, doc.signed_date or date.max)


def build_contract(contract: Document, related: list[Document], as_of: date) -> ContractView:
    base = extract_all(contract)
    flags: list[Flag] = [Flag(level="review", text=i, doc_id=contract.id) for i in contract.issues]
    fields: dict[str, FieldView] = {}

    for name, spec in REGISTRY.items():
        ex = base[name]
        if ex.value is not None:
            status = FieldStatus.review if ex.ambiguous else FieldStatus.ok
            note = "В договоре несколько разных значений" if ex.ambiguous else None
            hist = [HistoryStep(state=StepState.base, date=contract.signed_date or contract.doc_date,
                                doc_id=contract.id, doc_label=contract.label, display=ex.display,
                                reason="исходное условие договора", evidence=ex.evidence)]
        else:
            status, note, hist = FieldStatus.missing, ex.missing_reason, []
        fields[name] = FieldView(field=name, label=spec.label, value=ex.value, display=ex.display,
                                 status=status, evidence=ex.evidence, note=note, history=hist,
                                 rejected=ex.rejected)

    pending: list[PendingChange] = []
    applied: list[tuple[Document, Change]] = []
    for doc in sorted(related, key=_amend_sort_key):
        if doc.kind == DocKind.unknown:
            flags.append(Flag(level="review", text=f"{doc.filename}: тип документа не распознан", doc_id=doc.id))
            continue
        ok, reason = _applicability(doc, as_of)
        changes = extract_changes(doc)
        if doc.kind in (DocKind.amendment, DocKind.amendment_draft) and not changes:
            flags.append(Flag(level="review", text=f"{doc.label}: не удалось распознать изменяемые условия", doc_id=doc.id))
        if ok:
            for ch in changes:
                applied.append((doc, ch))
        else:
            if doc.kind == DocKind.amendment and doc.signed and doc.effective_date is None:
                flags.append(Flag(level="review", text=f"{doc.label}: {reason}", doc_id=doc.id))
            for ch in changes:
                pending.append(PendingChange(field=ch.field, label=REGISTRY[ch.field].label,
                                             current_display=None, proposed_display=ch.display,
                                             doc_id=doc.id, doc_label=doc.label, reason=reason,
                                             evidence=ch.evidence))

    # применяем по порядку; конфликт в одну дату вступления — требует проверки
    last_eff: dict[str, tuple] = {}
    for doc, ch in applied:
        f = fields[ch.field]
        prev = last_eff.get(ch.field)
        if prev and prev[0] == doc.effective_date and prev[1] != ch.value:
            f.status = FieldStatus.review
            f.note = f"Два ДС с одной датой вступления в силу дают разные значения ({prev[2]} и {doc.label})"
        for h in f.history:
            if h.state in (StepState.base, StepState.applied):
                h.state = StepState.superseded
        reason = _applicability(doc, as_of)[1]
        f.history.append(HistoryStep(state=StepState.applied, date=doc.effective_date, doc_id=doc.id,
                                     doc_label=doc.label, display=ch.display, reason=reason, evidence=[ch.evidence]))
        f.value, f.display, f.evidence = ch.value, ch.display, [ch.evidence]
        if f.status != FieldStatus.review:
            f.status = FieldStatus.changed
            f.note = None
        f.changed_by = doc.label
        last_eff[ch.field] = (doc.effective_date, ch.value, doc.label)

    # предложения: показываем только отличающиеся от действующего значения
    kept = []
    for pc in pending:
        f = fields[pc.field]
        pc.current_display = f.display
        if f.display == pc.proposed_display:
            continue
        f.history.append(HistoryStep(state=StepState.pending, date=None, doc_id=pc.doc_id, doc_label=pc.doc_label,
                                     display=pc.proposed_display, reason=pc.reason, evidence=[pc.evidence]))
        kept.append(pc)

    for f in fields.values():
        if f.status == FieldStatus.missing and REGISTRY[f.field].in_registry:
            flags.append(Flag(level="review", text=f"{f.label.split(',')[0]} — нет данных. {f.note or 'Значение не найдено'}."))

    return ContractView(number=contract.contract_number or "?", doc_id=contract.id, filename=contract.filename,
                        fields=fields, pending=kept, flags=flags, related_docs=[d.id for d in related])


def build_registry(docs: list[Document], as_of: date) -> tuple[list[ContractView], list[Flag]]:
    contracts: dict[str, list[Document]] = {}
    others: dict[str, list[Document]] = {}
    global_flags: list[Flag] = []
    for d in docs:
        if d.kind == DocKind.contract and d.contract_number:
            contracts.setdefault(d.contract_number, []).append(d)
        elif d.contract_number:
            others.setdefault(d.contract_number, []).append(d)
        else:
            global_flags.append(Flag(level="review", text=f"{d.filename}: не удалось связать с договором", doc_id=d.id))

    views = []
    for number in sorted(contracts):
        docs_for = contracts[number]
        view = build_contract(docs_for[0], others.get(number, []), as_of)
        if len(docs_for) > 1:
            view.flags.insert(0, Flag(level="review", text=f"Загружено {len(docs_for)} текста договора {number} — используется {docs_for[0].filename}"))
        views.append(view)
    for number, ds in others.items():
        if number not in contracts:
            for d in ds:
                global_flags.append(Flag(level="review", text=f"{d.label}: договор {number} не загружен", doc_id=d.id))
    return views, global_flags
