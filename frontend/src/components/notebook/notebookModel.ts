import type { CellKey, CellPosition, NotebookColumn, NotebookField, NotebookFilter, NotebookRow, NotebookView } from "./notebookTypes";

export const NOTEBOOK_COLUMNS: readonly NotebookColumn[] = [
  { key: "customer_name", label: "Customer Name", minWidth: 190, editable: true },
  { key: "customer_phone", label: "Mobile Number", minWidth: 145, editable: true },
  { key: "address", label: "Address", minWidth: 220, editable: true },
  { key: "kitchen_type", label: "Kitchen Type", minWidth: 125, editable: true },
  { key: "referred_by", label: "Referred By", minWidth: 155, editable: true },
  { key: "architect_interior_designer", label: "Architect / Interior Designer", minWidth: 220, editable: true },
  { key: "status", label: "Status", minWidth: 110, editable: true },
  { key: "notes", label: "Notes", minWidth: 260, editable: true },
];

export const QUOTATION_COLUMNS: readonly NotebookColumn[] = [
  { key: "quotation_price", label: "Quotation Price", minWidth: 155, editable: true, quotationOnly: true },
  { key: "estimated_value", label: "Estimated Value", minWidth: 155, editable: true, quotationOnly: true },
  { key: "quotation_date", label: "Quotation Date", minWidth: 145, editable: true, quotationOnly: true },
];

export const NOTEBOOK_FILTERS: readonly NotebookFilter[] = ["all", "pending", "won", "lost", "new", "quotation"];

export function columnsForView(view: NotebookView): readonly NotebookColumn[] {
  return view === "quotation" ? [...NOTEBOOK_COLUMNS, ...QUOTATION_COLUMNS] : NOTEBOOK_COLUMNS;
}

const SEARCH_FIELDS: readonly NotebookField[] = [
  "customer_name", "customer_phone", "address", "architect_interior_designer", "referred_by", "notes",
];

export function searchNotebookRows(rows: readonly NotebookRow[], query: string): NotebookRow[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [...rows];
  return rows.filter((row) => SEARCH_FIELDS.some((field) => String(row[field] ?? "").toLocaleLowerCase().includes(needle)));
}

export function nextCell(position: CellPosition, key: CellKey, rowCount: number, columnCount: number): CellPosition | null {
  if (key === "Enter") return position;
  if (key === "Escape") return null;
  let row = position.row;
  let column = position.column;
  if (key === "Tab") column += 1;
  if (key === "Shift+Tab") column -= 1;
  if (key === "ArrowDown") row += 1;
  if (key === "ArrowUp") row -= 1;
  if (key === "ArrowRight") column += 1;
  if (key === "ArrowLeft") column -= 1;
  if (column >= columnCount) { column = 0; row += 1; }
  if (column < 0) { column = columnCount - 1; row -= 1; }
  if (row < 0 || row >= rowCount) return null;
  return { row, column };
}

export function applyCellPatch(row: NotebookRow, field: NotebookField, value: unknown): NotebookRow {
  return { ...row, [field]: value } as NotebookRow;
}

export function formatRupees(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value)}`;
}

export function formatIndianDate(value: string | null | undefined): string {
  if (!value) return "—";
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(value)) return value;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

