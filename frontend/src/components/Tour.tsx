import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

/** Интерактивный тур по продукту: затемнение, плавная подсветка элемента,
 *  анимированный курсор (наведение и клик) и карточка «что можно сделать».
 *  Запускается сам при первом визите и по кнопке «Как пользоваться». */

export type TourApi = {
  hasDocs: () => boolean;
  loadSamples: () => Promise<void>;
  openDocs: () => void;
  closeAll: () => void; // закрыть меню, панель основания, ответ
};

type Step = {
  scenario: string;
  title: string;
  text: string;
  target: () => Element | null;
  action?: "hover" | "click";
  realClick?: boolean;           // после анимации действительно нажать (показать результат)
  prep?: (api: TourApi) => Promise<void> | void;
};

const q = (s: string) => () => document.querySelector(s);
const cellWith = (sel: string) => () => document.querySelector(sel)?.closest("td") ?? null;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const STEPS: Step[] = [
  { scenario: "Начало", title: "Сверка договоров поставки",
    text: "Прототип собирает реестр действующих условий по пачке документов: сумма и срок поставки на дату проверки. Каждое значение подтверждается точной цитатой из файла. Пройдём основные сценарии — это займёт пару минут.",
    target: q('[data-tour="title"]') },
  { scenario: "1. Загрузка", title: "Загрузите документы",
    text: "Договоры, допсоглашения, письма поставщиков, проекты — TXT, сразу несколько файлов (кнопка или перетаскивание). Тип и статус документа определяются по тексту, а не по имени файла. Для тура мы загрузим учебные примеры.",
    target: q('[data-tour="upload"]'), action: "click",
    prep: async (api) => { api.closeAll(); } },
  { scenario: "1. Загрузка", title: "Что распознано в файлах",
    text: "«Документы ▾» — список файлов и их статус: подписан, ДС в силе, проект не подписан, предложение в письме. Отсюда можно убрать лишний файл (с подтверждением) или догрузить новый.",
    target: q('[data-tour="docs"]'), action: "click", realClick: true,
    prep: async (api) => { if (!api.hasDocs()) { await api.loadSamples(); await sleep(400); } api.closeAll(); } },
  { scenario: "2. Реестр", title: "Дата проверки",
    text: "Условия считаются на эту дату: допсоглашение применяется, только если подписано обеими сторонами и вступило в силу не позже неё. Смените дату — реестр пересчитается сразу.",
    target: q('[data-tour="asof"]'), action: "hover", prep: (api) => api.closeAll() },
  { scenario: "2. Реестр", title: "Реестр действующих условий",
    text: "Одна строка — один договор: поставщик, сумма с НДС, срок поставки, статус. Работает как таблица в Excel: шапка и номер договора закреплены, клик по заголовку — сортировка.",
    target: q('[data-tour="table"]') },
  { scenario: "2. Реестр", title: "Значение изменено допсоглашением",
    text: "Метка «ДС1» значит: исходное условие договора заменено подписанным ДС № 1. Так видно, каким документом изменено значение.",
    target: cellWith(".grid td.cell-btn .tag.ok"), action: "hover" },
  { scenario: "2. Реестр", title: "«Нет данных» вместо догадки",
    text: "Если значения в тексте нет (например, цена в отсутствующем приложении), прототип пишет «нет данных» и ставит статус «■ Проверить». Похожие числа вроде бюджетного лимита не подставляются.",
    target: cellWith(".grid td .nd"), action: "hover" },
  { scenario: "2. Реестр", title: "Статус и несогласованные изменения",
    text: "«□ Есть предложение» — есть проект ДС или письмо с другими условиями; они НЕ меняют реестр и показаны в колонке «Не согласовано». «■ Проверить» — нужен взгляд человека.",
    target: cellWith(".grid td .st"), action: "hover" },
  { scenario: "3. Основание", title: "Откройте основание значения",
    text: "Клик по сумме или сроку (или Enter на выбранной ячейке) открывает, откуда взято значение. Давайте нажмём.",
    target: cellWith(".grid td.cell-btn .tag.ok"), action: "click", realClick: true },
  { scenario: "3. Основание", title: "Точная цитата и файл",
    text: "Цитата дословно из документа, имя файла и номер абзаца. «Копировать» — чтобы отправить юристу или поставщику.",
    target: q(".drawer .quote"), action: "hover" },
  { scenario: "3. Основание", title: "Как получено значение",
    text: "Цепочка документов: исходный договор → подписанное ДС → проект на согласовании. Клик по шагу показывает его абзац в документе ниже.",
    target: q(".drawer .chain"), action: "click" },
  { scenario: "3. Основание", title: "Исходный документ",
    text: "Текст файла с подсвеченным абзацем-основанием; зелёным — статус подписания и дата вступления в силу. Esc или «Закрыть» — вернуться к реестру.",
    target: q(".drawer .viewer"), action: "hover" },
  { scenario: "4. Вопросы", title: "Спросите своими словами",
    text: "Например: «Какова сумма договора STN-102?» или «Срок поставки STN-101 на 1 марта 2026». Под полем — 4 вопроса из задания. Enter — ответ с цитатой; клик по ссылке в ответе открывает основание.",
    target: q('[data-tour="ask"]'), action: "click", prep: (api) => api.closeAll() },
  { scenario: "5. Фильтры", title: "Найдите нужные договоры",
    text: "«Проверить» — где нужен человек, «Есть предложение» — где есть несогласованные изменения, «Поставка до» — срок раньше даты. Поиск по номеру и поставщику, «Сохранить фильтр» — для повторного использования.",
    target: q('[data-tour="filters"]'), action: "hover" },
  { scenario: "6. Настройка", title: "Таблица под себя",
    text: "«Колонки ▾» — скрыть, показать (например, «Неустойка») и переставить колонки. Границы колонок и строк тянутся мышью, двойной клик — сброс/по содержимому. «Компактно / Стандартно» — плотность. Стрелки + Enter — работа с клавиатуры.",
    target: q('[data-tour="view"]'), action: "hover" },
  { scenario: "7. LLM-сверка", title: "Второе мнение локальной модели",
    text: "Включает перепроверку суммы и срока локальной моделью (Ollama). «LLM ✓» — модель согласна, «LLM ≠» — расхождение, «Проверить». Ответ модели принимается только с дословной цитатой. Без Ollama переключатель неактивен — всё работает на правилах.",
    target: q('[data-tour="llm"]'), action: "hover" },
  { scenario: "Готово", title: "Вернуться к туру можно всегда",
    text: "Кнопка «Как пользоваться» запускает этот тур снова. Подсказки «?» рядом с терминами объясняют их по наведению.",
    target: q('[data-tour="help"]'), action: "hover" },
];

