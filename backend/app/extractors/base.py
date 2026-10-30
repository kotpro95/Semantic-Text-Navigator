"""Реестр экстракторов полей. Новое поле = новый модуль с функцией под @register.

Экстрактор получает документ и список абзацев (для ДС — абзацы с текстом новой
редакции пункта) и возвращает Extracted. Правило для всех: значение принимается,
только если есть цитата — точная подстрока абзаца. Иначе — «нет данных».
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..models import Document, Evidence, Extracted, Paragraph


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    fn: Callable[[Document, list[Paragraph]], Extracted]
    in_registry: bool = True   # показывать колонкой в реестре


REGISTRY: dict[str, FieldSpec] = {}


def register(name: str, label: str, in_registry: bool = True):
    def deco(fn):
        REGISTRY[name] = FieldSpec(name, label, fn, in_registry)
        return fn
    return deco


def ev(doc: Document, p: Paragraph, quote: str) -> Evidence:
    quote = quote.strip()
    if quote not in p.text:
        raise ValueError(f"Цитата не найдена в абзаце {p.n} файла {doc.filename}: {quote!r}")
    return Evidence(doc_id=doc.id, filename=doc.filename, paragraph=p.n, quote=quote, doc_label=doc.label)


def extract_all(doc: Document, paras: list[Paragraph] | None = None) -> dict[str, Extracted]:
    paras = doc.paragraphs if paras is None else paras
    return {name: spec.fn(doc, paras) for name, spec in REGISTRY.items()}
