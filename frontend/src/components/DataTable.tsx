import { useEffect, useMemo, useRef, useState } from "react";
import type { ContractView, Evidence, FieldView } from "../api";
import { fmtDate } from "../api";
import { Hint, STATUS, StatusLabel, TERMS, contractStatus, shortDoc, useStored, type Status } from "./common";

export type Focus = { contract: string; field: string; evidence: Evidence | null };

export type Row = {
  c: ContractView;
  status: Status;
  pendingText: string;
  reviewText: string;
};

type Col = {
  id: string;
  label: string;
  hint?: string;
  width: number;
  align?: "r";
  field?: string; // клик по ячейке открывает основание этого поля
  sort: (r: Row) => string | number;
  render: (r: Row) => React.ReactNode;
  text: (r: Row) => string; // для title / экспорта
};

// метка LLM-сверки у значения: подтверждено / расходится / найдено моделью / ещё проверяется
const LLM_TAG: Record<string, [string, string] | undefined> = {
  agree: ["llm", "LLM ✓"], disagree: ["pending", "LLM ≠"], filled: ["pending", "LLM"], pending: ["llm", "LLM…"],
};
function llmTag(f: FieldView) {
  const t = f.llm && LLM_TAG[f.llm.verdict];
  return t ? <span className={`tag ${t[0]}`} title={f.llm!.note}>{t[1]}</span> : null;
}

function fieldCell(f: FieldView | undefined) {
  if (!f || f.status === "missing") return <><span className="nd">нет данных</span>{f && llmTag(f)}</>;
  return (
    <>
      {f.display}
      {f.status === "changed" && f.changed_by && <span className="tag ok" title={`Изменено: ${f.changed_by}`}>{shortDoc(f.changed_by).replace("ДС № ", "ДС")}</span>}
      {f.status === "review" && !f.llm && <span className="tag pending" title={f.note ?? ""}>?</span>}
      {llmTag(f)}
    </>
  );
}
// «STN-101» → мелкий серый префикс + крупный номер, как в варианте A
const numCell = (n: string) => { const i = n.lastIndexOf("-"); return <span className="cnum"><span>{n.slice(0, i + 1)}</span><b>{n.slice(i + 1)}</b></span>; };
const fieldText = (f: FieldView | undefined) => (!f || f.status === "missing" ? "нет данных" : f.display ?? "");

export const COLUMNS: Col[] = [
  { id: "number", label: "Договор", width: 104, sort: (r) => r.c.number, render: (r) => numCell(r.c.number), text: (r) => r.c.number },
  { id: "supplier", label: "Поставщик", width: 200, field: "supplier", sort: (r) => r.c.fields.supplier.display ?? "", render: (r) => fieldCell(r.c.fields.supplier), text: (r) => fieldText(r.c.fields.supplier) },
  { id: "amount", label: "Сумма, ₽ с НДС", hint: TERMS.amount, width: 185, align: "r", field: "amount", sort: (r) => Number(r.c.fields.amount.value ?? -1), render: (r) => fieldCell(r.c.fields.amount), text: (r) => fieldText(r.c.fields.amount) },
  { id: "delivery", label: "Срок поставки", hint: TERMS.delivery, width: 175, align: "r", field: "delivery", sort: (r) => r.c.fields.delivery.value ?? "9999", render: (r) => fieldCell(r.c.fields.delivery), text: (r) => fieldText(r.c.fields.delivery) },
  { id: "status", label: "Статус", width: 150, sort: (r) => ["review", "pending", "ok"].indexOf(r.status), render: (r) => <StatusLabel s={r.status} />, text: (r) => STATUS[r.status].label },
  { id: "pending", label: "Не согласовано", hint: TERMS.pending, width: 260, sort: (r) => r.pendingText, render: (r) => r.pendingText ? <span style={{ color: "var(--pending)" }}>{r.pendingText}</span> : <span className="muted">—</span>, text: (r) => r.pendingText },
  { id: "review", label: "Проверить", hint: TERMS.review, width: 240, sort: (r) => r.reviewText, render: (r) => r.reviewText ? <span style={{ color: "var(--signal)" }}>{r.reviewText}</span> : <span className="muted">—</span>, text: (r) => r.reviewText },
  { id: "penalty", label: "Неустойка", hint: TERMS.penalty, width: 190, field: "penalty", sort: (r) => r.c.fields.penalty?.display ?? "", render: (r) => fieldCell(r.c.fields.penalty), text: (r) => fieldText(r.c.fields.penalty) },
  { id: "docs", label: "Документов", width: 100, align: "r", sort: (r) => r.c.related_docs.length + 1, render: (r) => r.c.related_docs.length + 1, text: (r) => String(r.c.related_docs.length + 1) },
];
export const DEFAULT_ORDER = COLUMNS.map((c) => c.id);
export const DEFAULT_HIDDEN = ["penalty", "docs"];

