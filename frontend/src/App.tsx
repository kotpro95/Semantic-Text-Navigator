import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DocSummary, Registry } from "./api";
import { api, fmtDate } from "./api";
import { Confirm, Hint, TERMS, useStored, type ConfirmState } from "./components/common";
import { ColumnsMenu, DEFAULT_HIDDEN, DEFAULT_ORDER, DataTable, toRows, type Focus } from "./components/DataTable";
import { AskBar, DocsMenu, useFileDrop } from "./components/Panels";
import { SourceDrawer } from "./components/SourceDrawer";

type View = "all" | "review" | "pending";
type Filter = { view: View; before: string | null; q: string };
type Saved = Filter & { name: string };

function Empty({ onFiles, onSamples, busy }: { onFiles: (f: File[]) => void; onSamples: () => void; busy: boolean }) {
  const drop = useFileDrop(onFiles);
  return (
    <main className="empty">
      <div className="blk">
        <h2>Загрузите договоры и связанные документы</h2>
        <p>Договоры, допсоглашения, письма поставщиков, проекты изменений — TXT, сразу несколько. Тип и статус каждого документа определяются по тексту.</p>
        <div className={`drop ${drop.over ? "over" : ""}`} {...drop.props}>
          <span>Перетащите TXT-файлы сюда</span>
          <div className="row">
            <button className="btn primary" onClick={drop.pick} disabled={busy}>Выбрать файлы</button>
            <button className="btn" onClick={onSamples} disabled={busy}>Загрузить примеры (6)</button>
          </div>
        </div>
        {drop.picker}
      </div>
    </main>
  );
}

