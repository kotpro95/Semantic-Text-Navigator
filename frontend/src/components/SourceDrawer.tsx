import { useEffect, useRef, useState } from "react";
import type { ContractView, DocumentFull, Evidence } from "../api";
import { api, fmtDate } from "../api";
import { Badge, shortDoc } from "./common";
import type { Focus } from "./RegistryTable";

const STATE_TEXT = { base: "исходное", applied: "действует", superseded: "заменено", pending: "не согласовано" } as const;

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
  const closeRef = useRef<HTMLButtonElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);

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

  const aux = new Set([doc?.status_evidence?.paragraph, doc?.effective_evidence?.paragraph].filter(Boolean));
  const current = field?.history.find((h) => h.state === "applied" || h.state === "base");
  const go = (e: Evidence | undefined) => e && onFocus({ ...focus, evidence: e });

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Основание значения">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="kicker">Основание значения</span>
          <button ref={closeRef} className="linkbtn" onClick={onClose}>Закрыть ✕</button>
        </div>

        {field && contract && (
          <div>
            <h2>{field.label} · {contract.number}</h2>
            <div className="bigval">
              {field.status === "missing"
                ? <span style={{ font: "italic 28px var(--serif)", color: "var(--ink-muted)" }}>нет данных</span>
                : <span>{field.display}</span>}
              {field.status === "changed" && <Badge tone="sage">действует на {fmtDate(asOf)}</Badge>}
              {field.status === "ok" && <Badge tone="sage">из договора, не менялось</Badge>}
              {field.status === "review" && <Badge tone="red">требует проверки</Badge>}
              {field.status === "missing" && <Badge tone="red">не придумываем — проверьте</Badge>}
            </div>
            {field.note && <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>{field.note}</p>}
          </div>
        )}

        {field && field.history.length > 0 && (
          <div className="chain">
            <span className="kicker" style={{ paddingBottom: 6 }}>Как получено</span>
            {field.history.map((h, i) => (
              <button key={i} className={`step ${h.evidence[0]?.doc_id === ev?.doc_id && h.evidence[0]?.paragraph === ev?.paragraph ? "sel" : ""}`}
                onClick={() => go(h.evidence[0])}>
                <span className={`dot ${h.state}`} aria-label={STATE_TEXT[h.state]} />
                <span className="d">{h.date ? fmtDate(h.date) : "—"}</span>
                <span>
                  <span className="t">{shortDoc(h.doc_label)}</span><br />
                  <span className="r" style={{ color: h.state === "pending" ? "var(--ochre)" : h.state === "applied" ? "var(--sage)" : "var(--ink-muted)" }}>
                    {STATE_TEXT[h.state]} · {h.reason}
                  </span>
                </span>
                <span className={`x ${h.state}`}>{h.display}</span>
              </button>
            ))}
            {current && field.status === "changed" && (
              <span className="hint" style={{ paddingTop: 6 }}>Правило: условие меняет только подписанное обеими сторонами ДС, вступившее в силу к дате проверки.</span>
            )}
          </div>
        )}

        <div className="viewer">
          <div className="tab"><span>{doc?.filename ?? "…"}</span><span>{ev ? `абз. ${ev.paragraph} из ${doc?.paragraphs.length ?? "…"}` : ""}</span></div>
          <div className="page" ref={pageRef}>
            {err && <p className="err" style={{ paddingLeft: 16 }}>{err}</p>}
            {doc?.paragraphs.map((p) => {
              const kind = p.n === ev?.paragraph ? "main" : aux.has(p.n) ? "aux" : "";
              return (
                <div key={p.n} className={`para ${kind}`} ref={kind === "main" ? mainRef : undefined}>
                  <span className="bar" /><span className="n">¶{p.n}</span><span>{p.text}</span>
                </div>
              );
            })}
          </div>
          <div className="legend"><span>■ цитата-основание</span><span style={{ color: "var(--sage)" }}>■ статус и вступление в силу</span></div>
        </div>

        {ev && (
          <div className="quote">
            <span className="kicker">Точная цитата</span>
            <q>{ev.quote}</q>
            <span style={{ display: "flex", gap: 16 }}>
              <span className="src">{ev.filename} · ¶{ev.paragraph}</span>
              <button className="linkbtn" onClick={() => navigator.clipboard?.writeText(`«${ev.quote}» (${ev.filename}, абз. ${ev.paragraph})`).then(() => setCopied(true))}>
                {copied ? "Скопировано" : "Копировать"}
              </button>
            </span>
          </div>
        )}

        {field && field.rejected.length > 0 && (
          <div className="rej">
            <span className="kicker">Найдено в тексте, но не принято</span>
            {field.rejected.map((r, i) => (
              <button key={i} className="src" onClick={() => go(r.evidence)}>
                {r.display} — {r.reason} · ¶{r.evidence.paragraph}
              </button>
            ))}
          </div>
        )}
      </aside>
    </>
  );
}
