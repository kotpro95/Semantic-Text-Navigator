"""Эталонные ответы на учебном комплекте (дата проверки 10.03.2026)."""
from datetime import date

from app.models import FieldStatus
from app.queries import delivery_before, field_answer

from .conftest import AS_OF, run


def test_registry_three_contracts(texts):
    v, flags, _ = run(texts)
    assert sorted(v) == ["STN-101", "STN-102", "STN-103"]
    assert v["STN-101"].fields["supplier"].display == "ООО «Вектор Прибор»"
    assert v["STN-102"].fields["supplier"].display == "ООО «Контур Электро»"
    assert v["STN-103"].fields["supplier"].display == "ООО «ПромСнаб Сервис»"
    assert flags == []


def test_q1_stn101_delivery_changed_by_signed_amendment(texts):
    v, _, _ = run(texts)
    f = v["STN-101"].fields["delivery"]
    assert f.value == "2026-04-30" and f.status == FieldStatus.changed
    assert f.changed_by == "ДС № 1 к STN-101"
    assert f.evidence[0].filename == "02_amendment_signed.txt"
    assert "30.04.2026" in f.evidence[0].quote
    # исходное значение договора сохранено в истории как заменённое
    assert [h.state.value for h in f.history] == ["superseded", "applied", "pending"]
    assert f.history[0].display == "15.04.2026"
    # проект ДС №2 — только как предложение
    pend = [p for p in v["STN-101"].pending if p.field == "delivery"]
    assert len(pend) == 1 and pend[0].proposed_display == "10.05.2026"
    assert pend[0].evidence.filename == "06_amendment_draft.txt"


def test_stn101_amount_from_amendment_not_draft(texts):
    v, _, _ = run(texts)
    f = v["STN-101"].fields["amount"]
    assert f.value == "1380000" and f.changed_by == "ДС № 1 к STN-101"
    assert any(p.proposed_display == "1 450 000" for p in v["STN-101"].pending)


def test_q2_stn102_amount_not_advance(texts):
    v, _, _ = run(texts)
    f = v["STN-102"].fields["amount"]
    assert f.value == "840000" and f.status == FieldStatus.ok
    assert f.evidence[0].filename == "03_contract.txt"
    assert any(r.display == "252 000" for r in f.rejected)


def test_q3_stn103_amount_no_data(texts):
    v, _, _ = run(texts)
    f = v["STN-103"].fields["amount"]
    assert f.value is None and f.status == FieldStatus.missing
    assert "приложении № 1" in f.evidence[0].quote   # объясняющая цитата
    assert any(r.display == "600 000" and "лимит" in r.reason for r in f.rejected)


def test_q4_delivery_before_april(texts):
    v, _, _ = run(texts)
    a = delivery_before(list(v.values()), date(2026, 4, 1), AS_OF)
    assert [m["contract"] for m in a.matches] == ["STN-102"]
    m = a.matches[0]
    assert m["display"] == "20.03.2026"
    assert m["pending"][0]["proposed_display"] == "27.03.2026"
    assert m["pending"][0]["evidence"]["filename"] == "05_supplier_email.txt"


def test_payment_and_acceptance_dates_are_not_delivery(texts):
    v, _, _ = run(texts)
    assert v["STN-102"].fields["delivery"].value == "2026-03-20"
    assert any(r.display == "10.04.2026" for r in v["STN-102"].fields["delivery"].rejected)


def test_penalty_extracted_with_quote(texts):
    v, _, _ = run(texts)
    assert v["STN-101"].fields["penalty"].display == "0,1% в день, не более 10%"
    assert v["STN-102"].fields["penalty"].display == "0,05% в день, не более 5%"
    assert v["STN-103"].fields["penalty"].status == FieldStatus.missing


def test_every_quote_is_exact_substring_of_its_paragraph(texts):
    v, _, docs = run(texts)
    by_id = {d.id: d for d in docs}
    evs = []
    for c in v.values():
        for f in c.fields.values():
            evs += f.evidence + [r.evidence for r in f.rejected]
            for h in f.history:
                evs += h.evidence
        evs += [p.evidence for p in c.pending]
    assert evs
    for e in evs:
        para = by_id[e.doc_id].paragraphs[e.paragraph - 1]
        assert e.quote and e.quote in para.text


def test_field_answer_text(texts):
    v, _, _ = run(texts)
    a = field_answer(list(v.values()), "STN-103", "amount", AS_OF)
    assert "нет данных" in a.text