export default function App() {
  const [asOf, setAsOf] = useState("2026-03-10");
  const [reg, setReg] = useState<Registry | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState<Focus | null>(null);
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const [menu, setMenu] = useState<"docs" | "cols" | null>(null);
  const [density, setDensity] = useStored<"compact" | "comfortable">("tbl.density", "compact");
  const [order, setOrder] = useStored<string[]>("tbl.order", DEFAULT_ORDER);
  const [hidden, setHidden] = useStored<string[]>("tbl.hidden", DEFAULT_HIDDEN);
  const [tableKey, setTableKey] = useState(0);
  const [filter, setFilter] = useState<Filter>({ view: "all", before: null, q: "" });
  const [saved, setSaved] = useStored<Saved[]>("tbl.saved", []);
  const menuRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    api.registry(asOf).then((r) => { setReg(r); setErr(null); }).catch((e) => setErr(e.message));
  }, [asOf]);
  useEffect(load, [load]);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (menu && !(e.target as HTMLElement).closest(".pop-anchor")) setMenu(null); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [menu]);

  const act = async (p: Promise<unknown>) => {
    setBusy(true);
    try { await p; setErr(null); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); load(); }
  };
  const onFiles = (files: File[]) => { if (files.length) act(api.upload(files)); };
  const topDrop = useFileDrop(onFiles);
  const removeDoc = (d: DocSummary) => { setMenu(null); setConfirm({
    title: `Убрать «${d.label}»?`, text: `Файл ${d.filename} будет исключён из сверки, реестр пересчитается. Исходный файл на диске не меняется.`,
    action: "Убрать", run: () => act(api.remove(d.id)),
  }); };
  const clearAll = () => { setMenu(null); setConfirm({
    title: "Убрать все документы?", text: "Реестр станет пустым, документы придётся загрузить заново.",
    action: "Убрать все", run: () => { setFocus(null); act(api.clear()); },
  }); };

  const registryFields = useMemo(() => (reg?.fields ?? []).filter((f) => f.in_registry).map((f) => f.name), [reg]);
  const allRows = useMemo(() => toRows(reg?.contracts ?? [], registryFields), [reg, registryFields]);
  const rows = allRows.filter((r) => {
    if (filter.view !== "all" && r.status !== filter.view) return false;
    if (filter.before) {
      const d = r.c.fields.delivery.value;
      if (!d || d >= filter.before) return false;
    }
    const q = filter.q.trim().toLowerCase();
    return !q || `${r.c.number} ${r.c.fields.supplier.display ?? ""}`.toLowerCase().includes(q);
  });
  const count = (v: View) => (v === "all" ? allRows.length : allRows.filter((r) => r.status === v).length);
  const filterName = (f: Filter) => [
    { all: "Все", review: "Проверить", pending: "Есть предложение" }[f.view],
    f.before ? `поставка до ${fmtDate(f.before)}` : "", f.q ? `«${f.q}»` : "",
  ].filter(Boolean).join(" · ");
  const isDefault = filter.view === "all" && !filter.before && !filter.q;

  const docs = reg?.documents ?? [];
  const contracts = reg?.contracts ?? [];

  return (
    <div className={density}>
      <header className="top">
        <h1>Сверка договоров поставки</h1>
        <label className="field">Дата проверки
          <input className="input mono" type="date" value={asOf} onChange={(e) => e.target.value && setAsOf(e.target.value)} />
          <Hint text={TERMS.asOf} />
        </label>
        <span className="grow" />
        {docs.length > 0 && (
          <div className="pop-anchor" ref={menuRef}>
            <button className="btn" aria-expanded={menu === "docs"} onClick={() => setMenu(menu === "docs" ? null : "docs")}>
              Документы <span className="mono muted">{docs.length}</span> ▾
            </button>
            {menu === "docs" && <DocsMenu docs={docs} asOf={asOf} onFiles={onFiles} onRemove={removeDoc} onClear={clearAll} />}
          </div>
        )}
        {/* на стартовом экране загрузка уже в центре — в шапке не дублируем */}
        {docs.length > 0 && <button className="btn primary" onClick={topDrop.pick} disabled={busy}>{busy ? "Загрузка…" : "Загрузить TXT"}</button>}
        {topDrop.picker}
      </header>
      {err && <div className="answer"><span className="err" role="alert">{err}</span></div>}

      {reg && docs.length === 0 && <Empty onFiles={onFiles} onSamples={() => act(api.samples())} busy={busy} />}

      {reg && docs.length > 0 && (
        <main>
          <div className="toolbar" role="toolbar" aria-label="Фильтры и вид таблицы">
            <div className="seg" role="group" aria-label="Статус">
              {(["all", "review", "pending"] as View[]).map((v) => (
                <button key={v} aria-pressed={filter.view === v} onClick={() => setFilter({ ...filter, view: v })}>
                  {{ all: "Все", review: "Проверить", pending: "Есть предложение" }[v]} <span className="n">{count(v)}</span>
                </button>
              ))}
            </div>
            <label className="field">
              <input type="checkbox" checked={!!filter.before} onChange={(e) => setFilter({ ...filter, before: e.target.checked ? filter.before ?? "2026-04-01" : null })} />
              Поставка до
            </label>
            <input className="input mono" type="date" aria-label="Поставка до даты" value={filter.before ?? "2026-04-01"} disabled={!filter.before}
              onChange={(e) => setFilter({ ...filter, before: e.target.value || null })} />
            <input className="input" style={{ width: 200 }} placeholder="Номер или поставщик" aria-label="Поиск" value={filter.q}
              onChange={(e) => setFilter({ ...filter, q: e.target.value })} />
            {!isDefault && <>
              <button className="btn" onClick={() => setSaved([...saved.filter((s) => s.name !== filterName(filter)), { ...filter, name: filterName(filter) }])}>Сохранить фильтр</button>
              <button className="linkbtn" onClick={() => setFilter({ view: "all", before: null, q: "" })}>Сбросить</button>
            </>}
            {saved.length > 0 && <span className="sep" />}
            {saved.map((s) => (
              <span key={s.name} className="seg">
                <button aria-pressed={filterName(filter) === s.name} onClick={() => setFilter({ view: s.view, before: s.before, q: s.q })}>{s.name}</button>
                <button aria-label={`Удалить фильтр ${s.name}`} onClick={() => setSaved(saved.filter((x) => x.name !== s.name))}>×</button>
              </span>
            ))}
            <span style={{ flex: 1 }} />
            <div className="pop-anchor">
              <button className="btn" aria-expanded={menu === "cols"} onClick={() => setMenu(menu === "cols" ? null : "cols")}>Колонки ▾</button>
              {menu === "cols" && (
                <ColumnsMenu order={order} setOrder={setOrder} hidden={hidden} setHidden={setHidden}
                  onReset={() => { setOrder(DEFAULT_ORDER); setHidden(DEFAULT_HIDDEN); try { localStorage.removeItem("tbl.widths"); } catch { /* */ } setTableKey((k) => k + 1); }} />
              )}
            </div>
            <div className="seg" role="group" aria-label="Плотность">
              <button aria-pressed={density === "compact"} onClick={() => setDensity("compact")}>Компактно</button>
              <button aria-pressed={density === "comfortable"} onClick={() => setDensity("comfortable")}>Стандартно</button>
            </div>
          </div>

          <AskBar key={asOf} asOf={asOf} onOpen={setFocus} />

          {contracts.length > 0
            ? <DataTable key={tableKey} rows={rows} order={order} hidden={hidden} focus={focus} onOpen={setFocus} />
            : <div className="empty-row">Среди загруженных документов нет договоров.</div>}
          {reg.flags.length > 0 && <div className="answer"><span className="err">{reg.flags.map((f) => f.text).join(" · ")}</span></div>}

          <footer className="foot">
            <span>{rows.length} из {allRows.length} договоров · на {fmtDate(asOf)}</span>
            <span><kbd>↑</kbd><kbd>↓</kbd><kbd>←</kbd><kbd>→</kbd> ячейка · <kbd>Enter</kbd> основание · <kbd>Esc</kbd> закрыть</span>
            <span style={{ marginLeft: "auto" }}>Извлечение: правила{reg.llm.enabled ? ` + LLM ${reg.llm.model}` : " · LLM выключена"}</span>
          </footer>
        </main>
      )}

      {focus && (
        <SourceDrawer focus={focus} asOf={asOf} contract={contracts.find((c) => c.number === focus.contract)}
          onClose={() => setFocus(null)} onFocus={setFocus} />
      )}
      <Confirm state={confirm} onClose={() => setConfirm(null)} />
    </div>
  );
}
