"""Локальная LLM (Ollama) — «второе мнение» и страховка. Включается переключателем в UI.

Роль модели ограничена:
- правила остаются основным путём (детерминированно, покрыто тестами);
- модель независимо читает текст ДОГОВОРА и называет сумму и срок поставки с цитатой;
- ответ модели принимается к рассмотрению, только если цитата дословно есть в тексте
  и не попадает под те же «ловушки», что отсекают правила (аванс, лимит, срок оплаты…);
- совпало с правилами → «LLM подтверждает»; расходится → «Проверить»;
- правила дали «нет данных», а модель нашла подтверждённое цитатой значение →
  значение показывается, но со статусом «Проверить» и пометкой «найдено LLM».

Модель работает в фоне (один поток, CPU-машины медленные), результаты кэшируются
по id документа, интерфейс опрашивает прогресс. Без Ollama всё работает как раньше.
Настройка: OLLAMA_URL (по умолчанию http://localhost:11434), OLLAMA_MODEL (qwen2.5:3b).
"""
from __future__ import annotations

import json
import os
import queue
import re
import threading
import time

import httpx

from .extractors.fields import AMOUNT_NOT_PRICE, DELIVERY_NOT
from .models import ContractView, Document, Evidence, FieldStatus, Flag, LlmCheck, StepState
from .parsing.segment import fmt_date, fmt_money, parse_date, parse_money

URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
FIELDS = ("amount", "delivery")

PROMPT = """Ты извлекаешь условия из договора поставки на русском языке. Верни ТОЛЬКО JSON без пояснений:
{{"amount": {{"value": "<общая стоимость договора в рублях цифрами или null>", "quote": "<точная цитата из текста или null>"}},
 "delivery": {{"value": "<срок поставки ДД.ММ.ГГГГ или null>", "quote": "<точная цитата из текста или null>"}}}}
Правила:
- сумма — только общая (итоговая) стоимость договора; аванс, бюджетный лимит, часть стоимости — НЕ сумма;
- срок поставки — только срок поставки товара; срок оплаты и дата приёмки — НЕ срок поставки;
- если значения в тексте нет (например, стоимость в отсутствующем приложении) — null;
- цитату копируй из текста дословно. Ничего не придумывай.

Текст договора:
{text}"""

_lock = threading.Lock()
_enabled = False
_jobs: dict[str, dict] = {}          # doc_id -> {state, result, error, ms}
_queue: "queue.Queue[Document]" = queue.Queue()
_worker: threading.Thread | None = None
_avail_cache: tuple[float, dict] | None = None


def availability() -> dict:
    """Запущена ли Ollama и скачана ли модель. Кэш 5 с, чтобы не дёргать сервер на каждый запрос."""
    global _avail_cache
    now = time.time()
    if _avail_cache and now - _avail_cache[0] < 5:
        return _avail_cache[1]
    try:
        tags = httpx.get(f"{URL}/api/tags", timeout=1.5).json()
        names = [m.get("name", "") for m in tags.get("models", [])]
        has = any(n == MODEL or n.startswith(MODEL + ":") or n.split(":")[0] == MODEL for n in names)
        info = {"available": has, "reason": None if has else f"Модель {MODEL} не скачана: ollama pull {MODEL}"}
    except Exception:
        info = {"available": False, "reason": f"Ollama не запущена ({URL})"}
    _avail_cache = (now, info)
    return info


def status(contract_ids: list[str] | None = None) -> dict:
    a = availability()
    s = {"enabled": _enabled, "model": MODEL, "url": URL, **a}
    if contract_ids is not None:
        st = [(_jobs.get(i) or {}).get("state") for i in contract_ids]
        s["progress"] = {"total": len(contract_ids), "done": st.count("done"),
                         "errors": st.count("error"), "pending": len(contract_ids) - st.count("done") - st.count("error")}
    return s


def set_enabled(flag: bool) -> dict:
    global _enabled
    if flag:
        a = availability()
        if not a["available"]:
            raise RuntimeError(a["reason"])
    _enabled = flag
    return status()


def ensure(docs: list[Document]) -> None:
    """Поставить в очередь договоры, которых ещё нет в кэше."""
    if not _enabled:
        return
    global _worker
    with _lock:
        for d in docs:
            if d.id not in _jobs:
                _jobs[d.id] = {"state": "pending"}
                _queue.put(d)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, daemon=True)
            _worker.start()


def _run() -> None:
    while True:
        try:
            doc = _queue.get(timeout=30)
        except queue.Empty:
            return
        t = time.time()
        try:
            res = call_model(doc.text)
            _jobs[doc.id] = {"state": "done", "result": res, "ms": int((time.time() - t) * 1000)}
        except Exception as e:  # сеть, модель не загружена, невалидный JSON
            _jobs[doc.id] = {"state": "error", "error": str(e)[:200]}


