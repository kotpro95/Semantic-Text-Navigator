export type Evidence = { doc_id: string; filename: string; paragraph: number; quote: string; doc_label: string };
export type Rejected = { display: string; reason: string; evidence: Evidence };
export type HistoryStep = {
  state: "base" | "applied" | "superseded" | "pending";
  date: string | null; doc_id: string; doc_label: string; display: string | null; reason: string; evidence: Evidence[];
};
export type FieldStatus = "ok" | "changed" | "missing" | "review";
export type FieldView = {
  field: string; label: string; value: string | null; display: string | null; status: FieldStatus;
  evidence: Evidence[]; changed_by: string | null; note: string | null; history: HistoryStep[]; rejected: Rejected[];
};
export type PendingChange = {
  field: string; label: string; current_display: string | null; proposed_display: string;
  doc_id: string; doc_label: string; reason: string; evidence: Evidence;
};
export type Flag = { level: string; text: string; doc_id: string | null };
export type ContractView = {
  number: string; doc_id: string; filename: string; fields: Record<string, FieldView>;
  pending: PendingChange[]; flags: Flag[]; related_docs: string[];
};
export type DocSummary = {
  id: string; filename: string; kind: "contract" | "amendment" | "amendment_draft" | "letter" | "unknown";
  label: string; contract_number: string | null; signed: boolean; signed_date: string | null;
  effective_date: string | null; status_text: string | null; issues: string[];
};
export type Registry = {
  as_of: string; fields: { name: string; label: string; in_registry: boolean }[];
  contracts: ContractView[]; flags: Flag[]; documents: DocSummary[]; llm: { enabled: boolean; model: string | null };
};
export type Paragraph = { n: number; clause: string | null; text: string };
export type DocumentFull = DocSummary & {
  paragraphs: Paragraph[]; status_evidence: Evidence | null; effective_evidence: Evidence | null;
};
export type DeliveryRow = {
  contract: string; display: string | null; status: FieldStatus; evidence: Evidence[];
  pending: PendingChange[]; reason?: string;
};
export type Answer = {
  kind: "field" | "delivery_before"; question: string; text: string; as_of: string; contract: string | null;
  field: FieldView | null; pending: PendingChange[]; matches: DeliveryRow[]; excluded: DeliveryRow[]; evidence: Evidence[];
};

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not json */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

export const api = {
  registry: (asOf: string) => req<Registry>(`/api/registry?as_of=${asOf}`),
  upload: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return req<DocSummary[]>("/api/documents", { method: "POST", body: fd });
  },
  samples: () => req<DocSummary[]>("/api/documents/samples", { method: "POST" }),
  document: (id: string) => req<DocumentFull>(`/api/documents/${id}`),
  remove: (id: string) => req(`/api/documents/${id}`, { method: "DELETE" }),
  clear: () => req("/api/documents", { method: "DELETE" }),
  ask: (q: string, asOf: string) => req<Answer>(`/api/ask?q=${encodeURIComponent(q)}&as_of=${asOf}`),
};

export const fmtDate = (iso: string | null) => (iso ? iso.split("-").reverse().join(".") : "—");