export function toRows(contracts: ContractView[], registryFields: string[]): Row[] {
  return contracts.map((c) => {
    // одна строка на документ-источник: «Проект ДС № 2 → 1 450 000 / 10.05.2026»
    const byDoc = new Map<string, string[]>();
    c.pending.forEach((p) => byDoc.set(shortDoc(p.doc_label), [...(byDoc.get(shortDoc(p.doc_label)) ?? []), p.proposed_display]));
    const pend = [...byDoc].map(([doc, vals]) => `${doc} → ${vals.join(" / ")}`);
    const missing = Object.values(c.fields).filter((f) => registryFields.includes(f.field) && f.status === "missing").map((f) => `${f.label.split(",")[0]}: ${f.note ?? "нет данных"}`);
    const review = Object.values(c.fields).filter((f) => f.status === "review").map((f) => f.note ?? f.label);
    const other = c.flags.filter((f) => f.level === "review" && !f.text.includes("нет данных")).map((f) => f.text);
    const rv = [...missing, ...review, ...other];
    return {
      c, status: contractStatus(c, registryFields),
      pendingText: pend.length ? pend[0] + (pend.length > 1 ? `; +${pend.length - 1}` : "") : "",
      reviewText: rv.length ? rv[0] + (rv.length > 1 ? `; +${rv.length - 1}` : "") : "",
    };
  });
}

