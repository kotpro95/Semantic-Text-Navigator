"""Опциональное «второе мнение» локальной LLM (Ollama). По умолчанию выключено.

LLM не определяет ответ — только перепроверяет извлечение из текста договора.
Ответ модели принимается к сравнению, только если её цитата дословно есть в
тексте; расхождение с правилами показывается как «требует проверки».
Включение: OLLAMA_URL=http://localhost:11434 [OLLAMA_MODEL=qwen2.5:7b-instruct]
"""
from __future__ import annotations

import json
import os
import re

import httpx

from .models import ContractView, Document, StepState
from .parsing.segment import parse_date, parse_money

URL = os.getenv("OLLAMA_URL", "").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

PROMPT = """Ты извлекаешь условия из договора поставки. Верни ТОЛЬКО JSON:
{{"amount": {{"value": "<сумма договора в рублях цифрами или null>", "quote": "<точная цитата или null>"}},
 "delivery": {{"value": "<срок поставки ДД.ММ.ГГГГ или null>", "quote": "<точная цитата или null>"}}}}
Правила: аванс, лимит бюджета, срок оплаты и дата приёмки — НЕ сумма и НЕ срок поставки.
Если значения в тексте нет — null. Ничего не придумывай.

Текст договора:
{text}"""


def status() -> dict:
    return {"enabled": bool(URL), "model": MODEL if URL else None}


def _norm(field: str, v: str | None) -> str | None:
    if not v:
        return None
    if field == "amount":
        m = parse_money(v + " руб") or (int(re.sub(r"\D", "", v)) if re.sub(r"\D", "", v) else None)
        return str(m) if m else None
    d = parse_date(v)
    return d.isoformat() if d else None


def cross_check(view: ContractView, contract: Document | None) -> dict:
    if not URL:
        return {"enabled": False, "message": "LLM выключена: задайте OLLAMA_URL, чтобы включить сверку"}
    try:
        r = httpx.post(f"{URL}/api/generate", timeout=120,
                       json={"model": MODEL, "prompt": PROMPT.format(text=contract.text),
                             "format": "json", "stream": False, "options": {"temperature": 0}})
        r.raise_for_status()
        data = json.loads(r.json()["response"])
    except Exception as e:  # сеть, модель не скачана, невалидный JSON
        return {"enabled": True, "error": f"LLM недоступна: {e}"}

    results = []
    for field in ("amount", "delivery"):
        f = view.fields[field]
        base = next((h for h in f.history if h.state in (StepState.base, StepState.superseded)
                     and h.doc_id == view.doc_id), None)
        rule_value = None
        if base and base.display:
            rule_value = _norm(field, base.display)
        got = data.get(field) or {}
        quote = (got.get("quote") or "").strip()
        llm_value = _norm(field, got.get("value"))
        quote_ok = bool(quote) and quote in contract.text
        if llm_value and not quote_ok:
            verdict = "rejected"   # цитаты нет в тексте — ответ модели отбрасываем
        elif llm_value == rule_value:
            verdict = "agree"
        else:
            verdict = "disagree"   # → требует проверки
        results.append({"field": field, "rules": rule_value, "llm": llm_value, "quote": quote,
                        "quote_found": quote_ok, "verdict": verdict})
    return {"enabled": True, "model": MODEL, "results": results}
