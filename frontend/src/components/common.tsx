import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ContractView, DocSummary } from "../api";
import { fmtDate } from "../api";

const TIP_W = 280;

/** Подсказка к термину: «?» с пояснением при наведении и фокусе с клавиатуры.
 *  Рендерится порталом в body с position: fixed — иначе её обрезают ячейки
 *  таблицы (overflow: hidden) и прокручиваемый контейнер. */
export function Hint({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number; up: boolean } | null>(null);
  const show = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - TIP_W / 2), window.innerWidth - TIP_W - 8);
    const up = r.bottom + 140 > window.innerHeight; // у нижнего края — показываем над значком
    setPos({ left, top: up ? r.top - 6 : r.bottom + 6, up });
  };
  const hide = () => setPos(null);
  useEffect(() => {
    if (!pos) return;
    window.addEventListener("scroll", hide, true);
    return () => window.removeEventListener("scroll", hide, true);
  }, [pos]);
  return (
    <span ref={ref} className="hint" tabIndex={0} role="note" aria-label={text}
      onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
      onClick={(e) => e.stopPropagation()}>
      ?
      {pos && createPortal(
        <span className="tip" aria-hidden="true"
          style={{ left: pos.left, top: pos.top, width: TIP_W, transform: pos.up ? "translateY(-100%)" : undefined }}>
          {text}
        </span>,
        document.body,
      )}
    </span>
  );
}

export const TERMS = {
  asOf: "Дата, на которую считаются действующие условия. ДС применяется, только если подписано обеими сторонами и вступило в силу не позже этой даты.",
  ds: "ДС — дополнительное соглашение. Меняет условия договора, только если подписано обеими сторонами и вступило в силу к дате проверки.",
  pending: "Проекты ДС, письма поставщиков и ДС с будущей датой вступления. Это сведения для проверки — условия они не меняют.",
  review: "Значения нет в тексте или оно противоречиво. Прототип не подставляет догадки — нужно решение человека.",
  amount: "Общая (итоговая) стоимость договора с НДС. Аванс, бюджетный лимит и части стоимости суммой не считаются.",
  delivery: "Срок «поставить не позднее…». Срок оплаты и дата приёмки сюда не попадают.",
  penalty: "Ставка неустойки за просрочку поставки и её предел — как в тексте договора.",
};

export type Status = "review" | "pending" | "ok";
export const STATUS: Record<Status, { icon: string; label: string }> = {
  review: { icon: "!", label: "Проверить" },
  pending: { icon: "◐", label: "Есть предложение" },
  ok: { icon: "✓", label: "В силе" },
};

export function contractStatus(c: ContractView, registryFields: string[]): Status {
  const bad = Object.values(c.fields).some((f) => f.status === "review" || (f.status === "missing" && registryFields.includes(f.field)));
  if (bad || c.flags.some((f) => f.level === "review")) return "review";
  return c.pending.length ? "pending" : "ok";
}

export function StatusLabel({ s }: { s: Status }) {
  return <span className={`st ${s}`}><i aria-hidden="true" />{STATUS[s].label}</span>;
}

export function docStatus(d: DocSummary, asOf: string): [Status, string] {
  switch (d.kind) {
    case "contract":
      return d.signed ? ["ok", "подписан"] : ["review", "не подписан"];
    case "amendment":
      if (!d.signed) return ["pending", "не подписано обеими"];
      if (!d.effective_date) return ["review", "нет даты вступления"];
      return d.effective_date <= asOf ? ["ok", `в силе с ${fmtDate(d.effective_date)}`] : ["pending", `вступает ${fmtDate(d.effective_date)}`];
    case "amendment_draft":
      return ["pending", "проект, не подписан"];
    case "letter":
      return ["pending", "предложение"];
    default:
      return ["review", "тип не распознан"];
  }
}

export const shortDoc = (label: string) => label.replace(/ (к|по) [A-ZА-ЯЁ]{2,6}-\d+$/, "");

/** useState, который переживает перезагрузку (настройки таблицы, фильтры). */
export function useStored<T>(key: string, initial: T) {
  const [v, setV] = useState<T>(() => {
    try { const s = localStorage.getItem(key); return s ? (JSON.parse(s) as T) : initial; } catch { return initial; }
  });
  useEffect(() => { try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* приватный режим */ } }, [key, v]);
  return [v, setV] as const;
}

export type ConfirmState = { title: string; text: string; action: string; run: () => void } | null;

export function Confirm({ state, onClose }: { state: ConfirmState; onClose: () => void }) {
  useEffect(() => {
    if (!state) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [state, onClose]);
  if (!state) return null;
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="cf-t" onClick={(e) => e.stopPropagation()}>
        <h3 id="cf-t">{state.title}</h3>
        <p>{state.text}</p>
        <div className="acts">
          <button className="btn" onClick={onClose} autoFocus>Отмена</button>
          <button className="btn danger" onClick={() => { state.run(); onClose(); }}>{state.action}</button>
        </div>
      </div>
    </div>
  );
}
