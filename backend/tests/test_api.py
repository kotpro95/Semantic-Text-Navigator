from fastapi.testclient import TestClient

from app.main import app
from app.store import store

from .conftest import DOCS

client = TestClient(app)


def setup_function():
    store.clear()


def _upload_all():
    files = [("files", (p.name, p.read_bytes(), "text/plain")) for p in sorted(DOCS.glob("*.txt"))]
    r = client.post("/api/documents", files=files)
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_and_registry():
    docs = _upload_all()
    assert {d["kind"] for d in docs} == {"contract", "amendment", "amendment_draft", "letter"}
    reg = client.get("/api/registry", params={"as_of": "2026-03-10"}).json()
    by = {c["number"]: c for c in reg["contracts"]}
    assert by["STN-101"]["fields"]["delivery"]["display"] == "30.04.2026"
    assert by["STN-103"]["fields"]["amount"]["status"] == "missing"


def test_rejects_non_txt():
    r = client.post("/api/documents", files=[("files", ("a.pdf", b"x", "application/pdf"))])
    assert r.status_code == 400


def test_cp1251_upload():
    text = (DOCS / "03_contract.txt").read_text(encoding="utf-8")
    r = client.post("/api/documents", files=[("files", ("c.txt", text.encode("cp1251"), "text/plain"))])
    assert r.json()[0]["contract_number"] == "STN-102"


def test_document_paragraphs():
    docs = _upload_all()
    d = client.get(f"/api/documents/{docs[1]['id']}").json()
    assert d["paragraphs"][0]["n"] == 1


def test_four_questions_as_text():
    _upload_all()
    a1 = client.get("/api/ask", params={"q": "Какой срок поставки действует по договору STN-101 на 10 марта 2026 года?"}).json()
    assert a1["field"]["display"] == "30.04.2026"
    a2 = client.get("/api/ask", params={"q": "Какова сумма договора STN-102?"}).json()
    assert a2["field"]["display"] == "840 000"
    a3 = client.get("/api/ask", params={"q": "Какова сумма договора STN-103?"}).json()
    assert a3["field"]["status"] == "missing" and "нет данных" in a3["text"]
    a4 = client.get("/api/ask", params={"q": "По каким договорам поставка запланирована раньше 1 апреля 2026 года и есть ли несогласованные изменения срока?"}).json()
    assert [m["contract"] for m in a4["matches"]] == ["STN-102"]
    assert a4["matches"][0]["pending"]


def test_structured_query():
    _upload_all()
    r = client.get("/api/query", params={"type": "delivery_before", "date": "2026-04-01"}).json()
    assert [m["contract"] for m in r["matches"]] == ["STN-102"]


def test_llm_toggle_off_by_default_and_409_when_unavailable(monkeypatch):
    from app import llm
    monkeypatch.setattr(llm, "availability", lambda: {"available": False, "reason": "Ollama не запущена"})
    assert client.get("/api/llm").json()["enabled"] is False
    r = client.post("/api/llm", json={"enabled": True})
    assert r.status_code == 409 and "Ollama" in r.json()["detail"]
