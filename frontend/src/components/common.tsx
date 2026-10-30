import type { DocSummary, Evidence } from "../api";
import { fmtDate } from "../api";

export type Tone = "neutral" | "sage" | "ochre" | "red";

export function Badge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

/** Ссылка на источник: «§ файл · ¶N». Клик открывает абзац. */
export function SourceRef({ ev, onOpen }: { ev: Evidence; onOpen: (ev: Evidence) => void }) {
  return (
    <button className="src" onClick={(e) => { e.stopPropagation(); onOpen(ev); }} title={ev.quote}>
      § {ev.filename.replace(/\.txt$/i, "")} · ¶{ev.paragraph}
    </button>
  );
}

export function docBadge(d: DocSummary, asOf: string): [Tone, string] {
  switch (d.kind) {
    case "contract":
      return d.signed ? ["sage", "Договор · подписан"] : ["red", "Договор · не подписан"];
    case "amendment":
      if (!d.signed) return ["ochre", "ДС · не подписано обеими"];
      if (!d.effective_date) return ["red", "ДС · нет даты вступления"];
      return d.effective_date <= asOf
        ? ["sage", `ДС · в силе с ${fmtDate(d.effective_date)}`]
        : ["ochre", `ДС · вступает ${fmtDate(d.effective_date)}`];
    case "amendment_draft":
      return ["ochre", "Проект · не подписан"];
    case "letter":
      return ["ochre", "Письмо · предложение"];
    default:
      return ["red", "Тип не распознан"];
  }
}

export const shortDoc = (label: string) => label.replace(/ (к|по) [A-ZА-ЯЁ]{2,6}-\d+$/, "");
