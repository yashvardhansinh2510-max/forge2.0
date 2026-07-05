// Shared types for the Quotation Builder.
// Kept isolated so components can depend on these without touching the context.

export type ProductVariant = {
  sku: string; finish?: string | null; size?: string | null; color?: string | null;
  mrp: number; price: number; stock?: number;
};

export type Product = {
  id: string; name: string; sku: string; price: number; mrp: number;
  finish?: string | null; images: string[]; category_id: string; brand_id: string;
  variants?: ProductVariant[];
  // Optional metadata used by the Assistant (family, brand name, series, stock).
  family_key?: string | null;
  brand_name?: string | null;
  series?: string | null;
  collection?: string | null;
  subcategory?: string | null;
  stock?: number | null;
  specs?: Record<string, any> | null;
};

export type Category = { id: string; name: string };

export type Customer = { id: string; name: string; company?: string | null; email: string };

export type Line = {
  id: string; product_id: string; sku: string; name: string; image?: string | null;
  category_id?: string | null; room?: string;
  qty: number; unit_price: number;
  discount_pct: number | null;
  description?: string | null; notes?: string | null;
  finish?: string | null;
  family_key?: string | null;
};

export type SaveState = "idle" | "saving" | "saved" | "error";

// One immutable snapshot of everything the user can undo.
export type BuilderState = {
  customerId: string | null;
  lines: Line[];
  rooms: string[];
  collapsedRooms: Record<string, boolean>;
  activeRoom: string;
  notes: string;
  projectDiscount: number;
  categoryDiscounts: Record<string, number>;
};

// Flat row model for the receipt DnD list (mixes room headers + lines).
export type BuilderRow =
  | { kind: "room-header"; id: string; roomName: string; itemCount: number; subtotal: number; collapsed: boolean }
  | { kind: "line"; id: string; line: Line };

// Sheet state descriptors.
export type DiscountSheetState =
  | null
  | { kind: "project" }
  | { kind: "category"; category_id: string }
  | { kind: "line"; line_id: string };

export type RoomSheetState =
  | null
  | { kind: "add" }
  | { kind: "rename"; name: string };

export type DescSheetState = null | { line_id: string };

export type SwapSheetState = null | { line_id: string; product_id: string };

export type PickerTab = "search" | "recent" | "frequent";

export const DEFAULT_ROOMS = [
  "Master Bath", "Powder Room", "Guest Bath", "Kitchen", "Utility", "Living", "Study",
];

export const INITIAL_BUILDER_STATE: BuilderState = {
  customerId: null,
  lines: [],
  rooms: [DEFAULT_ROOMS[0]],
  collapsedRooms: {},
  activeRoom: DEFAULT_ROOMS[0],
  notes: "",
  projectDiscount: 0,
  categoryDiscounts: {},
};
