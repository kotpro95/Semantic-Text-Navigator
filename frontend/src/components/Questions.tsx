import { useState } from "react";
import type { Answer, DeliveryRow, Evidence } from "../api";
import { api, fmtDate } from "../api";
import { Badge } from "./common";
import type { Focus } from "./RegistryTable";

// Шаблоны вопросов закупщика. Ответ не вшит: текст уходит на /api/ask,
// где правила разбирают договор, поле и дату и считают ответ по загруженным документам.
const PRESETS = [
  "Какой срок поставки действует по договору STN-101 на 10 марта 2026 года?",
  "Какова сумма договора STN-102?",
  "Какова сумма договора STN-103?",
  "По каким договорам поставка запланирована раньше 1 апреля 2026 года и есть ли несогласованные изменения срока?",
];

function Quote({ ev, tone, onOpen }: { ev: Evidence; tone?: "ochre"; onOpen: (ev: Evidence) => void }) {
  return (
    <div className={`quote ${tone ?? ""}`}>
      <q>{ev.quote}</q>
      <button className="src" onClick={() => onOpen(ev)}>§ {ev.filename} · ¶{ev.paragraph} — открыть</button>
    </div>
  );
}

function Row({ r, onOpen }: { r: DeliveryRow; onOpen: (c: string, f: string, ev: Evidence) => void }) {
  return (
    <div className="arow">
      <span className="mono" style={{ fontWeight: 500, fontSize: 15 }}>{r.contract}</span>
      <span className="mono" style={{ fontWeight: 500, fontSize: 15 }}>{r.display ?? "нет данных"}</span>
      <div style={{ display: "grid", gap: 8, justifyItems: "start" }}>
        <Badge tone="sage">действует</Badge>
        {r.evidence.map((e, i) => <Quote key={i} ev={e} onOpen={(ev) => onOpen(r.contract, "delivery", ev)} />)}
        {r.pending.map((p, i) => (
          <div key={i} style={{ display: "grid", gap: 8, justifyItems: "start" }}>
            <Badge tone="ochre">Не согласовано: {p.doc_label} → {p.proposed_display}</Badge>
            <Quote ev={p.evidence} tone="ochre" onOpen={(ev) => onOpen(r.contract, "delivery", ev)} />
            <span className="hint">{p.reason}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Questions({ asOf, onOpen }: { asOf: string; onOpen: (f: Focus) => void }) {
  const [active, setActive] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [ans, setAns] = useState<Answer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = (contract: string, field: string, evidence: Evidence) => onOpen({ contract, field, evidence });

  const run = async (q: string, idx: number | null) => {
    setActive(idx); setErr(null); setBusy(true);
    try { setAns(await api.ask(q, asOf)); } catch (e) { setAns(null); setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <section aria-label="Вопросы закупщика">
      <div className="qhead"><h3>Вопросы закупщика</h3><span className="hint">ответ строится по загруженным документам</span></div>
      <div className="qgrid">
        {PRESETS.map((q, i) => (
          <button key={i} className={`q ${active === i ? "active" : ""}`} onClick={() => run(q, i)} aria-pressed={active === i}>
            <b>{i + 1}</b><span>{q}</span>
          </button>
        ))}
      </div>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); if (text.trim()) run(text, null); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} aria-label="Свой вопрос"
          placeholder="Свой вопрос: «Какая неустойка по STN-101?», «Срок поставки STN-102 на 1 марта 2026»" />
        <button className="btn" disabled={busy}>Спросить</button>
      </form>
      {err && <p className="err">{err}</p>}
      {ans && (
        <div className="answer" aria-live="polite">
          <span className="kicker">
            {active !== null ? `Ответ на вопрос ${active + 1}` : "Ответ"} · по состоянию на {fmtDate(ans.as_of)}
          </span>
          <p className="big">{ans.text}</p>
          {ans.kind === "field" && ans.field && (
            <div className="arow">
              <span className="mono" style={{ fontWeight: 500, fontSize: 15 }}>{ans.contract}</span>
              <span className="mono" style={{ fontWeight: 500, fontSize: 15 }}>
                {ans.field.status === "missing" ? <i style={{ fontFamily: "var(--serif)" }} className="muted">нет данных</i> : ans.field.display}
              </span>
              <div style={{ display: "grid", gap: 8, justifyItems: "start" }}>
                {ans.field.status === "changed" && <Badge tone="sage">изменено: {ans.field.changed_by}</Badge>}
                {ans.field.status === "missing" && <Badge tone="red">нет данных — проверьте</Badge>}
                {ans.field.evidence.map((e, i) => <Quote key={i} ev={e} onOpen={(ev) => open(ans.contract!, ans.field!.field, ev)} />)}
                {ans.field.rejected.map((r, i) => (
                  <span className="hint" key={i}>Не принято: {r.display} — {r.reason}</span>
                ))}
                {ans.pending.map((p, i) => (
                  <div key={i} style={{ display: "grid", gap: 8, justifyItems: "start" }}>
                    <Badge tone="ochre">Не согласовано: {p.doc_label} → {p.proposed_display}</Badge>
                    <Quote ev={p.evidence} tone="ochre" onOpen={(ev) => open(ans.contract!, p.field, ev)} />
                  </div>
                ))}
              </div>
            </div>
          )}
          {ans.kind === "delivery_before" && (
            <div>
              {ans.matches.map((r) => <Row key={r.contract} r={r} onOpen={open} />)}
              {ans.excluded.length > 0 && (
                <div className="arow">
                  <span className="hint">остальные</span><span className="hint">—</span>
                  <span className="muted" style={{ fontSize: 13 }}>
                    {ans.excluded.map((r) => `${r.contract}: ${r.reason}${r.pending.length ? ` (не согласовано: ${r.pending.map((p) => `${p.doc_label} → ${p.proposed_display}`).join(", ")})` : ""}`).join("; ")}
                  </span>
                </div>
              )}
            </div>
          )}
          <span className="hint">Запрос: {ans.question}</span>
        </div>
      )}
    </section>
  );
}
