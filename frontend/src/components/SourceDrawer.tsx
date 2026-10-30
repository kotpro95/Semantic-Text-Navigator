import { useEffect, useRef, useState } from "react";
import type { ContractView, DocumentFull, Evidence } from "../api";
import { api, fmtDate } from "../api";
import { Hint, TERMS, shortDoc } from "./common";
import type { Focus } from "./DataTable";

const STEP = {
  base: { icon: "–", text: "исходное" },
  applied: { icon: "■", text: "действует" },
  superseded: { icon: "–", text: "заменено" },
  pending: { icon: "□", text: "не согласовано" },
} as const;

export function SourceDrawer({ focus, contract, asOf, onClose, onFocus }: {
  focus: Focus; contract: ContractView | undefined; asOf: string; onClose: () => void; onFocus: (f: Focus) => void;
}) {
  const field = contract?.fields[focus.field];
  const ev = focus.evidence;
  const docId = ev?.doc_id ?? contract?.doc_id;
  const [doc, setDoc] = useState<DocumentFull | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const mainRef = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!docId) return;
    setErr(null);
    api.document(docId).then(setDoc).catch((e) => setErr(String(e.message ?? e)));
  }, [docId]);
  useEffect(() => {
    // прокручиваем только окно документа, а не всю панель
    const el = mainRef.current, page = pageRef.current;
    if (el && page) page.scrollTop = el.offsetTop - page.offsetTop - page.clientHeight / 2 + el.clientHeight / 2;
  }, [doc, ev?.paragraph]);
  useEffect(() => {
    closeRef.current?.focus();
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  useEffect(() => setCopied(false), [ev?.quote]);

  const aux = new Set([doc?.status_evidence?.paragraph, doc?.effective_evidence?.paragraph].filter(Boolean));
  const go = (e: Evidence | undefined) => e && onFocus({ ...focus, evidence: e });
  const statusText = !field ? "" : {
    ok: "из договора, не менялось",
    changed: `действует на ${fmtDate(asOf)} · ${field.changed_by}`,
    missing: "нет в тексте — не подставляем догадку",
    review: "требует проверки",
  }[field.status];
  const statusCls = !field ? "" : field.status === "missing" || field.status === "review" ? "review" : "ok";

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Основание значения">
        <div className="head">
          <span className="kick">Основание · {contract?.number}</span>
          <button ref={closeRef} className="btn" onClick={onClose}>Закрыть <span className="muted mono">Esc</span></button>
        </div>

        {field && (
          <div style={{ display: "grid", gap: 4 }}>
            <h2>{field.label}</h2>
            <div className="bigval">
              {field.status === "missing" ? <span style={{ color: "var(--signal)", fontFamily: "var(--sans)" }}>нет данных</span> : <span>{field.display}</span>}
            </div>
            <span className={`st ${statusCls === "ok" ? "pending" : "review"}`} style={{ fontWeight: 400 }}>
              <i aria-hidden="true" style={statusCls === "ok" ? { background: "var(--ink)" } : undefined} />{statusText}
            </span>
            {field.note && field.status !== "changed" && <span className="muted" style={{ fontSize: 12.5 }}>{field.note}</span>}
          </div>
        )}

        {field && field.history.length > 0 && (
          <div>
            <div className="kick" style={{ display: "flex", gap: 6, alignItems: "center", paddingBottom: 6 }}>Как получено <Hint text={TERMS.ds} /></div>
            <div className="chain">
              {field.history.map((h, i) => {
                const e0 = h.evidence[0];
                const sel = e0?.doc_id === ev?.doc_id && e0?.paragraph === ev?.paragraph;
                return (
                  <button key={i} className={`step ${sel ? "sel" : ""}`} onClick={() => go(e0)}>
                    <span className={`i ${h.state}`} aria-hidden="true">{STEP[h.state].icon}</span>
                    <span className="d">{h.date ? fmtDate(h.date) : "—"}</span>
                    <span><span className="t">{shortDoc(h.doc_label)}</span> <span className="r">· {STEP[h.state].text}</span><br /><span className="r">{h.reason}</span></span>
                    <span className={`x ${h.state}`}>{h.display}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {ev && (
          <div className="quote">
            <span className="kick">Точная цитата</span>
            <q>{ev.quote}</q>
            <span style={{ display: "flex", gap: 14, fontSize: 12 }}>
              <span className="mono muted">{ev.filename} · абз. {ev.paragraph}</span>
              <button className="linkbtn" onClick={() => navigator.clipboard?.writeText(`«${ev.quote}» (${ev.filename}, абз. ${ev.paragraph})`).then(() => setCopied(true))}>
                {copied ? "Скопировано" : "Копировать"}
              </button>
            </span>
          </div>
        )}

        <div className="viewer">
          <div className="tab"><span>{doc?.filename ?? "…"}</span><span>{ev ? `абз. ${ev.paragraph} из ${doc?.paragraphs.length ?? "…"}` : ""}</span></div>
          <div className="page" ref={pageRef}>
            {err && <p className="err" style={{ paddingLeft: 12 }}>{err}</p>}
            {doc?.paragraphs.map((p) => {
              const kind = p.n === ev?.paragraph ? "main" : aux.has(p.n) ? "aux" : "";
              return (
                <div key={p.n} className={`para ${kind}`} ref={kind === "main" ? mainRef : undefined}>
                  <span className="bar" /><span className="n">{p.n}</span><span>{p.text}</span>
                </div>
              );
            })}
          </div>
          <div className="legend"><span>▮ цитата-основание</span><span>▮ статус и дата вступления (серым)</span></div>
        </div>

        {field?.llm && contract && (
          <div className="llm-box">
            <span className="kick">Сверка LLM</span>
            <span className={`st ${field.llm.verdict === "agree" ? "pending" : field.llm.verdict === "pending" ? "ok" : "review"}`} style={{ fontWeight: 400 }}>
              <i aria-hidden="true" style={field.llm.verdict === "agree" ? { background: "var(--ink)" } : undefined} />{field.llm.note}
            </span>
            {field.llm.quote && (
              <div className="cite">
                <q>{field.llm.quote}</q>
                {field.llm.paragraph && (
                  <button className="linkbtn" onClick={() => onFocus({ ...focus, evidence: { doc_id: contract.doc_id, filename: contract.filename, paragraph: field.llm!.paragraph!, quote: field.llm!.quote!, doc_label: contract.number } })}>
                    {contract.filename} · абз. {field.llm.paragraph}
                  </button>
                )}
              </div>
            )}
            <span className="muted" style={{ fontSize: 11.5 }}>Модель читает только текст договора; ответ принимается, если цитата дословно есть в тексте.</span>
          </div>
        )}

        {field && field.rejected.length > 0 && (
          <div className="rej">
            <span className="kick">Найдено в тексте, но не принято</span>
            {field.rejected.map((r, i) => (
              <button key={i} className="linkbtn" style={{ textAlign: "left" }} onClick={() => go(r.evidence)}>
                {r.display} — {r.reason} (абз. {r.evidence.paragraph})
              </button>
            ))}
          </div>
        )}
      </aside>
    </>
  );
}