type Rect = { x: number; y: number; w: number; h: number };

export function Tour({ open, onClose, api }: { open: boolean; onClose: () => void; api: TourApi }) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number }>({ x: window.innerWidth / 2, y: window.innerHeight - 60 });
  const [phase, setPhase] = useState<"move" | "hover" | "click" | "idle">("idle");
  const [busy, setBusy] = useState(false);
  const elRef = useRef<Element | null>(null);
  const run = useRef(0);

  const steps = STEPS;
  const step = steps[i];

  const measure = useCallback(() => {
    const el = elRef.current;
    if (!el) return setRect(null);
    const r = el.getBoundingClientRect();
    // подсветка ровно по границам элемента, рамка внутри — не налезает на соседей и края экрана
    setRect({ x: r.left, y: r.top, w: r.width, h: r.height });
  }, []);

  useEffect(() => { if (open) setI(0); }, [open]);

  // показать шаг: подготовка → найти элемент → подсветить → курсор → наведение → клик
  useEffect(() => {
    if (!open) return;
    const my = ++run.current;
    const alive = () => run.current === my;
    (async () => {
      setBusy(true); setPhase("idle");
      document.querySelectorAll(".tour-hover").forEach((e) => e.classList.remove("tour-hover"));
      await step.prep?.(api);
      let el: Element | null = null;
      for (let t = 0; t < 30 && !el; t++) { el = step.target(); if (!el) await sleep(100); }
      if (!alive()) return;
      if (!el) { setBusy(false); setI((n) => Math.min(n + 1, steps.length - 1)); return; } // элемента нет — пропускаем шаг
      elRef.current = el;
      el.scrollIntoView({ block: "nearest", inline: "nearest" });
      await sleep(60); measure();
      const r = el.getBoundingClientRect();
      if (step.action) {
        setPhase("move"); setCursor({ x: r.left + Math.min(r.width / 2, 120), y: r.top + Math.min(r.height / 2, 40) });
        await sleep(750); if (!alive()) return;
        setPhase("hover"); el.classList.add("tour-hover");
        await sleep(650); if (!alive()) return;
        if (step.action === "click") {
          setPhase("click"); await sleep(450); if (!alive()) return;
          if (step.realClick) {
            const btn = el.matches("button") ? el : el.querySelector("button");
            (btn as HTMLElement | null)?.click();
            await sleep(350); measure();
          }
        }
      }
      setBusy(false);
    })();
  }, [open, i]); // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    if (!open) return;
    const h = () => measure();
    window.addEventListener("resize", h); window.addEventListener("scroll", h, true);
    return () => { window.removeEventListener("resize", h); window.removeEventListener("scroll", h, true); };
  }, [open, measure]);

  const close = useCallback(() => {
    run.current++;
    document.querySelectorAll(".tour-hover").forEach((e) => e.classList.remove("tour-hover"));
    try { localStorage.setItem("tour.seen", "1"); } catch { /* */ }
    api.closeAll(); onClose();
  }, [api, onClose]);
  const next = useCallback(() => (i >= steps.length - 1 ? close() : setI(i + 1)), [i, steps.length, close]);
  const prev = useCallback(() => setI((n) => Math.max(0, n - 1)), []);

  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
      else if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); e.stopPropagation(); next(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); prev(); }
    };
    window.addEventListener("keydown", h, true);
    return () => window.removeEventListener("keydown", h, true);
  }, [open, next, prev, close]);

  if (!open) return null;

  // карточка: под элементом, если есть место, иначе над ним; для больших элементов — у нижнего края
  const W = 380, vw = window.innerWidth, vh = window.innerHeight;
  let card: React.CSSProperties = { left: vw / 2 - W / 2, top: vh / 2 - 120 };
  if (rect) {
    const left = Math.min(Math.max(16, rect.x), vw - W - 16);
    if (rect.y + rect.h + 230 < vh) card = { left, top: rect.y + rect.h + 12 };
    else if (rect.y > 250) card = { left, top: rect.y - 12, transform: "translateY(-100%)" };
    else card = { left: vw - W - 24, top: vh - 24, transform: "translateY(-100%)" };
  }

  return (
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-text">
      <div className="tour-catch" onClick={(e) => e.stopPropagation()} />
      <div className="tour-spot" style={rect ? { left: rect.x, top: rect.y, width: rect.w, height: rect.h } : { left: vw / 2, top: vh / 2, width: 0, height: 0 }} />
      {step.action && phase !== "idle" && (
        <div className={`tour-cursor ${phase}`} style={{ transform: `translate(${cursor.x}px, ${cursor.y}px)` }} aria-hidden="true">
          <svg width="22" height="26" viewBox="0 0 22 26"><path d="M2 2 L2 21 L7 16.5 L10.5 24 L14 22.5 L10.5 15 L17 15 Z" fill="#fff" stroke="#0a0a0a" strokeWidth="1.6" strokeLinejoin="round" /></svg>
          {phase === "click" && <span className="tour-ripple" />}
        </div>
      )}
      <div className="tour-card" style={{ ...card, width: W }}>
        <div className="tour-meta"><span>{step.scenario}</span><span>{i + 1} / {steps.length}</span></div>
        <h3 id="tour-title">{step.title}</h3>
        <p id="tour-text">{step.text}</p>
        {step.action && <p className="tour-act">{step.action === "click" ? "Действие: нажмите" : "Действие: наведите курсор"}{busy ? " — смотрите, как это выглядит" : ""}</p>}
        <div className="tour-progress" aria-hidden="true"><span style={{ width: `${((i + 1) / steps.length) * 100}%` }} /></div>
        <div className="tour-actions">
          <button className="linkbtn" onClick={close}>Пропустить тур</button>
          <span style={{ flex: 1 }} />
          {i > 0 && <button className="btn" onClick={prev}>Назад</button>}
          <button className="btn primary" onClick={next} autoFocus>{i >= steps.length - 1 ? "Готово" : "Далее →"}</button>
        </div>
      </div>
    </div>
  );
}
