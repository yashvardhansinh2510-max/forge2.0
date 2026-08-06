export type NotebookStatus = "new" | "pending" | "won" | "lost";
export type NotebookView = "followups" | "quotation";
export type NotebookFilter = "all" | "pending" | "won" | "lost" | "new" | "quotation";
export type NotebookField =
  | "customer_name"
  | "customer_phone"
  | "address"
  | "kitchen_type"
  | "referred_by"
  | "architect_interior_designer"
  | "status"
  | "notes"
  | "quotation_price"
  | "estimated_value"
  | "quotation_date";

export type NotebookRow = {
  id: string;
  customer_name: string;
  customer_phone: string;
  address: string;
  kitchen_type: "GI" | "SS" | "";
  referred_by: string;
  architect_interior_designer: string;
  status: NotebookStatus;
  notes: string;
  is_converted: boolean;
  updated_at: string;
  quotation_price?: number | null;
  estimated_value?: number | null;
  quotation_date?: string | null;
};

export type NotebookColumn = {
  key: NotebookField;
  label: string;
  minWidth: number;
  editable: boolean;
  quotationOnly?: boolean;
};

export type CellPosition = { row: number; column: number };
export type CellKey = "Enter" | "Tab" | "Shift+Tab" | "Escape" | "ArrowUp" | "ArrowDown" | "ArrowLeft" | "ArrowRight";