def call_model(text: str) -> dict:
    r = httpx.post(f"{URL}/api/generate", timeout=300, json={
        "model": MODEL, "prompt": PROMPT.format(text=text), "format": "json", "stream": False,
        "keep_alive": "30m", "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 256}})
    r.raise_for_status()
    return json.loads(r.json()["response"])


def reset_cache() -> None:
    with _lock:
        _jobs.clear()


# ---------- слияние с правилами ----------

def _norm(field: str, v) -> str | None:
    if v in (None, "", "null"):
        return None
    v = str(v)
    if field == "amount":
        m = parse_money(v + " руб")
        if m is None:
            digits = re.sub(r"[^\d]", "", v.split(",")[0].split(".")[0])
            m = int(digits) if digits else None
        return str(m) if m is not None else None
    d = parse_date(v)
    return d.isoformat() if d else None


def _display(field: str, value: str) -> str:
    from datetime import date
    from decimal import Decimal
    return fmt_money(Decimal(value)) if field == "amount" else fmt_date(date.fromisoformat(value))


def _find_quote(doc: Document, quote: str) -> tuple[int, str] | None:
    q = quote.strip().strip("«»\"'").strip()
    for cand in (q, q.rstrip(".")):
        if len(cand) < 8:
            continue
        for p in doc.paragraphs:
            if cand in p.text:
                return p.n, cand
    return None


def _trap(field: str, quote: str) -> str | None:
    low = quote.lower()
    traps = AMOUNT_NOT_PRICE if field == "amount" else DELIVERY_NOT
    return next((why for key, why in traps.items() if key in low), None)


def apply(view: ContractView, contract: Document) -> None:
    """Добавить в поля договора результат LLM-сверки (если он готов)."""
    job = _jobs.get(contract.id)
    if not _enabled or not job:
        return
    for field in FIELDS:
        f = view.fields[field]
        if job["state"] != "done":
            f.llm = LlmCheck(verdict="pending" if job["state"] == "pending" else "error",
                             note="LLM проверяет…" if job["state"] == "pending" else f"LLM: ошибка — {job.get('error', '')}")
            continue
        got = (job["result"] or {}).get(field) or {}
        llm_val = _norm(field, got.get("value"))
        quote = (got.get("quote") or "").strip()
        base = next((h for h in f.history if h.doc_id == contract.id and h.state in (StepState.base, StepState.superseded)), None)
        rule_val = _norm(field, base.display) if base and base.display else None

        if llm_val is None:
            f.llm = LlmCheck(verdict="agree" if rule_val is None else "not_found",
                             note="LLM тоже не нашла значение" if rule_val is None else "LLM не нашла значение — остаётся результат правил")
            continue
        found = _find_quote(contract, quote) if quote else None
        disp = _display(field, llm_val)
        if not found:
            f.llm = LlmCheck(verdict="rejected", display=disp, quote=quote or None,
                             note="Цитата модели не найдена в тексте — ответ отброшен")
            continue
        para, q = found
        trap = _trap(field, q)
        if trap:
            f.llm = LlmCheck(verdict="rejected", display=disp, quote=q, paragraph=para,
                             note=f"Модель предложила {disp}, но {trap} — отброшено")
            continue
        if rule_val == llm_val:
            note = ("LLM подтверждает значение договора" if f.status != FieldStatus.changed
                    else f"LLM подтверждает исходное значение договора ({disp}); действующее задано: {f.changed_by}")
            f.llm = LlmCheck(verdict="agree", display=disp, quote=q, paragraph=para, note=note)
        elif rule_val is not None:
            f.llm = LlmCheck(verdict="disagree", display=disp, quote=q, paragraph=para,
                             note=f"LLM читает договор иначе: {disp} вместо {base.display}")
            f.status = FieldStatus.review
            f.note = f"Расхождение с LLM: {disp} вместо {base.display} — проверьте по тексту"
        elif f.status != FieldStatus.missing:
            # в договоре значения нет, но его задало подписанное ДС — значение ДС не трогаем
            f.llm = LlmCheck(verdict="not_found", display=disp, quote=q, paragraph=para,
                             note="Значение задано допсоглашением; LLM видит в договоре " + disp)
        else:
            # страховка: правила не нашли, модель нашла значение с дословной цитатой
            label = f.label.split(",")[0]
            view.flags = [fl for fl in view.flags if not fl.text.startswith(f"{label} — нет данных")]
            view.flags.append(Flag(level="review", text=f"{label}: найдено LLM, правила не распознали — проверьте"))
            f.llm = LlmCheck(verdict="filled", display=disp, quote=q, paragraph=para, note="Найдено LLM — проверьте")
            f.value, f.display, f.status = llm_val, disp, FieldStatus.review
            f.note = "Найдено LLM, правила значение не распознали — проверьте по цитате"
            f.evidence = [Evidence(doc_id=contract.id, filename=contract.filename, paragraph=para, quote=q,
                                   doc_label=contract.label)]
