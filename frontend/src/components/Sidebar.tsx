import { useRef, useState } from "react";
import type { DocSummary } from "../api";
import { Badge, docBadge } from "./common";

export function useFileDrop(onFiles: (f: File[]) => void) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const props = {
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setOver(true); },
    onDragLeave: () => setOver(false),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault(); setOver(false);
      onFiles(Array.from(e.dataTransfer.files));
    },
  };
  const picker = (
    <input ref={input} type="file" accept=".txt,text/plain" multiple hidden
      onChange={(e) => { onFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
  );
  return { over, props, picker, pick: () => input.current?.click() };
}

export function Sidebar({ docs, asOf, onFiles, onRemove, onClear }: {
  docs: DocSummary[]; asOf: string; onFiles: (f: File[]) => void; onRemove: (id: string) => void; onClear: () => void;
}) {
  const drop = useFileDrop(onFiles);
  return (
    <aside className="side" aria-label="Загруженные документы">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", paddingBottom: 8 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
          <h2>Документы</h2><span className="mono muted" style={{ fontSize: 11 }}>{docs.length} файлов</span>
        </div>
        <button className="linkbtn" onClick={onClear}>Очистить</button>
      </div>
      {docs.map((d) => {
        const [tone, label] = docBadge(d, asOf);
        return (
          <div className="doc" key={d.id}>
            <span className="file">{d.filename}</span>
            <span className="title">{d.label}</span>
            <span><Badge tone={tone}>{label}</Badge></span>
            {d.issues.filter((i) => !i.startsWith("Допсоглашение не подписано")).map((i) => <span className="issue" key={i}>{i}</span>)}
            <button className="rm" aria-label={`Убрать ${d.filename}`} title="Убрать из сверки" onClick={() => onRemove(d.id)}>×</button>
          </div>
        );
      })}
      <button className={`drop ${drop.over ? "over" : ""}`} {...drop.props} onClick={drop.pick}>
        <strong>Перетащите ещё TXT-файлы</strong>
        <span>или нажмите, чтобы выбрать · договоры, ДС, письма, проекты</span>
      </button>
      {drop.picker}
    </aside>
  );
}
