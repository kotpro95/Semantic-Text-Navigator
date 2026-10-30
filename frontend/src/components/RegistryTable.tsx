import type { ContractView, Evidence, FieldView, Registry } from "../api";
import { Badge, SourceRef, shortDoc } from "./common";

export type Focus = { contract: string; field: string; evidence: Evidence | null };

function ValueCell({ c, f, focus, onOpen }: {
  c: ContractView; f: FieldView; focus: Focus | null; onOpen: (x: Focus) => void;
}) {
  const ev = f.evidence[0] ?? null;
  const active = focus?.contract === c.number && focus.field === f.field;
  const open = () => onOpen({ contract: c.number, field: f.field, evidence: ev });
  const label = `${f.label} по ${c.number}: ${f.display ?? "нет данных"}. Открыть источник`;
  return (
    <button className={`val ${active ? "active" : ""}`} onClick={open} aria-label={label}>
      {f.status === "missing" ? (
        <>
          <span className="nodata">нет данных</span>
          {f.note && <span className="why">{f.note}</span>}
        </>
      ) : (
        <span className="v">{f.display}</span>
      )}
      {f.status === "changed" && f.changed_by && <Badge tone="sage">изм. {shortDoc(f.changed_by)}</Badge>}
      {f.status === "review" && <Badge tone="red">проверить</Badge>}
      {f.status === "review" && f.note && <span className="why">{f.note}</span>}
      {ev && <span className="src">§ {ev.filename.replace(/\.txt$/i, "")} · ¶{ev.paragraph}</span>}
    </button>
  );
}

function Notes({ c, onOpen }: { c: ContractView; onOpen: (x: Focus) => void }) {
  const byDoc = new Map<string, typeof c.pending>();
  c.pending.forEach((p) => byDoc.set(p.doc_id, [...(byDoc.get(p.doc_id) ?? []), p]));
  const missingFlags = c.flags.filter((f) => f.level === "review");
  if (!byDoc.size && !missingFlags.length) return <span className="muted mono" style={{ fontSize: 11 }}>—</span>;
  return (
    <div>
      {[...byDoc.values()].map((ps) => (
        <div className="note" key={ps[0].doc_id}>
          <Badge tone="ochre">{shortDoc(ps[0].doc_label)} · не согласовано</Badge>
          <p>
            {ps.map((p) => `${p.label.split(",")[0].toLowerCase()}: ${p.current_display ?? "—"} → ${p.proposed_display}`).join("; ")}.{" "}
            <span className="muted">{ps[0].reason[0].toUpperCase() + ps[0].reason.slice(1)}.</span>
          </p>
          {ps.map((p) => (
            <SourceRef key={p.field} ev={p.evidence} onOpen={(ev) => onOpen({ contract: c.number, field: p.field, evidence: ev })} />
          ))}
        </div>
      ))}
      {missingFlags.length > 0 && (
        <div className="note">
          <Badge tone="red">Требует проверки</Badge>
          {missingFlags.map((f) => <p key={f.text}>{f.text}</p>)}
        </div>
      )}
    </div>
  );
}

export function RegistryTable({ reg, focus, onOpen }: { reg: Registry; focus: Focus | null; onOpen: (x: Focus) => void }) {
  const cols = reg.fields.filter((f) => f.in_registry && f.name !== "supplier");
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 100 }}>Договор</th>
            <th style={{ width: 160 }}>Поставщик</th>
            {cols.map((c) => <th key={c.name} style={{ width: 170 }}>{c.label}</th>)}
            <th>Не согласовано · проверить</th>
          </tr>
        </thead>
        <tbody>
          {reg.contracts.map((c) => (
            <tr key={c.number}>
              <td className="num">{c.number}</td>
              <td><ValueCell c={c} f={c.fields.supplier} focus={focus} onOpen={onOpen} /></td>
              {cols.map((col) => (
                <td key={col.name}><ValueCell c={c} f={c.fields[col.name]} focus={focus} onOpen={onOpen} /></td>
              ))}
              <td><Notes c={c} onOpen={onOpen} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
