// Shared types for the Quotation Builder.
// Kept isolated so components can depend on these without touching the context.

export type ProductVariant = {
  sku: string; finish?: string | null; size?: string | null; color?: string | null;
  mrp: number; price: number; stock?: number;
  // Populated dynamically by the backend from family-sibling products —
  // lets a finish/colour chip switch the main image, not just the price.
  id?: string | null; image?: string | null;
};

export type Product = {
  id: string; name: string; sku: string; price: number; mrp: number;
  finish?: string | null; size?: string | null; images: string[]; category_id: string; brand_id: string;
  variants?: ProductVariant[];
  // Real media pipeline fields (Supabase-backed) — `images` above is kept in
  // sync with these server-side, but components should prefer
  // `productImageList()` which reads all three consistently.
  hero_image_url?: string | null;
  gallery?: { url: string; role?: string; source_type?: string; quality?: string }[] | null;
  // Optional metadata used by the Assistant (family, brand name, series, stock).
  family_key?: string | null;
  brand_name?: string | null;
  series?: string | null;
  collection?: string | null;
  subcategory?: string | null;
  stock?: number | null;
  description?: string | null;
  dimensions?: string | null;
  warranty?: string | null;
  specs?: Record<string, any> | null;
  // V4 ranking / badge signals (populated by /products endpoint).
  popular?: boolean;
  frequently_used?: boolean;
  recently_used?: boolean;
  usage_count?: number;
  my_usage_count?: number;
  is_custom?: boolean;
};

export type Brand = { id: string; name: string; slug?: string; product_count?: number };

export type Category = { id: string; name: string; product_count?: number };

export type Customer = { id: string; name: string; company?: string | null; email?: string | null; phone?: string | null };

// V4 header fields — captured on the topbar so the salesperson never leaves the workspace.
export type QuotationHeader = {
  projectName: string;
  phone: string;
  referenceSource: string;
};

export type RecentQuotation = {
  id: string; number: string;
  customer_id?: string | null; customer_name?: string | null;
  project_name?: string | null; phone?: string | null;
  grand_total: number; status: string;
  revision_count: number;
  updated_at?: string | null; created_at?: string | null;
};

export type Line = {
  id: string; product_id: string; sku: string; name: string; image?: string | null;
  category_id?: string | null; room?: string;
  qty: number; unit_price: number; mrp?: number | null;
  discount_pct: number | null;
  description?: string | null; notes?: string | null;
  finish?: string | null;
  family_key?: string | null;
};

export type SaveState = "idle" | "saving" | "saved" | "error";

// Room-level discount — either a flat percentage off every line in the room,
// or a fixed rupee amount off the room's subtotal (allocated proportionally
// across its lines for itemised display). Product-level overrides always
// win over this; this in turn always wins over category/project discounts.
export type RoomDiscount = { type: "percent" | "amount"; value: number };

// One immutable snapshot of everything the user can undo.
export type BuilderState = {
  customerId: string | null;
  header: QuotationHeader;
  lines: Line[];
  rooms: string[];
  collapsedRooms: Record<string, boolean>;
  activeRoom: string;
  notes: string;
  projectDiscount: number;
  categoryDiscounts: Record<string, number>;
  roomDiscounts: Record<string, RoomDiscount>;
};

// Flat row model for the receipt DnD list (mixes room headers + lines).
export type BuilderRow =
  | { kind: "room-header"; id: string; roomName: string; itemCount: number; subtotal: number; collapsed: boolean; roomDiscount: RoomDiscount | null }
  | { kind: "line"; id: string; line: Line };

// Sheet state descriptors.
export type DiscountSheetState =
  | null
  | { kind: "project" }
  | { kind: "category"; category_id: string }
  | { kind: "line"; line_id: string }
  | { kind: "room"; room: string };

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
  header: { projectName: "", phone: "", referenceSource: "" },
  lines: [],
  rooms: [DEFAULT_ROOMS[0]],
  collapsedRooms: {},
  activeRoom: DEFAULT_ROOMS[0],
  notes: "",
  projectDiscount: 0,
  categoryDiscounts: {},
  roomDiscounts: {},
};
