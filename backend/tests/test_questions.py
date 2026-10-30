"""Свободные вопросы: правила понимают перефразировки, LLM — запасной путь, ответ всегда от правил."""
import pytest
from fastapi.testclient import TestClient

from app import llm
from app.main import app
from app.store import store

from .conftest import DOCS

client = TestClient(app)


@pytest.fixture(autouse=True)
def samples(monkeypatch):
    store.clear()
    for p in sorted(DOCS.glob("*.txt")):
        store.add(p.name, p.read_text(encoding="utf-8"))
    monkeypatch.setattr(llm, "_enabled", False)
    yield
    store.clear()


def ask(q):
    return client.get("/api/ask", params={"q": q})


@pytest.mark.parametrize("q,contract,field,display", [
    ("Сколько платим Контуру Электро?", "STN-102", "amount", "840 000"),
    ("Какова цена договора с Вектор Прибор?", "STN-101", "amount", "1 380 000"),
    ("Когда привезут по STN-101?", "STN-101", "delivery", "30.04.2026"),
    ("Сколько дней до поставки STN-102?", "STN-102", "delivery", "20.03.2026"),
    ("Какова сумма поставки по STN-101?", "STN-101", "amount", "1 380 000"),
    ("Какие пени по ПромСнаб?", "STN-103", "penalty", None),
    ("Кто поставщик по STN-103?", "STN-103", "supplier", "ООО «ПромСнаб Сервис»"),
])
def test_paraphrases_by_rules(q, contract, field, display):
    a = ask(q).json()
    assert a["contract"] == contract and a["field"]["field"] == field and a["field"]["display"] == display
    assert a["parsed_by"] == "правила" and contract in a["understood"]


def test_month_only_and_date_before():
    for q in ("Что поставят раньше апреля?", "Какие поставки до 01.04.2026?"):
        a = ask(q).json()
        assert [m["contract"] for m in a["matches"]] == ["STN-102"]
        assert "01.04.2026" in a["understood"]


def test_as_of_from_question():
    a = ask("Какой срок поставки по Вектор Прибор на 28 февраля 2026?").json()
    assert a["field"]["display"] == "15.04.2026" and "28.02.2026" in a["understood"]


def test_unclear_asks_to_clarify_without_guessing():
    r = ask("Что там по Контур Электро?")
    assert r.status_code == 422 and "STN-102" in r.json()["detail"]
    assert ask("привет").status_code == 422


def test_llm_fallback_only_parses(monkeypatch):
    monkeypatch.setattr(llm, "parse_question", lambda q, c: {"type": "field", "contract": "STN-102", "field": "amount", "date": None})
    a = ask("расскажи про тот самый договор подробнее").json()
    assert a["parsed_by"].startswith("LLM") and a["field"]["display"] == "840 000"
    assert a["field"]["evidence"][0]["filename"] == "03_contract.txt"  # ответ — от правил, с цитатой


class _Resp:
    def __init__(self, body): self.body = body
    def raise_for_status(self): pass
    def json(self): return {"response": self.body}


@pytest.mark.parametrize("body,expected", [
    ('{"type":"field","contract":"STN-999","field":"amount"}', {"contract": None, "field": "amount"}),  # чужой договор отброшен
    ('{"type":"field","contract":"STN-101","field":"price"}', {"contract": "STN-101", "field": None}),  # неизвестное поле отброшено
    ('{"type":"field","contract":"STN-999","field":"price"}', None),                                   # ничего годного
    ('{"type":"delivery_before","date":null}', None),                                                 # нет даты
    ('не json', None),
])
def test_llm_answer_is_validated(monkeypatch, body, expected):
    monkeypatch.setattr(llm, "_enabled", True)
    monkeypatch.setattr(llm, "availability", lambda: {"available": True, "reason": None})
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: _Resp(body))
    r = llm.parse_question("вопрос", [("STN-101", "ООО «Вектор Прибор»")])
    assert (r and {"contract": r["contract"], "field": r["field"]}) == expected if expected else r is None


def test_rules_and_llm_are_merged(monkeypatch):
    # правила поняли договор (по поставщику), модель — поле
    monkeypatch.setattr(llm, "parse_question", lambda q, c: {"type": "field", "contract": None, "field": "delivery", "date": None})
    a = ask("Что там по Контур Электро?").json()
    assert a["contract"] == "STN-102" and a["field"]["field"] == "delivery" and a["parsed_by"] == "правила + LLM"


def test_cost_synonym():
    assert ask("Во что нам обойдётся Контур Электро?").json()["field"]["display"] == "840 000"
