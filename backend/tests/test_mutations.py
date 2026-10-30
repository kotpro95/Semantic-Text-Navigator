"""Сценарии встречи: меняем поле, добавляем новый договор, ломаем статусы."""
from datetime import date

from app.models import FieldStatus
from app.queries import delivery_before

from .conftest import AS_OF, run

NEW_CONTRACT = """ДОГОВОР ПОСТАВКИ № STN-104
Дата: 01.03.2026
Статус: подписан обеими сторонами 02.03.2026.

1.1. Покупатель: ООО «СеверМет». Поставщик: ООО «Альфа Трейд».
1.2. Предмет: поставка кабельной продукции.

2.1. Общая стоимость поставки составляет 2 450 500 (два миллиона четыреста пятьдесят тысяч пятьсот) рублей, включая НДС. Указанная сумма — итоговая стоимость договора.

3.1. Поставщик обязуется поставить продукцию не позднее 25.03.2026.

4.1. Неустойка за просрочку поставки составляет 0,2% стоимости просроченной части поставки за каждый день, но не более 8% стоимости этой части.
"""


def test_changed_amount_in_contract(texts):
    texts["03_contract.txt"] = texts["03_contract.txt"].replace("840 000 (восемьсот сорок тысяч)", "910 000 (девятьсот десять тысяч)")
    v, _, _ = run(texts)
    assert v["STN-102"].fields["amount"].value == "910000"


def test_changed_delivery_moves_contract_out_of_q4(texts):
    texts["03_contract.txt"] = texts["03_contract.txt"].replace("не позднее 20.03.2026", "не позднее 15.04.2026")
    v, _, _ = run(texts)
    a = delivery_before(list(v.values()), date(2026, 4, 1), AS_OF)
    assert a.matches == []
    assert "STN-102" in a.text  # несогласованный перенос всё равно упомянут


def test_new_contract_same_format(texts):
    texts["07_new.txt"] = NEW_CONTRACT
    v, _, _ = run(texts)
    c = v["STN-104"]
    assert c.fields["supplier"].display == "ООО «Альфа Трейд»"
    assert c.fields["amount"].value == "2450500"
    assert c.fields["delivery"].display == "25.03.2026"
    assert c.fields["penalty"].display == "0,2% в день, не более 8%"
    a = delivery_before(list(v.values()), date(2026, 4, 1), AS_OF)
    assert [m["contract"] for m in a.matches] == ["STN-102", "STN-104"]


def test_file_names_do_not_matter(texts):
    renamed = {f"z{i}_{'x' * i}.txt": t for i, t in enumerate(reversed(list(texts.values())))}
    v1, _, _ = run(texts)
    v2, _, _ = run(renamed)
    for n in v1:
        for f in ("amount", "delivery", "supplier"):
            assert v1[n].fields[f].value == v2[n].fields[f].value


def test_as_of_before_amendment(texts):
    v, _, _ = run(texts, date(2026, 2, 28))
    f = v["STN-101"].fields["delivery"]
    assert f.value == "2026-04-15" and f.status == FieldStatus.ok
    assert any(p.doc_label == "ДС № 1 к STN-101" for p in v["STN-101"].pending)


def test_amendment_effective_after_as_of_is_pending(texts):
    texts["02_amendment_signed.txt"] = texts["02_amendment_signed.txt"].replace(
        "вступает в силу 01.03.2026", "вступает в силу 20.03.2026")
    v, _, _ = run(texts)
    assert v["STN-101"].fields["delivery"].value == "2026-04-15"
    p = [p for p in v["STN-101"].pending if p.doc_label == "ДС № 1 к STN-101"]
    assert p and "вступает в силу 20.03.2026" in p[0].reason


def test_amendment_signed_by_one_side_is_pending(texts):
    texts["02_amendment_signed.txt"] = texts["02_amendment_signed.txt"].replace(
        "Статус: подписано обеими сторонами 01.03.2026.", "Статус: подписано поставщиком 01.03.2026.")
    v, _, _ = run(texts)
    assert v["STN-101"].fields["amount"].value == "1200000"
    assert any(p.proposed_display == "1 380 000" for p in v["STN-101"].pending)


def test_amendment_without_effective_date_needs_review(texts):
    texts["02_amendment_signed.txt"] = texts["02_amendment_signed.txt"].replace(
        "4. Настоящее соглашение вступает в силу 01.03.2026.", "")
    v, _, _ = run(texts)
    assert v["STN-101"].fields["delivery"].value == "2026-04-15"
    assert any("дата вступления" in f.text for f in v["STN-101"].flags)


def test_conflicting_amendments_same_date_need_review(texts):
    texts["08_amend3.txt"] = texts["02_amendment_signed.txt"].replace("№ 1", "№ 3").replace("30.04.2026", "05.05.2026")
    v, _, _ = run(texts)
    assert v["STN-101"].fields["delivery"].status == FieldStatus.review


def test_missing_supplier_is_no_data(texts):
    texts["01_contract.txt"] = texts["01_contract.txt"].replace(" Поставщик: ООО «Вектор Прибор».", "")
    v, _, _ = run(texts)
    f = v["STN-101"].fields["supplier"]
    assert f.value is None and f.status == FieldStatus.missing


def test_orphan_document_is_flagged(texts):
    texts["09_letter.txt"] = texts["05_supplier_email.txt"].replace("STN-102", "STN-999")
    _, flags, _ = run(texts)
    assert any("STN-999" in f.text for f in flags)
