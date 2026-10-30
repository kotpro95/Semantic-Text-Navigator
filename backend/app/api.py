from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from . import llm
from .extractors import REGISTRY
from .models import ContractView, Document, Flag
from .queries import Answer, delivery_before, field_answer, parse_question
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
    views, flags = build_registry(store.all(), as_of)
    return Registry(as_of=as_of, contracts=views, flags=flags,
                    fields=[{"name": s.name, "label": s.label, "in_registry": s.in_registry} for s in REGISTRY.values()],
                    documents=[DocSummary.of(d) for d in store.all()], llm=llm.status())


@router.get("/contracts/{number}", response_model=ContractView)
def contract(number: str, as_of: date = Query(DEFAULT_AS_OF)):
    views, _ = build_registry(store.all(), as_of)
    v = next((v for v in views if v.number.upper() == number.upper()), None)
    if not v:
        raise HTTPException(404, f"Договор {number} не загружен")
    return v


@router.get("/query", response_model=Answer)
def query(type: str = Query(..., pattern="^(field|delivery_before)$"),
          contract: str | None = None, field: str | None = None,
          date_: date | None = Query(None, alias="date"), as_of: date = Query(DEFAULT_AS_OF)):
    views, _ = build_registry(store.all(), as_of)
    if type == "field":
        if not contract or field not in REGISTRY:
            raise HTTPException(400, f"Нужны contract и field ∈ {list(REGISTRY)}")
        return field_answer(views, contract, field, as_of)
    if not date_:
        raise HTTPException(400, "Нужен параметр date")
    return delivery_before(views, date_, as_of)


@router.get("/ask", response_model=Answer)
def ask(q: str, as_of: date = Query(DEFAULT_AS_OF)):
    p = parse_question(q, as_of)
    if p["type"] == "delivery_before":
        if not p["date"]:
            raise HTTPException(422, "Укажите дату: «раньше 1 апреля 2026»")
        views, _ = build_registry(store.all(), as_of)
        a = delivery_before(views, p["date"], as_of)
    else:
        if not p["contract"] or not p["field"]:
            raise HTTPException(422, "Не понял вопрос. Укажите номер договора и поле: сумма, срок поставки, неустойка, поставщик")
        views, _ = build_registry(store.all(), p["as_of"])
        a = field_answer(views, p["contract"], p["field"], p["as_of"])
    a.question = q
    return a


@router.get("/contracts/{number}/llm-check")
def llm_check(number: str, as_of: date = Query(DEFAULT_AS_OF)):
    views, _ = build_registry(store.all(), as_of)
    v = next((v for v in views if v.number.upper() == number.upper()), None)
    if not v:
        raise HTTPException(404, f"Договор {number} не загружен")
    return llm.cross_check(v, store.get(v.doc_id))
