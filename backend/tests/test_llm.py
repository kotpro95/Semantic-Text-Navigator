"""LLM-сверка: модель подменяется, проверяется только логика слияния с правилами."""
import pytest

from app import llm
from app.models import FieldStatus

from .conftest import run


@pytest.fixture
def llm_on(monkeypatch):
    monkeypatch.setattr(llm, "_enabled", True)
    llm.reset_cache()
    yield
    llm.reset_cache()


def _with_llm(texts, answers: dict):
    """answers: имя файла → ответ модели. Прогоняем реестр и применяем «готовые» ответы."""
    views, _, docs = run(texts)
    by_name = {d.filename: d for d in docs}
    for name, res in answers.items():
        llm._jobs[by_name[name].id] = {"state": "done", "result": res}
    for v in views.values():
        llm.apply(v, next(d for d in docs if d.id == v.doc_id))
    return views


def test_agree(texts, llm_on):
    v = _with_llm(texts, {"03_contract.txt": {
        "amount": {"value": "840000", "quote": "Общая стоимость поставки составляет 840 000 (восемьсот сорок тысяч) рублей, включая НДС."},
        "delivery": {"value": "20.03.2026", "quote": "Поставщик обязуется поставить комплектующие не позднее 20.03.2026."}}})
    f = v["STN-102"].fields["amount"]
    assert f.llm.verdict == "agree" and f.status == FieldStatus.ok


def test_disagree_marks_review(texts, llm_on):
    v = _with_llm(texts, {"03_contract.txt": {
        "amount": {"value": "252000", "quote": "Общая стоимость поставки составляет 840 000"},
        "delivery": {"value": None, "quote": None}}})
    f = v["STN-102"].fields["amount"]
    assert f.llm.verdict == "disagree" and f.status == FieldStatus.review and f.value == "840000"


def test_trap_is_rejected_limit_not_price(texts, llm_on):
    v = _with_llm(texts, {"04_contract.txt": {
        "amount": {"value": "600000", "quote": "Лимит закупки по внутреннему бюджету покупателя — 600 000 рублей."},
        "delivery": {"value": "30.04.2026", "quote": "Поставщик обязуется поставить запасные части не позднее 30.04.2026."}}})
    f = v["STN-103"].fields["amount"]
    assert f.llm.verdict == "rejected" and "лимит" in f.llm.note
    assert f.status == FieldStatus.missing and f.value is None  # «нет данных» сохранилось


def test_quote_not_in_text_is_rejected(texts, llm_on):
    v = _with_llm(texts, {"04_contract.txt": {
        "amount": {"value": "700000", "quote": "Стоимость договора составляет 700 000 рублей."},
        "delivery": {"value": None, "quote": None}}})
    f = v["STN-103"].fields["amount"]
    assert f.llm.verdict == "rejected" and f.value is None


def test_fallback_fills_with_review_when_rules_miss(texts, llm_on):
    texts["04_contract.txt"] = texts["04_contract.txt"].replace(
        "2.1. Общая стоимость определяется спецификацией в приложении № 1. Приложение № 1 в предоставленный комплект документов не входит. Числовое значение стоимости в тексте договора не указано.",
        "2.1. Покупатель оплачивает поставщику 455 000 руб. за весь объём поставки.")
    v = _with_llm(texts, {"04_contract.txt": {
        "amount": {"value": "455000", "quote": "Покупатель оплачивает поставщику 455 000 руб. за весь объём поставки."},
        "delivery": {"value": None, "quote": None}}})
    f = v["STN-103"].fields["amount"]
    assert f.llm.verdict == "filled" and f.value == "455000" and f.status == FieldStatus.review
    assert f.evidence[0].quote in texts["04_contract.txt"]
    assert any("найдено LLM" in fl.text for fl in v["STN-103"].flags)


def test_amendment_value_not_overwritten(texts, llm_on):
    v = _with_llm(texts, {"01_contract.txt": {
        "amount": {"value": "1200000", "quote": "Общая стоимость поставки составляет 1 200 000"},
        "delivery": {"value": "15.04.2026", "quote": "Поставщик обязуется поставить оборудование не позднее 15.04.2026."}}})
    f = v["STN-101"].fields["delivery"]
    assert f.value == "2026-04-30" and f.status == FieldStatus.changed and f.llm.verdict == "agree"


def test_disabled_changes_nothing(texts, monkeypatch):
    monkeypatch.setattr(llm, "_enabled", False)
    v, _, _ = run(texts)
    assert all(f.llm is None for c in v.values() for f in c.fields.values())