export function DataTable({ rows, order, hidden, focus, onOpen }: {
  rows: Row[]; order: string[]; hidden: string[]; focus: Focus | null; onOpen: (f: Focus) => void;
}) {
  const [widths, setWidths] = useStored<Record<string, number>>("tbl.widths", {});
  const [sort, setSort] = useState<{ id: string; dir: 1 | -1 } | null>(null);
  const [sel, setSelState] = useState<{ r: number; c: number }>({ r: 0, c: 0 });
  // ref — чтобы Enter сразу после стрелок видел актуальную ячейку, а не значение из прошлого рендера
  const selRef = useRef(sel);
  const setSel = (u: { r: number; c: number } | ((s: { r: number; c: number }) => { r: number; c: number })) => {
    selRef.current = typeof u === "function" ? u(selRef.current) : u;
    setSelState(selRef.current);
  };
  const wrap = useRef<HTMLDivElement>(null);

  const cols = order.map((id) => COLUMNS.find((c) => c.id === id)!).filter((c) => c && !hidden.includes(c.id));
  // «Договор» всегда первым и закреплён
  const visible = [COLUMNS[0], ...cols.filter((c) => c.id !== "number")];
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = COLUMNS.find((c) => c.id === sort.id)!;
    return [...rows].sort((a, b) => (col.sort(a) > col.sort(b) ? 1 : col.sort(a) < col.sort(b) ? -1 : 0) * sort.dir);
  }, [rows, sort]);

  useEffect(() => { setSel((s) => ({ r: Math.min(s.r, Math.max(0, sorted.length - 1)), c: s.c })); }, [sorted.length]);

  const open = (row: Row, col: Col | undefined) => {
    const field = col?.field ?? (row.status === "review"
      ? Object.values(row.c.fields).find((f) => f.status !== "ok" && f.status !== "changed")?.field ?? "delivery"
      : row.c.pending[0]?.field ?? "delivery");
    const f = row.c.fields[field];
    const pend = !col?.field && row.status === "pending" ? row.c.pending.find((p) => p.field === field)?.evidence : undefined;
    onOpen({ contract: row.c.number, field, evidence: pend ?? f?.evidence[0] ?? null });
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!sorted.length) return;
    const k = e.key;
    if (k === "ArrowDown" || k === "ArrowUp") {
      e.preventDefault();
      setSel((s) => ({ ...s, r: Math.max(0, Math.min(sorted.length - 1, s.r + (k === "ArrowDown" ? 1 : -1))) }));
    } else if (k === "ArrowRight" || k === "ArrowLeft") {
      e.preventDefault();
      setSel((s) => ({ ...s, c: Math.max(0, Math.min(visible.length - 1, s.c + (k === "ArrowRight" ? 1 : -1))) }));
    } else if (k === "Enter") {
      e.preventDefault();
      open(sorted[selRef.current.r], visible[selRef.current.c]);
    }
  };

  const startResize = (id: string, e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    const startX = e.clientX, startW = widths[id] ?? COLUMNS.find((c) => c.id === id)!.width;
    const move = (ev: MouseEvent) => setWidths((w) => ({ ...w, [id]: Math.max(60, startW + ev.clientX - startX) }));
    const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };
  const autoFit = (id: string) => setWidths((w) => { const n = { ...w }; delete n[id]; return n; });

  // Высота строки — как в Excel: тянем нижнюю границу в колонке «Договор».
  // Значение: px, или AUTO — по содержимому (текст переносится). Нет записи — обычная высота.
  const AUTO = -1;
  const [rowH, setRowH] = useStored<Record<string, number>>("tbl.rowh", {});
  const startRowResize = (num: string, e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    const tr = (e.currentTarget as HTMLElement).closest("tr")!;
    const startY = e.clientY, startH = tr.getBoundingClientRect().height;
    const move = (ev: MouseEvent) => setRowH((h) => ({ ...h, [num]: Math.max(28, Math.round(startH + ev.clientY - startY)) }));
    const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
  };
  // двойной клик: обычная → по содержимому → обычная
  const toggleRowFit = (num: string) => setRowH((h) => {
    const n = { ...h };
    if (n[num] === undefined) n[num] = AUTO; else delete n[num];
    return n;
  });

  return (
    <div className="grid-wrap" data-tour="table" ref={wrap} tabIndex={0} onKeyDown={onKey} aria-label="Реестр договоров. Стрелки — перемещение, Enter — открыть основание">
      <table className="grid" role="grid" aria-rowcount={sorted.length}>
        {/* последняя колонка без ширины — забирает остаток экрана, пока её не растянули вручную */}
        <colgroup>{visible.map((c, i) => <col key={c.id} style={{ width: widths[c.id] ?? (i === visible.length - 1 ? undefined : c.width) }} />)}</colgroup>
        <thead>
          <tr>
            {visible.map((c, i) => (
              <th key={c.id} className={`${i === 0 ? "sticky" : ""} ${c.align ?? ""}`} style={{ position: "sticky" }}
                aria-sort={sort?.id === c.id ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                <div className="th">
                  <button className="sort" onClick={() => setSort((s) => (s?.id === c.id ? (s.dir === 1 ? { id: c.id, dir: -1 } : null) : { id: c.id, dir: 1 }))}>
                    {c.label}<span aria-hidden="true">{sort?.id === c.id ? (sort.dir === 1 ? "↑" : "↓") : ""}</span>
                  </button>
                  {c.hint && <Hint text={c.hint} />}
                </div>
                <span className="rz" onMouseDown={(e) => startResize(c.id, e)} onDoubleClick={() => autoFit(c.id)} title="Потяните, чтобы изменить ширину; двойной клик — сброс" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, ri) => (
            <tr key={r.c.number}
              className={`${sel.r === ri || focus?.contract === r.c.number ? "sel" : ""} ${rowH[r.c.number] !== undefined ? "tall" : ""}`}
              style={rowH[r.c.number] > 0 ? { height: rowH[r.c.number] } : undefined}
              onClick={() => setSel((s) => ({ ...s, r: ri }))} onDoubleClick={() => open(r, undefined)}>
              {visible.map((c, ci) => {
                const cls = `${ci === 0 ? "sticky num" : ""} ${c.align ?? ""} ${c.field ? "cell-btn" : ""}`;
                const cursor = sel.r === ri && sel.c === ci ? { boxShadow: "inset 0 0 0 2px var(--ink)" } : undefined;
                return (
                  <td key={c.id} className={cls} style={cursor} title={c.text(r)}>
                    {c.field
                      ? <button onClick={(e) => { e.stopPropagation(); setSel({ r: ri, c: ci }); open(r, c); }}
                          aria-label={`${c.label} ${r.c.number}: ${c.text(r)}. Открыть основание`}>{c.render(r)}</button>
                      : c.render(r)}
                    {ci === 0 && (
                      <span className="rz-row" onMouseDown={(e) => startRowResize(r.c.number, e)}
                        onClick={(e) => e.stopPropagation()}
                        onDoubleClick={(e) => { e.stopPropagation(); toggleRowFit(r.c.number); }}
                        title="Потяните, чтобы изменить высоту строки; двойной клик — по содержимому / обратно" />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {!sorted.length && <div className="empty-row">Нет договоров под выбранный фильтр.</div>}
    </div>
  );
}

export function ColumnsMenu({ order, setOrder, hidden, setHidden, onReset }: {
  order: string[]; setOrder: (o: string[]) => void; hidden: string[]; setHidden: (h: string[]) => void; onReset: () => void;
}) {
  const move = (id: string, d: -1 | 1) => {
    const i = order.indexOf(id), j = i + d;
    if (j < 1 || j >= order.length) return;
    const o = [...order]; [o[i], o[j]] = [o[j], o[i]]; setOrder(o);
  };
  return (
    <div className="pop" role="dialog" aria-label="Настройка колонок">
      <h4>Колонки</h4>
      {order.map((id, i) => {
        const c = COLUMNS.find((x) => x.id === id)!;
        const fixed = id === "number";
        return (
          <label className="row" key={id}>
            <input type="checkbox" checked={!hidden.includes(id)} disabled={fixed}
              onChange={(e) => setHidden(e.target.checked ? hidden.filter((h) => h !== id) : [...hidden, id])} />
            <span className="grow">{c.label}{fixed && <span className="muted"> · закреплена</span>}</span>
            {!fixed && <>
              <button className="ord" aria-label={`${c.label} выше`} disabled={i <= 1} onClick={(e) => { e.preventDefault(); move(id, -1); }}>▲</button>
              <button className="ord" aria-label={`${c.label} ниже`} disabled={i === order.length - 1} onClick={(e) => { e.preventDefault(); move(id, 1); }}>▼</button>
            </>}
          </label>
        );
      })}
      <div className="row"><button className="linkbtn" onClick={onReset}>Сбросить колонки, ширины и высоты строк</button></div>
    </div>
  );
}

export const beforeLabel = (iso: string) => `до ${fmtDate(iso)}`;
