import { Fragment, useRef, useState } from "react";
import type { Answer, DocSummary, Evidence } from "../api";
import { api, fmtDate } from "../api";
import { docStatus } from "./common";
import type { Focus } from "./DataTable";

export function useFileDrop(onFiles: (f: File[]) => void) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const props = {
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setOver(true); },
    onDragLeave: () => setOver(false),
    onDrop: (e: React.DragEvent) => { e.preventDefault(); setOver(false); onFiles(Array.from(e.dataTransfer.files)); },
  };
  const picker = (
    <input ref={input} type="file" accept=".txt,text/plain" multiple hidden
      onChange={(e) => { onFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
  );
  return { over, props, picker, pick: () => input.current?.click() };
}

export function DocsMenu({ docs, asOf, onFiles, onRemove, onClear }: {
  docs: DocSummary[]; asOf: string; onFiles: (f: File[]) => void; onRemove: (d: DocSummary) => void; onClear: () => void;
}) {
  const drop = useFileDrop(onFiles);
  return (
    <div className="pop docs" role="dialog" aria-label="Загруженные документы">
      <h4>Документы · {docs.length}</h4>
      {docs.map((d) => {
        const [s, label] = docStatus(d, asOf);
        return (
          <div className="doc" key={d.id}>
            <span className="t">{d.label}</span>
            <span className={`st ${s}`} style={{ fontWeight: 400 }}>{label}</span>
            <button className="x" aria-label={`Убрать ${d.filename}`} title="Убрать из сверки" onClick={() => onRemove(d)}>×</button>
            <span className="f">{d.filename}{d.issues.length > 0 && !d.issues[0].startsWith("Допсоглашение") ? ` · ${d.issues[0]}` : ""}</span>
          </div>
        );
      })}
      <button className={`drop ${drop.over ? "over" : ""}`} {...drop.props} onClick={drop.pick}>
        Перетащите TXT сюда или нажмите, чтобы выбрать
      </button>
      {drop.picker}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="linkbtn" style={{ color: "var(--signal)" }} onClick={onClear}>Убрать все документы</button>
      </div>
    </div>
  );
}

// Шаблоны вопросов из ТЗ. Ответ не вшит: текст уходит на /api/ask и разбирается правилами.
export const PRESET_QUESTIONS = [
  "Какой срок поставки действует по договору STN-101 на 10 марта 2026 года?",
  "Какова сумма договора STN-102?",
  "Какова сумма договора STN-103?",
  "По каким договорам поставка запланирована раньше 1 апреля 2026 года и есть ли несогласованные изменения срока?",
];

export function AskBar({ asOf, onOpen }: { asOf: string; onOpen: (f: Focus) => void }) {
  const [q, setQ] = useState("");
  const [ans, setAns] = useState<Answer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // счётчик ответов: новый key перезапускает подсветку, даже если ответ тот же
  const [tick, setTick] = useState(0);
  // подсказки под полем: вопросы из задания, фильтруются по введённому тексту
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(-1);
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const suggestions = PRESET_QUESTIONS.filter((p) => words.every((w) => p.toLowerCase().includes(w)) && p !== q);

  const run = async (text: string) => {
    if (!text.trim()) { setErr("Введите вопрос или выберите подсказку под полем"); setOpen(true); return; }
    setQ(text); setErr(null); setBusy(true); setOpen(false); setHi(-1);
    try { setAns(await api.ask(text, asOf)); setTick((t) => t + 1); } catch (e) { setAns(null); setErr((e as Error).message); } finally { setBusy(false); }
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" && suggestions.length) { e.preventDefault(); setOpen(true); setHi((h) => (h + 1) % suggestions.length); }
    else if (e.key === "ArrowUp" && suggestions.length) { e.preventDefault(); setHi((h) => (h <= 0 ? suggestions.length - 1 : h - 1)); }
    else if (e.key === "Escape") { setOpen(false); setHi(-1); }
    else if (e.key === "Enter" && open && hi >= 0) { e.preventDefault(); run(suggestions[hi]); }
  };
  const cite = (contract: string, field: string, ev: Evidence, pending = false) => (
    <div className={`cite ${pending ? "pending" : ""}`} key={`${ev.doc_id}-${ev.paragraph}`}>
      {pending && <span className="st pending"><i aria-hidden="true" />не согласовано</span>}
      <q>{ev.quote}</q>
      <button className="linkbtn" onClick={() => onOpen({ contract, field, evidence: ev })}>{ev.filename} · абз. {ev.paragraph}</button>
    </div>
  );

  return (
    <>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); run(q); }}>
        <label htmlFor="ask" className="ask-label">
          Спросите по загруженным договорам
          <span>ответ строится по документам и приходит с цитатой-основанием</span>
        </label>
        <div className="ask-row">
          <div className="combo">
            <input id="ask" className="ask-input" value={q} autoComplete="off"
              role="combobox" aria-expanded={open && suggestions.length > 0} aria-controls="ask-list"
              aria-activedescendant={hi >= 0 ? `ask-opt-${hi}` : undefined}
              onChange={(e) => { setQ(e.target.value); setErr(null); setOpen(true); setHi(-1); }}
              onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)} onKeyDown={onKey}
              placeholder="Например: какова сумма договора STN-102? · срок поставки STN-101 на 1 марта 2026" />
            {open && suggestions.length > 0 && (
              <ul id="ask-list" className="combo-list" role="listbox" aria-label="Вопросы из задания">
                <li className="combo-head" aria-hidden="true">Вопросы из задания</li>
                {suggestions.map((s, i) => (
                  <li key={s} id={`ask-opt-${i}`} role="option" aria-selected={hi === i} className={hi === i ? "on" : ""}
                    onMouseDown={(e) => { e.preventDefault(); run(s); }} onMouseEnter={() => setHi(i)}>{s}</li>
                ))}
              </ul>
            )}
          </div>
          <button className="btn primary ask-btn" disabled={busy} title="Или нажмите Enter в поле">{busy ? "Считаю…" : <>Ответить <span aria-hidden="true">↵</span></>}</button>
        </div>
      </form>
      {err && <div className="answer"><span className="err" role="alert">{err}</span></div>}
      {ans && (
        <div className="answer flash" key={tick} aria-live="polite">
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span className="a">{ans.text}</span>
            <button className="linkbtn" onClick={() => setAns(null)}>Скрыть</button>
          </div>
          {ans.kind === "field" && ans.field && ans.contract && <>
            {ans.field.evidence.map((e) => cite(ans.contract!, ans.field!.field, e))}
            {ans.pending.map((p) => cite(ans.contract!, p.field, p.evidence, true))}
          </>}
          {ans.kind === "delivery_before" && ans.matches.map((m) => (
            <Fragment key={m.contract}>
              {m.evidence.map((e) => cite(m.contract, "delivery", e))}
              {m.pending.map((p) => cite(m.contract, "delivery", p.evidence, true))}
            </Fragment>
          ))}
          <span className="q">На {fmtDate(ans.as_of)} · {ans.question}</span>
        </div>
      )}
    </>
  );
}
