from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from . import llm
from .extractors import REGISTRY
from .models import ContractView, Document, Flag
from .queries import FIELD_NAMES, Answer, delivery_before, describe, field_answer, parse_question, supplier_index
from .resolver import build_registry
from .store import store

router = APIRouter(prefix="/api")
DEFAULT_AS_OF = date(2026, 3, 10)
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "documents"
MAX_BYTES = 1_000_000


class DocSummary(BaseModel):
    id: str
    filename: str
    kind: str
    label: str
    contract_number: str | None
    signed: bool
    signed_date: date | None
    effective_date: date | None
    status_text: str | None
    issues: list[str]

    @classmethod
    def of(cls, d: Document) -> "DocSummary":
        return cls(id=d.id, filename=d.filename, kind=d.kind.value, label=d.label,
                   contract_number=d.contract_number, signed=d.signed, signed_date=d.signed_date,
                   effective_date=d.effective_date, status_text=d.status_text, issues=d.issues)


class Registry(BaseModel):
    as_of: date
    fields: list[dict]
    contracts: list[ContractView]
    flags: list[Flag]
    documents: list[DocSummary]
    llm: dict


def _decode(raw: bytes, name: str) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise HTTPException(400, f"{name}: не удалось прочитать как UTF-8 или Windows-1251")


def _views(as_of: date):
    """Реестр на дату + результат LLM-сверки (если переключатель включён)."""
    views, flags = build_registry(store.all(), as_of)
    docs = [store.get(v.doc_id) for v in views]
    llm.ensure([d for d in docs if d])
    for v, d in zip(views, docs):
        if d:
            llm.apply(v, d)
    return views, flags


class LlmToggle(BaseModel):
    enabled: bool


@router.get("/llm")
def llm_status():
    return llm.status()


@router.post("/llm")
def llm_toggle(body: LlmToggle):
    try:
        return llm.set_enabled(body.enabled)
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@router.post("/documents", response_model=list[DocSummary])
async def upload(files: list[UploadFile] = File(...)):
    out = []
    for f in files:
        if not (f.filename or "").lower().endswith(".txt"):
            raise HTTPException(400, f"{f.filename}: поддерживаются только TXT-файлы")
        raw = await f.read()
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, f"{f.filename}: файл больше 1 МБ")
        out.append(DocSummary.of(store.add(f.filename, _decode(raw, f.filename))))
    return out


@router.post("/documents/samples", response_model=list[DocSummary])
def load_samples():
    return [DocSummary.of(store.add(p.name, p.read_text(encoding="utf-8")))
            for p in sorted(SAMPLES_DIR.glob("*.txt"))]


@router.get("/documents", response_model=list[DocSummary])
def list_documents():
    return [DocSummary.of(d) for d in store.all()]


@router.get("/documents/{doc_id}", response_model=Document)
def get_document(doc_id: str):
    d = store.get(doc_id)
    if not d:
        raise HTTPException(404, "Документ не найден")
    return d


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    if not store.delete(doc_id):
        raise HTTPException(404, "Документ не найден")
    return {"ok": True}


@router.delete("/documents")
def clear_documents():
    store.clear()
    return {"ok": True}


@router.get("/registry", response_model=Registry)
def registry(as_of: date = Query(DEFAULT_AS_OF)):
    views, flags = _views(as_of)
    return Registry(as_of=as_of, contracts=views, flags=flags,
                    fields=[{"name": s.name, "label": s.label, "in_registry": s.in_registry} for s in REGISTRY.values()],
                    documents=[DocSummary.of(d) for d in store.all()], llm=llm.status([v.doc_id for v in views]))


@router.get("/contracts/{number}", response_model=ContractView)
def contract(number: str, as_of: date = Query(DEFAULT_AS_OF)):
    views, _ = _views(as_of)
    v = next((v for v in views if v.number.upper() == number.upper()), None)
    if not v:
        raise HTTPException(404, f"Договор {number} не загружен")
    return v


@router.get("/query", response_model=Answer)
def query(type: str = Query(..., pattern="^(field|delivery_before)$"),
          contract: str | None = None, field: str | None = None,
          date_: date | None = Query(None, alias="date"), as_of: date = Query(DEFAULT_AS_OF)):
    views, _ = _views(as_of)
    if type == "field":
        if not contract or field not in REGISTRY:
            raise HTTPException(400, f"Нужны contract и field ∈ {list(REGISTRY)}")
        return field_answer(views, contract, field, as_of)
    if not date_:
        raise HTTPException(400, "Нужен параметр date")
    return delivery_before(views, date_, as_of)


@router.get("/ask", response_model=Answer)
def ask(q: str, as_of: date = Query(DEFAULT_AS_OF)):
    """Свободный вопрос → структурный запрос → ответ правил с цитатами.
    1) правила: синонимы, словоформы, поставщик → договор; 2) не поняли — LLM (если включена);
    3) не поняла и она — просим уточнить. Модель только разбирает вопрос, но не отвечает."""
    base_views, _ = build_registry(store.all(), as_of)
    p = parse_question(q, as_of, supplier_index(base_views))
    parsed_by = "правила"
    if not p["ok"]:
        contracts = [(v.number, v.fields["supplier"].display or "") for v in base_views]
        m = llm.parse_question(q, contracts)
        if m and m["type"] == "delivery_before":
            parsed_by, p = f"LLM ({llm.MODEL})", {"type": "delivery_before", "date": m["date"], "as_of": as_of, "ok": True}
        elif m:
            # объединяем: что поняли правила — оставляем, недостающее берём у модели
            contract = p.get("contract") or m["contract"]
            field = p.get("field") or m["field"]
            parsed_by = "правила + LLM" if (p.get("contract") or p.get("field")) else f"LLM ({llm.MODEL})"
            p = {"type": "field", "contract": contract, "field": field,
                 "as_of": p.get("as_of") if p.get("as_of") != as_of else (m["date"] or as_of), "ok": bool(contract and field)}
    if not p["ok"]:
        hint = "Например: «Какова сумма договора STN-102?», «Когда поставка по Контур Электро?», «Какие поставки раньше 1 апреля 2026?»"
        if p["type"] == "field" and p.get("contract") and not p.get("field"):
            raise HTTPException(422, f"Понял договор {p['contract']}, но не понял, что именно нужно: сумма, срок поставки, неустойка или поставщик?")
        if p["type"] == "field" and p.get("field") and not p.get("contract"):
            raise HTTPException(422, f"Понял поле «{FIELD_NAMES[p['field']]}», но не понял договор. Укажите номер или поставщика. {hint}")
        raise HTTPException(422, f"Не понял вопрос. {hint}")
    if p["type"] == "delivery_before":
        views, _ = _views(as_of)
        a = delivery_before(views, p["date"], as_of)
    else:
        views, _ = _views(p["as_of"])
        a = field_answer(views, p["contract"], p["field"], p["as_of"])
    a.question, a.understood, a.parsed_by = q, describe(p), parsed_by
    return a
