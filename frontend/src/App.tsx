import { useCallback, useEffect, useState } from "react";
import type { Registry } from "./api";
import { api, fmtDate } from "./api";
import { Badge } from "./components/common";
import { Questions } from "./components/Questions";
import { RegistryTable, type Focus } from "./components/RegistryTable";
import { Sidebar, useFileDrop } from "./components/Sidebar";
import { SourceDrawer } from "./components/SourceDrawer";

const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const longDate = (iso: string) => { const [y, m, d] = iso.split("-").map(Number); return `${d} ${MONTHS[m - 1]} ${y}`; };

function Empty({ onFiles, onSamples, busy }: { onFiles: (f: File[]) => void; onSamples: () => void; busy: boolean }) {
  const drop = useFileDrop(onFiles);
  return (
    <main className="empty">
      <div className="blk">
        <span className="kicker">Начало работы</span>
        <h2>Загрузите договоры и всё, что к ним относится</h2>
        <p>Договоры, допсоглашения, письма поставщиков и проекты изменений — TXT, сразу несколько файлов. Тип и статус каждого документа определяются по тексту, а не по имени файла.</p>
        <div className={`drop ${drop.over ? "over" : ""}`} {...drop.props}>
          <strong>Перетащите TXT-файлы сюда</strong>
          <div className="row">
            <button className="btn primary" onClick={drop.pick} disabled={busy}>Выбрать файлы</button>
            <button className="btn" onClick={onSamples} disabled={busy}>Загрузить примеры · 6 файлов</button>
          </div>
        </div>
        {drop.picker}
        <span className="rule-note">Правило сверки: условие меняет только допсоглашение, подписанное обеими сторонами и вступившее в силу к дате проверки. Всё остальное — сведения для проверки.</span>
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

  const load = useCallback(() => {
    api.registry(asOf).then((r) => { setReg(r); setErr(null); }).catch((e) => setErr(e.message));
  }, [asOf]);
  useEffect(load, [load]);

  const act = async (p: Promise<unknown>) => {
    setBusy(true);
    try { await p; setErr(null); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); load(); }
  };
  const onFiles = (files: File[]) => files.length && act(api.upload(files));
  const headerDrop = useFileDrop(onFiles);

  const contracts = reg?.contracts ?? [];
  const changed = contracts.filter((c) => Object.values(c.fields).some((f) => f.status === "changed")).length;
  const pendingDocs = new Set(contracts.flatMap((c) => c.pending.map((p) => p.doc_id))).size;
  const missing = contracts.reduce((n, c) => n + reg!.fields.filter((f) => f.in_registry && c.fields[f.name].status === "missing").length, 0);
  const review = contracts.reduce((n, c) => n + Object.values(c.fields).filter((f) => f.status === "review").length, 0);

  return (
    <>
      <header className="header">
        <div className="brand">
          <span className="kicker">Semantic TextNavigator · прототип</span>
          <h1>Сверка договоров поставки</h1>
        </div>
        <div className="header-right">
          <label className="asof">Дата проверки
            <input type="date" value={asOf} onChange={(e) => e.target.value && setAsOf(e.target.value)} />
          </label>
          <span title={reg?.llm.enabled ? `Ollama: ${reg.llm.model}` : "Извлечение правилами; LLM-сверка выключена"}>
            <Badge tone="neutral">{reg?.llm.enabled ? `Правила + LLM ${reg.llm.model}` : "Правила · LLM выкл."}</Badge>
          </span>
          <button className="btn primary" onClick={headerDrop.pick} disabled={busy}>{busy ? "Загрузка…" : "Загрузить TXT"}</button>
          {headerDrop.picker}
        </div>
      </header>
      {err && <p className="err" style={{ padding: "8px 40px", margin: 0 }} role="alert">{err}</p>}

      {reg && reg.documents.length === 0 && <Empty onFiles={onFiles} onSamples={() => act(api.samples())} busy={busy} />}

      {reg && reg.documents.length > 0 && (
        <div className="body">
          <Sidebar docs={reg.documents} asOf={asOf} onFiles={onFiles}
            onRemove={(id) => act(api.remove(id))} onClear={() => { setFocus(null); act(api.clear()); }} />
          <main className="main">
            <div>
              <span className="kicker">Действующие условия</span>
              <h2 className="h1">Реестр на {longDate(asOf)}</h2>
              <div className="summary">
                <span>{contracts.length} {contracts.length === 1 ? "договор" : contracts.length < 5 ? "договора" : "договоров"}</span>
                {changed > 0 && <span style={{ color: "var(--sage)" }}>{changed} изменено подписанным ДС</span>}
                {pendingDocs > 0 && <span style={{ color: "var(--ochre)" }}>{pendingDocs} предложений не согласовано</span>}
                {missing > 0 && <span style={{ color: "var(--red)" }}>{missing} — нет данных</span>}
                {review > 0 && <span style={{ color: "var(--red)" }}>{review} требует проверки</span>}
              </div>
              <p className="lead">Условия меняет только допсоглашение, подписанное обеими сторонами и вступившее в силу к дате проверки. Письма и проекты показаны отдельно — как сведения для проверки.</p>
            </div>
            {reg.flags.length > 0 && (
              <div className="note">
                <Badge tone="red">Не связано с договорами</Badge>
                {reg.flags.map((f) => <p key={f.text}>{f.text}</p>)}
              </div>
            )}
            {contracts.length > 0
              ? <RegistryTable reg={reg} focus={focus} onOpen={setFocus} />
              : <p className="muted">Среди загруженных документов нет договоров.</p>}
            <span className="hint">Нажмите на значение или §, чтобы открыть абзац-источник · дата проверки {fmtDate(asOf)}</span>
            <Questions key={asOf} asOf={asOf} onOpen={setFocus} />
          </main>
        </div>
      )}

      {focus && (
        <SourceDrawer focus={focus} asOf={asOf} contract={contracts.find((c) => c.number === focus.contract)}
          onClose={() => setFocus(null)} onFocus={setFocus} />
      )}
    </>
  );
}
