"""Модели данных. Любое значение, показанное пользователю, несёт Evidence —
точную цитату (подстроку исходного текста) и номер абзаца."""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocKind(str, Enum):
    contract = "contract"
    amendment = "amendment"            # допсоглашение (подписанное или нет — см. signed)
    amendment_draft = "amendment_draft"  # явно помеченный проект
    letter = "letter"
    unknown = "unknown"


class Paragraph(BaseModel):
    n: int                      # номер абзаца, с 1
    clause: Optional[str] = None  # номер пункта: "2.1", "3"
    text: str
    start: int                  # смещение в исходном тексте
    end: int


class Evidence(BaseModel):
    doc_id: str
    filename: str
    paragraph: int
    quote: str
    doc_label: str = ""


class Document(BaseModel):
    id: str
    filename: str
    text: str
    paragraphs: list[Paragraph]
    kind: DocKind
    label: str
    contract_number: Optional[str] = None
    amendment_number: Optional[str] = None
    doc_date: Optional[dt.date] = None
    signed: bool = False
    signed_date: Optional[dt.date] = None
    effective_date: Optional[dt.date] = None
    status_text: Optional[str] = None
    status_evidence: Optional[Evidence] = None
    effective_evidence: Optional[Evidence] = None
    issues: list[str] = Field(default_factory=list)


class Rejected(BaseModel):
    """Найденное в тексте число/дата, которое сознательно НЕ принято как значение поля."""
    display: str
    reason: str
    evidence: Evidence


class Extracted(BaseModel):
    """Результат экстрактора на одном документе."""
    field: str
    value: Optional[str] = None     # нормализованное значение: "1380000", "2026-04-30"
    display: Optional[str] = None   # как показать: "1 380 000", "30.04.2026"
    evidence: list[Evidence] = Field(default_factory=list)
    missing_reason: Optional[str] = None
    ambiguous: bool = False
    rejected: list[Rejected] = Field(default_factory=list)


class Change(BaseModel):
    """Изменение поля, найденное в ДС, проекте или письме."""
    field: str
    value: str
    display: str
    evidence: Evidence


class StepState(str, Enum):
    base = "base"              # исходное условие договора
    applied = "applied"        # применено (подписано и вступило в силу)
    superseded = "superseded"  # было действующим, затем заменено
    pending = "pending"        # не согласовано / не вступило в силу


class HistoryStep(BaseModel):
    state: StepState
    date: Optional[dt.date] = None
    doc_id: str
    doc_label: str
    display: Optional[str]
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)


class FieldStatus(str, Enum):
    ok = "ok"            # из договора, не менялось
    changed = "changed"  # изменено подписанным ДС
    missing = "missing"  # нет данных
    review = "review"    # требует проверки (противоречие/неоднозначность)


class FieldView(BaseModel):
    field: str
    label: str
    value: Optional[str] = None
    display: Optional[str] = None
    status: FieldStatus
    evidence: list[Evidence] = Field(default_factory=list)
    changed_by: Optional[str] = None
    note: Optional[str] = None
    history: list[HistoryStep] = Field(default_factory=list)
    rejected: list[Rejected] = Field(default_factory=list)
    llm: Optional["LlmCheck"] = None


class LlmCheck(BaseModel):
    """Сверка поля локальной LLM (Ollama) с правилами. Только по тексту договора."""
    verdict: str                     # agree | disagree | filled | rejected | not_found
    display: Optional[str] = None    # что нашла модель
    quote: Optional[str] = None      # цитата модели (принимается, только если дословно есть в тексте)
    paragraph: Optional[int] = None
    note: str = ""


class PendingChange(BaseModel):
    field: str
    label: str
    current_display: Optional[str]
    proposed_display: str
    doc_id: str
    doc_label: str
    reason: str
    evidence: Evidence


class Flag(BaseModel):
    level: str  # "review" | "info"
    text: str
    doc_id: Optional[str] = None


class ContractView(BaseModel):
    number: str
    doc_id: str
    filename: str
    fields: dict[str, FieldView]
    pending: list[PendingChange] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    related_docs: list[str] = Field(default_factory=list)


FieldView.model_rebuild()
