// TilesDocBuilder — Ground Floor → Tiles → Selection / Quotation.
// -----------------------------------------------------------------------------
// Each page renders as an editable on-screen replica of its official printed
// document (the PDFs the backend generates from the same record), backed by
// the existing quotation infrastructure: customers, autosave (silent PATCH),
// activity logging, the /quotations PDF endpoint and the Purchase Order
// workflow. Product rows are added manually with the "+" button (max 11) and
// filled through the text-only SKU/name picker; every populated value stays
// editable afterwards.
//
// Recorded design decision (Production readiness audit, 2026-07-23): this
// component deliberately bypasses both the shared design-token system
// (colors.ts / tokens.ts) and the app's useBp() breakpoint standard. Both
// are consequences of the same constraint — the "paper" is a fixed-size,
// pixel-faithful replica of a specific printed form (see PAPER_W below), not
// a responsive app screen, so it renders inside a horizontal ScrollView on
// narrow viewports instead of reflowing. The hardcoded hex values throughout
// this file mirror the printed document's own fixed colors (its blue sheet
// background, ruled borders, red highlight text) rather than the app's
// theme, which would drift the on-screen replica away from what actually
// prints. Not a defect to fix — recorded here so it reads as an intentional
// choice rather than an unexplained gap the next person has to re-diagnose.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { productImageList } from "@/src/components/quotation/helpers/media";
import type { Customer, Product } from "@/src/components/quotation/helpers/types";
import { BuildConLogo } from "@/src/design/BrandLogo";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";
import { downloadApiFile, printApiFile } from "@/src/utils/downloadFile";

import { TilesProductPicker } from "./TilesProductPicker";

export type TilesDocType = "tiles_selection" | "tiles_quotation";

const MAX_ROWS = 11;
const PAPER_W = 820;
const SHEET_BLUE = "#CBE7F5";
const CELL_GREY = "#BFBFBF";
const HEAD_GREY = "#D3D3D3";
const SERIF = Platform.select({ ios: "Times New Roman", android: "serif", default: "Georgia, 'Times New Roman', serif" }) as string;

type TileRow = {
  key: string;
  lineId: string | null;
  productId: string | null;
  sku: string;
  categoryId: string | null;
  name: string;
  image: string | null;
  mrp: number | null;
  area: string;
  size: string;
  rateSqft: string;
  rateBox: string;
  totalBox: string;
  pcsBox: string;
  total: string;
  totalEdited: boolean;
};

type TilesHeader = {
  customerName: string;
  phone: string;
  reference: string;
  docDate: string;
  attendedBy: string;
  preparedBy: string;
  address: string;
  docNumber: string;
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function defaultDocDate(docType: TilesDocType): string {
  const now = new Date();
  const dd = String(now.getDate()).padStart(2, "0");
  if (docType === "tiles_selection") {
    return `${dd}-${MONTHS[now.getMonth()]}-${String(now.getFullYear()).slice(2)}`;
  }
  return `${dd}-${String(now.getMonth() + 1).padStart(2, "0")}-${now.getFullYear()}`;
}

function parseDocDate(raw: string): Date | null {
  const text = (raw || "").trim();
  let m = text.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
  if (m) return new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  m = text.match(/^(\d{1,2})[-/ ]([A-Za-z]{3,})[-/ ](\d{2,4})$/);
  if (m) {
    const month = MONTHS.findIndex((x) => m![2].toLowerCase().startsWith(x.toLowerCase()));
    if (month >= 0) {
      const year = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
      return new Date(year, month, Number(m[1]));
    }
  }
  return null;
}

function pdfFilename(customerName: string, docDate: string): string {
  const d = parseDocDate(docDate) || new Date();
  const stamp = `${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;
  const name = (customerName || "Customer").trim().replace(/[\\/:*?"<>|]/g, "");
  return `${name} ${stamp}.pdf`;
}

function emptyRow(): TileRow {
  return {
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    lineId: null, productId: null, sku: "", categoryId: null,
    name: "", image: null, mrp: null,
    area: "", size: "", rateSqft: "", rateBox: "", totalBox: "", pcsBox: "BOX", total: "",
    totalEdited: false,
  };
}

const num = (text: string): number => {
  const value = parseFloat(String(text).replace(/,/g, ""));
  return Number.isFinite(value) ? value : 0;
};

function computedTotal(row: TileRow): string {
  const total = num(row.rateBox) * num(row.totalBox);
  return total ? String(Math.round(total * 100) / 100) : "";
}

// ---------------------------------------------------------------------------
// Document state + persistence
// ---------------------------------------------------------------------------
function useTilesDoc(docType: TilesDocType) {
  const router = useRouter();
  const { id: routeId } = useLocalSearchParams<{ id?: string }>();
  const [docId, setDocId] = useState<string | null>((routeId as string) || null);
  const [docNumberServer, setDocNumberServer] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [customerSnapshot, setCustomerSnapshot] = useState<{ name: string; phone: string }>({ name: "", phone: "" });
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [header, setHeader] = useState<TilesHeader>({
    customerName: "", phone: "", reference: "", docDate: defaultDocDate(docType),
    attendedBy: "", preparedBy: "", address: "", docNumber: "",
  });
  const [rows, setRows] = useState<TileRow[]>([emptyRow()]);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(routeId));
  const dirtyRef = useRef(false);
  const persistRef = useRef<() => Promise<string | null>>(async () => null);

  useEffect(() => {
    api.get<Customer[]>("/customers").then(setCustomers).catch(() => {});
  }, []);

  // Restore a saved document.
  useEffect(() => {
    if (!routeId) return;
    let alive = true;
    (async () => {
      try {
        const doc = await api.get<any>(`/quotations/${routeId}`);
        if (!alive) return;
        setDocId(doc.id);
        setDocNumberServer(doc.number || null);
        setCustomerId(doc.customer_id || null);
        setCustomerSnapshot({ name: doc.customer_name || "", phone: doc.phone_snapshot || "" });
        setHeader({
          customerName: doc.customer_name || "",
          phone: doc.phone_snapshot || "",
          reference: doc.reference_source || "",
          docDate: doc.doc_date || defaultDocDate(docType),
          attendedBy: doc.attended_by || "",
          preparedBy: doc.prepared_by || "",
          address: doc.address_snapshot || "",
          docNumber: doc.doc_number || doc.number || "",
        });
        const restored: TileRow[] = (doc.items || []).map((it: any): TileRow => ({
          key: it.id || `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          lineId: it.id || null,
          productId: it.product_id || null,
          sku: it.sku || "",
          categoryId: it.category_id || null,
          name: it.name || "",
          image: it.image || null,
          mrp: it.mrp ?? null,
          area: it.room || "",
          size: it.size || "",
          rateSqft: it.rate_sqft != null ? String(it.rate_sqft) : "",
          rateBox: it.unit_price ? String(it.unit_price) : "",
          totalBox: it.qty ? String(it.qty) : "",
          pcsBox: it.pcs_per_box || "BOX",
          total: it.qty && it.unit_price ? String(Math.round(it.qty * it.unit_price * 100) / 100) : "",
          totalEdited: false,
        }));
        setRows(restored.length ? restored : [emptyRow()]);
      } catch (e: any) {
        toast.error(e?.detail || "Couldn't open that document");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [routeId, docType]);

  const markDirty = useCallback(() => { dirtyRef.current = true; }, []);

  const setHeaderField = useCallback((field: keyof TilesHeader, value: string) => {
    setHeader((cur) => ({ ...cur, [field]: value }));
    markDirty();
  }, [markDirty]);

  const updateRow = useCallback((key: string, patch: Partial<TileRow>) => {
    setRows((cur) => cur.map((row) => {
      if (row.key !== key) return row;
      const next = { ...row, ...patch };
      if ("total" in patch) {
        next.totalEdited = true;
      } else if ("rateBox" in patch || "totalBox" in patch) {
        next.totalEdited = false;
        next.total = computedTotal(next);
      }
      return next;
    }));
    markDirty();
  }, [markDirty]);

  const addRow = useCallback(() => {
    setRows((cur) => (cur.length >= MAX_ROWS ? cur : [...cur, emptyRow()]));
    markDirty();
  }, [markDirty]);

  const removeRow = useCallback((key: string) => {
    setRows((cur) => {
      const next = cur.filter((row) => row.key !== key);
      return next.length ? next : [emptyRow()];
    });
    markDirty();
  }, [markDirty]);

  const applyProduct = useCallback((key: string, product: Product) => {
    const image = productImageList(product)[0] || null;
    const specs = product.specs || {};
    const specNum = (...keys: string[]): string => {
      for (const k of keys) {
        const v = (specs as any)[k];
        if (v != null && v !== "" && Number.isFinite(parseFloat(String(v)))) return String(v);
      }
      return "";
    };
    const specText = (...keys: string[]): string => {
      for (const k of keys) {
        const v = (specs as any)[k];
        if (v != null && String(v).trim()) return String(v);
      }
      return "";
    };
    setRows((cur) => cur.map((row) => {
      if (row.key !== key) return row;
      const next: TileRow = {
        ...row,
        productId: product.id,
        sku: product.sku,
        categoryId: product.category_id || null,
        name: product.name,
        image,
        mrp: product.mrp ?? null,
        size: product.size || product.dimensions || row.size,
        rateSqft: product.price ? String(product.price) : row.rateSqft,
        rateBox: specNum("rate_per_box", "rate_box", "box_rate") || row.rateBox,
        pcsBox: specText("pcs_per_box", "pcs_box", "pcs") || row.pcsBox,
        totalEdited: false,
      };
      next.total = computedTotal(next);
      return next;
    }));
    markDirty();
  }, [markDirty]);

  // ---- Persistence -------------------------------------------------------
  const buildItems = useCallback(() => {
    return rows
      .filter((row) => row.productId && row.name.trim())
      .map((row, index) => {
        const qty = num(row.totalBox) || 1;
        const manualTotal = num(row.total);
        const unitPrice = row.totalEdited && manualTotal > 0 && qty > 0
          ? Math.round((manualTotal / qty) * 100) / 100
          : num(row.rateBox);
        const item: any = {
          product_id: row.productId, sku: row.sku, name: row.name.trim(),
          image: row.image, category_id: row.categoryId,
          room: row.area.trim() || null,
          qty, unit_price: unitPrice,
          mrp: row.mrp,
          size: row.size.trim() || null,
          rate_sqft: row.rateSqft.trim() ? num(row.rateSqft) : null,
          pcs_per_box: row.pcsBox.trim() || null,
          sort_order: index,
        };
        if (row.lineId) item.id = row.lineId;
        return item;
      });
  }, [rows]);

  const persist = useCallback(async ({ silent = true }: { silent?: boolean } = {}): Promise<string | null> => {
    const name = header.customerName.trim();
    if (!name) {
      toast.show("Enter the customer name first");
      return null;
    }
    setSaveState("saving");
    try {
      // 1. Resolve the customer — reuse an explicit pick, else create one.
      let cid = customerId;
      if (!cid) {
        const created = await api.post<Customer>("/customers", { name, phone: header.phone.trim() || null });
        cid = created.id;
        setCustomerId(created.id);
        setCustomerSnapshot({ name, phone: header.phone.trim() });
        setCustomers((cur) => [created, ...cur]);
      } else if (name !== customerSnapshot.name || header.phone.trim() !== customerSnapshot.phone) {
        // Header edits correct the customer record (typo fixes stay in sync).
        await api.patch(`/customers/${cid}`, { name, phone: header.phone.trim() || null }).catch(() => {});
        setCustomerSnapshot({ name, phone: header.phone.trim() });
      }

      const payload: any = {
        customer_id: cid,
        items: buildItems(),
        rooms: [],
        phone_snapshot: header.phone.trim() || null,
        reference_source: header.reference.trim() || null,
        attended_by: header.attendedBy.trim() || null,
        prepared_by: header.preparedBy.trim() || null,
        address_snapshot: header.address.trim() || null,
        doc_date: header.docDate.trim() || null,
        doc_number: header.docNumber.trim() || null,
      };
      let id = docId;
      if (!id) {
        const created = await api.post<{ id: string; number: string }>("/quotations", { ...payload, doc_type: docType });
        id = created.id;
        setDocId(created.id);
        setDocNumberServer(created.number);
        if (docType === "tiles_quotation" && !header.docNumber.trim()) {
          setHeader((cur) => ({ ...cur, docNumber: created.number }));
        }
        router.setParams({ id: created.id });
      } else {
        await api.patch(`/quotations/${id}`, { ...payload, silent, reason: silent ? undefined : "Saved from tiles builder" });
      }
      dirtyRef.current = false;
      setSaveState("saved");
      return id;
    } catch (e: any) {
      setSaveState("error");
      toast.error(e?.detail || "Save failed");
      return null;
    }
  }, [header, customerId, customerSnapshot, docId, docType, buildItems, router]);
  persistRef.current = () => persist({ silent: true });

  // Autosave: once the document exists, silently persist edits.
  useEffect(() => {
    if (!docId || !dirtyRef.current) return;
    const timer = setTimeout(() => { void persistRef.current(); }, 900);
    return () => clearTimeout(timer);
  }, [docId, header, rows]);

  const save = useCallback(async () => {
    setBusy("save");
    const id = await persist({ silent: false });
    setBusy(null);
    if (id) toast.success("Saved");
  }, [persist]);

  const generatePdf = useCallback(async () => {
    setBusy("pdf");
    try {
      const id = await persist({ silent: true });
      if (!id) return;
      await downloadApiFile(`/quotations/${id}/pdf`, pdfFilename(header.customerName, header.docDate), "PDF");
    } finally {
      setBusy(null);
    }
  }, [persist, header.customerName, header.docDate]);

  const print = useCallback(async () => {
    setBusy("print");
    try {
      const id = await persist({ silent: true });
      if (!id) return;
      await printApiFile(`/quotations/${id}/pdf`, "PDF");
    } finally {
      setBusy(null);
    }
  }, [persist]);

  const placeOrder = useCallback(async () => {
    setBusy("order");
    const id = await persist({ silent: true });
    setBusy(null);
    if (!id) return;
    if (!buildItems().length) {
      toast.show("Add at least one product first");
      return;
    }
    router.push(`/(admin)/quotations/${id}/place-order` as any);
  }, [persist, buildItems, router]);

  const pickCustomer = useCallback((customer: Customer) => {
    setCustomerId(customer.id);
    setCustomerSnapshot({ name: customer.name, phone: customer.phone || "" });
    setHeader((cur) => ({ ...cur, customerName: customer.name, phone: customer.phone || cur.phone }));
    markDirty();
  }, [markDirty]);

  return {
    docId, docNumberServer, loading, header, setHeaderField, rows,
    updateRow, addRow, removeRow, applyProduct,
    customers, customerId, pickCustomer, setCustomerId,
    saveState, busy, save, generatePdf, print, placeOrder,
  };
}

// ---------------------------------------------------------------------------
// Small shared pieces
// ---------------------------------------------------------------------------
function CellInput({
  value, onChangeText, style, placeholder, red, bold, serif, multiline, testID, align = "center",
}: {
  value: string; onChangeText: (t: string) => void;
  style?: any; placeholder?: string; red?: boolean; bold?: boolean; serif?: boolean;
  multiline?: boolean; testID?: string; align?: "left" | "center" | "right";
}) {
  return (
    <TextInput
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor="#77777"
      multiline={multiline}
      testID={testID}
      style={[
        cellStyles.input,
        { textAlign: align },
        serif ? { fontFamily: SERIF } : null,
        bold ? { fontWeight: "700" } : null,
        red ? { color: "#E00000" } : null,
        style,
      ]}
    />
  );
}

const cellStyles = StyleSheet.create({
  input: {
    fontSize: 12.5, color: "#111", paddingVertical: 2, paddingHorizontal: 3,
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
});

function CustomerNameField({
  value, onChangeText, customers, customerId, onPickCustomer, inputStyle, testID,
}: {
  value: string; onChangeText: (t: string) => void;
  customers: Customer[]; customerId: string | null;
  onPickCustomer: (c: Customer) => void;
  inputStyle?: any; testID?: string;
}) {
  const [focused, setFocused] = useState(false);
  const matches = useMemo(() => {
    const q = value.trim().toLowerCase();
    if (!q || q.length < 2) return [];
    return customers
      .filter((c) => c.name.toLowerCase().includes(q) || (c.phone || "").includes(q))
      .slice(0, 5);
  }, [value, customers]);
  const exactPicked = customerId && matches.length === 1 && matches[0].id === customerId;
  const show = focused && matches.length > 0 && !exactPicked;
  return (
    <View style={{ flex: 1, zIndex: 400 }}>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 180)}
        placeholder="Customer name"
        placeholderTextColor="#999"
        testID={testID}
        style={[cellStyles.input, { textAlign: "left" }, inputStyle]}
      />
      {show ? (
        <View style={suggestStyles.panel}>
          {matches.map((c) => (
            <Pressable
              key={c.id}
              // Both handlers on purpose: onPressIn beats the TextInput's
              // delayed blur-hide for real pointers, while web click events
              // (keyboard, assistive tech, automation) arrive as onPress.
              // Picking twice is idempotent.
              onPressIn={() => { onPickCustomer(c); setFocused(false); }}
              onPress={() => { onPickCustomer(c); setFocused(false); }}
              style={({ hovered }: any) => [suggestStyles.row, hovered && { backgroundColor: colors.brandTint }]}
            >
              <Text style={suggestStyles.name} numberOfLines={1}>{c.name}</Text>
              {c.phone ? <Text style={suggestStyles.phone}>{c.phone}</Text> : null}
            </Pressable>
          ))}
          <Text style={suggestStyles.hint}>Pick to reuse an existing customer — or keep typing to create a new one on save.</Text>
        </View>
      ) : null}
    </View>
  );
}

const suggestStyles = StyleSheet.create({
  panel: {
    position: "absolute", top: "100%", left: 0, right: 0, marginTop: 3,
    backgroundColor: colors.surface, borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    zIndex: 100, overflow: "hidden",
    ...(Platform.OS === "web" ? { boxShadow: "0 10px 28px rgba(0,0,0,0.18)" } as any : {}),
  },
  row: { paddingHorizontal: 10, paddingVertical: 7, flexDirection: "row", justifyContent: "space-between", gap: 8 },
  name: { fontSize: 12.5, fontWeight: "600", color: colors.onSurface, flexShrink: 1 },
  phone: { fontSize: 11.5, color: colors.onSurfaceSecondary, fontVariant: ["tabular-nums"] },
  hint: {
    fontSize: 10, color: colors.onSurfaceMuted, paddingHorizontal: 10, paddingVertical: 5,
    borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.divider,
  },
});

function ProductCell({
  row, onOpenPicker, onChangeName, bold, testID,
}: {
  row: TileRow; onOpenPicker: () => void; onChangeName: (t: string) => void; bold?: boolean; testID?: string;
}) {
  if (!row.productId) {
    return (
      <Pressable onPress={onOpenPicker} style={productStyles.pickTarget} testID={testID}>
        <Feather name="search" size={13} color="#555" />
        <Text style={productStyles.pickLabel}>Select product…</Text>
      </Pressable>
    );
  }
  return (
    <View style={{ flex: 1, alignSelf: "stretch", justifyContent: "center" }}>
      <CellInput value={row.name} onChangeText={onChangeName} bold={bold} multiline testID={testID ? `${testID}-name` : undefined} />
      <Pressable onPress={onOpenPicker} hitSlop={13} style={productStyles.swapBtn} testID={testID ? `${testID}-swap` : undefined}>
        <Feather name="refresh-cw" size={11} color="#666" />
      </Pressable>
    </View>
  );
}

const productStyles = StyleSheet.create({
  pickTarget: {
    flex: 1, alignSelf: "stretch", alignItems: "center", justifyContent: "center",
    flexDirection: "row", gap: 6,
  },
  pickLabel: { fontSize: 12, color: "#555", fontStyle: "italic" },
  swapBtn: {
    position: "absolute", right: 2, bottom: 2, width: 18, height: 18,
    alignItems: "center", justifyContent: "center", borderRadius: 9,
    backgroundColor: "rgba(255,255,255,0.65)",
  },
});

function RowSideControls({
  isLast, canAdd, onAdd, onRemove, showRemove,
}: {
  isLast: boolean; canAdd: boolean; onAdd: () => void; onRemove: () => void; showRemove: boolean;
}) {
  return (
    <View style={sideStyles.wrap}>
      {/*
        Add/remove sit 8px apart in a 40px rail. Their hitSlop is deliberately
        asymmetric rather than a uniform ~44px pad on both: expanding evenly
        would make the two tap zones overlap in the gap between them, which
        turns "reach for add, land on remove" from a risk into a certainty.
        Each button's hitSlop is generous on the sides that face empty space
        and small on the side that faces the other button.
      */}
      {isLast && canAdd ? (
        <Pressable
          onPress={onAdd}
          style={sideStyles.addBtn}
          hitSlop={{ top: 12, left: 12, right: 12, bottom: 3 }}
          testID="tiles-add-row"
          accessibilityLabel="Add product row"
        >
          <Feather name="plus" size={16} color="#fff" />
        </Pressable>
      ) : null}
      {showRemove ? (
        <Pressable
          onPress={onRemove}
          style={sideStyles.removeBtn}
          hitSlop={{ top: 3, left: 14, right: 14, bottom: 14 }}
          testID="tiles-remove-row"
          accessibilityLabel="Remove row"
        >
          <Feather name="x" size={12} color="#8A3333" />
        </Pressable>
      ) : null}
    </View>
  );
}

const sideStyles = StyleSheet.create({
  wrap: {
    position: "absolute", right: -44, top: 0, bottom: 0,
    alignItems: "center", justifyContent: "center", gap: 8, width: 40,
  },
  addBtn: {
    width: 30, height: 30, borderRadius: 15, backgroundColor: colors.brand,
    alignItems: "center", justifyContent: "center",
    ...(Platform.OS === "web" ? { boxShadow: "0 3px 10px rgba(0,0,0,0.25)" } as any : {}),
  },
  removeBtn: {
    width: 20, height: 20, borderRadius: 10, backgroundColor: "#F6E3E3",
    alignItems: "center", justifyContent: "center",
  },
});

// ---------------------------------------------------------------------------
// SELECTION paper — replica of the grey selection sheet
// ---------------------------------------------------------------------------
const SEL_COLS = [13, 37, 52, 44, 23, 25]; // proportional to the printed mm widths

function SelectionPaper(doc: ReturnType<typeof useTilesDoc>) {
  const [pickerRow, setPickerRow] = useState<string | null>(null);
  const flex = (index: number) => ({ flex: SEL_COLS[index] });
  return (
    <View style={selStyles.paper}>
      <View style={{ alignItems: "center" }}>
        <BuildConLogo height={64} />
        <Text style={selStyles.address}>
          Nr. Gujarat Housing Board, Kataria Motors, 2nd 150 Ring Road, Rajkot-360005
        </Text>
      </View>
      <View style={selStyles.ruleThick} />
      <View style={selStyles.ruleThin} />

      {/* Header fields */}
      <View style={selStyles.headerRow}>
        <View style={{ flex: 1.55, gap: 6 }}>
          <View style={[selStyles.fieldRow, { zIndex: 400 }]}>
            <Text style={selStyles.fieldLabel}>NAME:</Text>
            <View style={[selStyles.fieldValueWrap, { zIndex: 400 }]}>
              <CustomerNameField
                value={doc.header.customerName}
                onChangeText={(t) => doc.setHeaderField("customerName", t)}
                customers={doc.customers}
                customerId={doc.customerId}
                onPickCustomer={doc.pickCustomer}
                testID="tiles-customer-name"
              />
            </View>
          </View>
          <View style={selStyles.fieldRow}>
            <Text style={selStyles.fieldLabel}>MOB:</Text>
            <View style={selStyles.fieldValueWrap}>
              <CellInput value={doc.header.phone} onChangeText={(t) => doc.setHeaderField("phone", t)} align="left" testID="tiles-phone" />
            </View>
          </View>
          <View style={selStyles.fieldRow}>
            <Text style={selStyles.fieldLabel}>REF:</Text>
            <View style={selStyles.fieldValueWrap}>
              <CellInput value={doc.header.reference} onChangeText={(t) => doc.setHeaderField("reference", t)} align="left" testID="tiles-reference" />
            </View>
          </View>
        </View>
        <View style={{ flex: 1, gap: 6 }}>
          <View style={selStyles.fieldRow}>
            <Text style={[selStyles.fieldLabel, { width: 110 }]}>SELECTION DT:</Text>
            <View style={selStyles.fieldValueWrap}>
              <CellInput value={doc.header.docDate} onChangeText={(t) => doc.setHeaderField("docDate", t)} testID="tiles-date" />
            </View>
          </View>
          <View style={selStyles.fieldRow}>
            <Text style={[selStyles.fieldLabel, { width: 110 }]}>ATTENDED BY:</Text>
            <View style={selStyles.fieldValueWrap}>
              <CellInput value={doc.header.attendedBy} onChangeText={(t) => doc.setHeaderField("attendedBy", t)} testID="tiles-attended" />
            </View>
          </View>
          <View style={selStyles.fieldRow}>
            <Text style={[selStyles.fieldLabel, { width: 110 }]}>PREPARED BY:</Text>
            <View style={selStyles.fieldValueWrap}>
              <CellInput value={doc.header.preparedBy} onChangeText={(t) => doc.setHeaderField("preparedBy", t)} testID="tiles-prepared" />
            </View>
          </View>
        </View>
      </View>

      {/* Product grid */}
      <View style={selStyles.table}>
        <View style={[selStyles.tr, { backgroundColor: HEAD_GREY, minHeight: 34 }]}>
          {["NO.", "AREA", "PRODUCT DETAIL", "IMAGE", "SIZE"].map((h, i) => (
            <View key={h} style={[selStyles.td, flex(i)]}><Text style={selStyles.th}>{h}</Text></View>
          ))}
          <View style={[selStyles.td, flex(5), { borderRightWidth: 0 }]}>
            <Text style={[selStyles.th, { color: "#E00000" }]}>RATE/SQ.FT</Text>
          </View>
        </View>
        {doc.rows.map((row, index) => (
          <View key={row.key} style={[selStyles.tr, { minHeight: 96, backgroundColor: CELL_GREY }]}>
            <View style={[selStyles.td, flex(0)]}><Text style={selStyles.cellText}>{index + 1}</Text></View>
            <View style={[selStyles.td, flex(1)]}>
              <CellInput value={row.area} onChangeText={(t) => doc.updateRow(row.key, { area: t })} placeholder="Area" multiline testID={`tiles-area-${index}`} />
            </View>
            <View style={[selStyles.td, flex(2)]}>
              <ProductCell
                row={row}
                onOpenPicker={() => setPickerRow(row.key)}
                onChangeName={(t) => doc.updateRow(row.key, { name: t })}
                testID={`tiles-product-${index}`}
              />
            </View>
            <View style={[selStyles.td, flex(3), { padding: 2 }]}>
              {row.image ? (
                <Image source={{ uri: row.image }} resizeMode="contain" style={{ width: "100%", height: 88 }} />
              ) : null}
            </View>
            <View style={[selStyles.td, flex(4)]}>
              <CellInput value={row.size} onChangeText={(t) => doc.updateRow(row.key, { size: t })} testID={`tiles-size-${index}`} />
            </View>
            <View style={[selStyles.td, flex(5), { borderRightWidth: 0 }]}>
              <CellInput value={row.rateSqft} onChangeText={(t) => doc.updateRow(row.key, { rateSqft: t })} red bold testID={`tiles-rate-${index}`} />
              <Text style={selStyles.rateSuffix}>PER SQFT</Text>
            </View>
            <RowSideControls
              isLast={index === doc.rows.length - 1}
              canAdd={doc.rows.length < MAX_ROWS}
              onAdd={doc.addRow}
              onRemove={() => doc.removeRow(row.key)}
              showRemove={doc.rows.length > 1}
            />
          </View>
        ))}
      </View>

      {/* Terms & Conditions */}
      <Text style={selStyles.termsTitle}>Terms &amp; Conditions</Text>
      <View style={{ gap: 3, paddingLeft: 18 }}>
        <Text style={selStyles.term}>1. <Text style={selStyles.termBold}>Prices</Text> quoted are based on the current <Text style={selStyles.termBold}>NET Prices</Text> at the time of selection.</Text>
        <Text style={selStyles.term}>2. <Text style={selStyles.termBold}>Prices revisions</Text> by <Text style={selStyles.termBold}>any brands</Text> may occur without prior notice.</Text>
        <Text style={selStyles.term}>3. <Text style={selStyles.termBold}>100% advance payment</Text> is required to confirm orders.</Text>
        <Text style={selStyles.term}>4. <Text style={selStyles.termBold}>Freight &amp; Unloading charges</Text> will be applicable as per actuals.</Text>
        <Text style={selStyles.term}>5. <Text style={selStyles.termBold}>Delivery timelines</Text> are subject to the <Text style={selStyles.termBold}>manufacturer's schedule</Text>.</Text>
        <Text style={selStyles.term}>6. <Text style={selStyles.termBold}>Rates are valid for 5 Days</Text>, unless stated otherwise in writing.</Text>
      </View>

      {/* Contact strip */}
      <View style={{ marginTop: 18 }}>
        <View style={selStyles.ruleThin} />
        <View style={{ flexDirection: "row", gap: 12, marginVertical: 2 }}>
          <View style={selStyles.contactCell}>
            <Text style={selStyles.contactText}><Text style={{ fontWeight: "700" }}>E-MAIL:</Text> buildconhouse@gmail.com</Text>
          </View>
          <View style={selStyles.contactCell}>
            <Text style={selStyles.contactText}><Text style={{ fontWeight: "700" }}>MOBILE:</Text> +91 99099 06652</Text>
          </View>
        </View>
        <View style={selStyles.ruleThin} />
      </View>

      <TilesProductPicker
        open={pickerRow !== null}
        onClose={() => setPickerRow(null)}
        onPick={(product) => { if (pickerRow) doc.applyProduct(pickerRow, product); }}
      />
    </View>
  );
}

const selStyles = StyleSheet.create({
  paper: {
    width: PAPER_W, backgroundColor: "#fff", paddingHorizontal: 30, paddingVertical: 26,
    borderRadius: 2,
    ...(Platform.OS === "web" ? { boxShadow: "0 10px 34px rgba(20,20,20,0.16)" } as any : {}),
  },
  address: { fontSize: 11.5, color: "#3B3B3B", marginTop: 6 },
  ruleThick: { height: 2.5, backgroundColor: "#111", marginTop: 8 },
  ruleThin: { height: 1.2, backgroundColor: "#111", marginTop: 3 },
  headerRow: { flexDirection: "row", gap: 28, marginTop: 16, zIndex: 60 },
  fieldRow: { flexDirection: "row", alignItems: "flex-end", gap: 6 },
  fieldLabel: { fontSize: 12.5, fontWeight: "700", color: "#111", paddingBottom: 3 },
  fieldValueWrap: { flex: 1, borderBottomWidth: 1, borderColor: "#333", zIndex: 60 },
  table: { marginTop: 20, borderWidth: 1.4, borderColor: "#111" },
  tr: { flexDirection: "row", borderTopWidth: 1, borderColor: "#111", alignItems: "stretch" },
  td: {
    borderRightWidth: 1, borderColor: "#111",
    alignItems: "center", justifyContent: "center", paddingHorizontal: 4, paddingVertical: 4,
  },
  th: { fontSize: 12, fontWeight: "700", color: "#111", textAlign: "center" },
  cellText: { fontSize: 12.5, color: "#111" },
  rateSuffix: { fontSize: 9.5, fontWeight: "700", color: "#E00000", marginTop: 2 },
  termsTitle: { fontSize: 15, fontWeight: "700", color: "#2B2B2B", marginTop: 18, marginBottom: 7 },
  term: { fontSize: 11, color: "#4A4A4A", lineHeight: 17 },
  termBold: { fontWeight: "700", color: "#333" },
  contactCell: {
    flex: 1, backgroundColor: HEAD_GREY, paddingVertical: 6, alignItems: "center", justifyContent: "center",
  },
  contactText: { fontSize: 11.5, color: "#111" },
});

// ---------------------------------------------------------------------------
// QUOTATION paper — replica of the light-blue bordered sheet
// ---------------------------------------------------------------------------
const QUO_COLS = [12, 33, 26, 24, 15, 14.5, 14.5, 12.5, 12.5, 16];

function QuotationPaper(doc: ReturnType<typeof useTilesDoc>) {
  const [pickerRow, setPickerRow] = useState<string | null>(null);
  const flex = (index: number) => ({ flex: QUO_COLS[index] });
  const totals = useMemo(() => {
    let boxes = 0;
    let subtotal = 0;
    for (const row of doc.rows) {
      if (!row.productId) continue;
      boxes += num(row.totalBox);
      subtotal += row.totalEdited && num(row.total) > 0 ? num(row.total) : num(row.rateBox) * num(row.totalBox);
    }
    return { boxes, subtotal };
  }, [doc.rows]);

  const headLabels = ["SR.", "PRODUCT NAME", "PHOTO", "Area", "Size", "RATE PER\nSQFT", "RATE PER\nBOX", "TOTAL\nBOX", "PCS|BOX", "TOTAL"];
  return (
    <View style={quoStyles.paper}>
      {/* Brand + title */}
      <View style={{ flexDirection: "row", alignItems: "flex-start" }}>
        <View style={{ flex: 1 }} />
        <BuildConLogo height={52} />
        <View style={{ flex: 1, alignItems: "flex-end" }}>
          <Text style={quoStyles.title}>Quotation</Text>
        </View>
      </View>

      {/* Customer block */}
      <View style={{ flexDirection: "row", marginTop: 10, zIndex: 60 }}>
        <View style={{ flex: 1.7, gap: 2 }}>
          <View style={[quoStyles.hRow, { zIndex: 400 }]}>
            <Text style={quoStyles.hLabel}>NAME :</Text>
            <CustomerNameField
              value={doc.header.customerName}
              onChangeText={(t) => doc.setHeaderField("customerName", t)}
              customers={doc.customers}
              customerId={doc.customerId}
              onPickCustomer={doc.pickCustomer}
              inputStyle={quoStyles.hInput}
              testID="tiles-customer-name"
            />
          </View>
          <View style={quoStyles.hRow}>
            <Text style={quoStyles.hLabel}>MO :</Text>
            <View style={{ flex: 1 }}>
              <CellInput value={doc.header.phone} onChangeText={(t) => doc.setHeaderField("phone", t)} align="left" serif bold style={quoStyles.hInput} testID="tiles-phone" />
            </View>
          </View>
          <View style={quoStyles.hRow}>
            <Text style={quoStyles.hLabel}>REF :</Text>
            <View style={{ flex: 1 }}>
              <CellInput value={doc.header.reference} onChangeText={(t) => doc.setHeaderField("reference", t)} align="left" serif bold style={quoStyles.hInput} testID="tiles-reference" />
            </View>
          </View>
          <View style={quoStyles.hRow}>
            <Text style={quoStyles.hLabel}>ATTENDED BY :</Text>
            <View style={{ flex: 1 }}>
              <CellInput value={doc.header.attendedBy} onChangeText={(t) => doc.setHeaderField("attendedBy", t)} align="left" serif bold style={quoStyles.hInput} testID="tiles-attended" />
            </View>
          </View>
          <View style={quoStyles.hRow}>
            <Text style={quoStyles.hLabel}>ADDRESS :</Text>
            <View style={{ flex: 1 }}>
              <CellInput value={doc.header.address} onChangeText={(t) => doc.setHeaderField("address", t)} align="left" serif bold style={quoStyles.hInput} testID="tiles-address" />
            </View>
          </View>
        </View>
        <View style={{ flex: 1, gap: 2, paddingLeft: 24 }}>
          <View style={quoStyles.hRow}>
            <Text style={[quoStyles.hLabel, { width: 108, textAlign: "left" }]}>QUOTATION NO:</Text>
            <View style={{ flex: 1 }}>
              <CellInput value={doc.header.docNumber} onChangeText={(t) => doc.setHeaderField("docNumber", t)} align="left" serif bold style={quoStyles.hInput} testID="tiles-doc-number" />
            </View>
          </View>
          <View style={quoStyles.hRow}>
            <Text style={[quoStyles.hLabel, { width: 108, textAlign: "left" }]}>DATE:</Text>
            <View style={{ flex: 1 }}>
              <CellInput value={doc.header.docDate} onChangeText={(t) => doc.setHeaderField("docDate", t)} align="left" serif bold style={quoStyles.hInput} testID="tiles-date" />
            </View>
          </View>
          <View style={quoStyles.hRow}>
            <Text style={[quoStyles.hLabel, { width: 108, textAlign: "left" }]}>PREPARED BY:</Text>
            <View style={{ flex: 1 }}>
              <CellInput value={doc.header.preparedBy} onChangeText={(t) => doc.setHeaderField("preparedBy", t)} align="left" serif bold style={quoStyles.hInput} testID="tiles-prepared" />
            </View>
          </View>
        </View>
      </View>

      {/* Product grid */}
      <View style={quoStyles.table}>
        <View style={[quoStyles.tr, { minHeight: 34 }]}>
          {headLabels.map((h, i) => (
            <View key={h} style={[quoStyles.td, flex(i), i === headLabels.length - 1 && { borderRightWidth: 0 }]}>
              <Text style={[quoStyles.th, i === 5 && { color: "#E00000" }]}>{h}</Text>
            </View>
          ))}
        </View>
        {doc.rows.map((row, index) => (
          <View key={row.key} style={[quoStyles.tr, { minHeight: 76 }]}>
            <View style={[quoStyles.td, flex(0)]}><Text style={quoStyles.cellText}>{index + 1}</Text></View>
            <View style={[quoStyles.td, flex(1)]}>
              <ProductCell
                row={row}
                bold
                onOpenPicker={() => setPickerRow(row.key)}
                onChangeName={(t) => doc.updateRow(row.key, { name: t })}
                testID={`tiles-product-${index}`}
              />
            </View>
            <View style={[quoStyles.td, flex(2), { padding: 2 }]}>
              {row.image ? <Image source={{ uri: row.image }} resizeMode="contain" style={{ width: "100%", height: 68 }} /> : null}
            </View>
            <View style={[quoStyles.td, flex(3)]}>
              <CellInput value={row.area} onChangeText={(t) => doc.updateRow(row.key, { area: t })} placeholder="Area" multiline testID={`tiles-area-${index}`} />
            </View>
            <View style={[quoStyles.td, flex(4)]}>
              <CellInput value={row.size} onChangeText={(t) => doc.updateRow(row.key, { size: t })} bold testID={`tiles-size-${index}`} />
            </View>
            <View style={[quoStyles.td, flex(5)]}>
              <CellInput value={row.rateSqft} onChangeText={(t) => doc.updateRow(row.key, { rateSqft: t })} red bold testID={`tiles-rate-sqft-${index}`} />
            </View>
            <View style={[quoStyles.td, flex(6)]}>
              <CellInput value={row.rateBox} onChangeText={(t) => doc.updateRow(row.key, { rateBox: t })} testID={`tiles-rate-box-${index}`} />
            </View>
            <View style={[quoStyles.td, flex(7)]}>
              <CellInput value={row.totalBox} onChangeText={(t) => doc.updateRow(row.key, { totalBox: t })} bold testID={`tiles-total-box-${index}`} />
            </View>
            <View style={[quoStyles.td, flex(8)]}>
              <CellInput value={row.pcsBox} onChangeText={(t) => doc.updateRow(row.key, { pcsBox: t })} bold testID={`tiles-pcs-box-${index}`} />
            </View>
            <View style={[quoStyles.td, flex(9), { borderRightWidth: 0 }]}>
              <CellInput value={row.total} onChangeText={(t) => doc.updateRow(row.key, { total: t })} testID={`tiles-total-${index}`} />
            </View>
            <RowSideControls
              isLast={index === doc.rows.length - 1}
              canAdd={doc.rows.length < MAX_ROWS}
              onAdd={doc.addRow}
              onRemove={() => doc.removeRow(row.key)}
              showRemove={doc.rows.length > 1}
            />
          </View>
        ))}
      </View>

      {/* Totals stack */}
      <View style={{ alignItems: "flex-end", marginTop: 8 }}>
        <View style={{ width: 250 }}>
          <View style={[quoStyles.sumRow, { alignSelf: "flex-start", borderWidth: 1, width: 150 }]}>
            <Text style={quoStyles.sumText}>TOTAL BOX : {totals.boxes ? `${Math.round(totals.boxes * 100) / 100}` : "0"}</Text>
          </View>
          <View style={{ flexDirection: "row", borderWidth: 1, borderColor: "#111", marginTop: -1 }}>
            <View style={[quoStyles.sumCell, { flex: 1.5 }]}><Text style={quoStyles.sumText}>SUBTOTAL</Text></View>
            <View style={[quoStyles.sumCell, { flex: 1, borderRightWidth: 0 }]}><Text style={quoStyles.sumText}>{money(totals.subtotal)}</Text></View>
          </View>
          <View style={{ flexDirection: "row", borderWidth: 1, borderColor: "#111", marginTop: -1 }}>
            <View style={[quoStyles.sumCell, { flex: 1.5 }]}><Text style={quoStyles.sumText}>TRANSPORTATION</Text></View>
            <View style={[quoStyles.sumCell, { flex: 1, borderRightWidth: 0 }]}><Text style={quoStyles.sumText}>EXTRA</Text></View>
          </View>
          <View style={{ flexDirection: "row", borderWidth: 1, borderColor: "#111", marginTop: -1 }}>
            <View style={[quoStyles.sumCell, { flex: 1.5 }]}><Text style={[quoStyles.sumText, { color: "#E00000" }]}>TOTAL QUOTE</Text></View>
            <View style={[quoStyles.sumCell, { flex: 1, borderRightWidth: 0 }]}><Text style={[quoStyles.sumText, { color: "#E00000" }]}>{money(totals.subtotal)}</Text></View>
          </View>
        </View>
      </View>

      {/* Notes + terms + blue footer */}
      <View style={{ alignItems: "center", marginTop: 14, gap: 2 }}>
        <Text style={quoStyles.noteRed}>☺ LABOUR COST EXTRA</Text>
        <Text style={quoStyles.noteHead}>☺ TERMS&amp;CONDITION :</Text>
        <View style={{ gap: 1, marginTop: 3 }}>
          {[
            "•Above given rate are including GST @18%.",
            "•Freight & unloading charges will be extra as applicable.",
            "•Payment - 100% Advance.",
            "•All orders / Deliveries are subject to material availability.",
            "•price tends to change in case of changes in govt. levy.",
            "•cheque should be written in favour of BUILDCON HOUSE.",
            "•After confirmation of P.O. material will be delivered within 15 days.",
            "•RATE VALID FOR 5 DAYS.",
          ].map((line) => <Text key={line} style={quoStyles.termLine}>{line}</Text>)}
        </View>
        <View style={{ marginTop: 10, gap: 1, alignItems: "center" }}>
          <Text style={quoStyles.blueLine}>ADDRESS :- Before Gujarat housing, Nr.katariya motors, 2nd 150ft ring road, Rajkot-360005</Text>
          <Text style={quoStyles.blueLine}>Mail :buildconhouse@gmail.com</Text>
          <Text style={quoStyles.blueLine}>Mo:+91 99099 06652</Text>
        </View>
      </View>

      <TilesProductPicker
        open={pickerRow !== null}
        onClose={() => setPickerRow(null)}
        onPick={(product) => { if (pickerRow) doc.applyProduct(pickerRow, product); }}
      />
    </View>
  );
}

const quoStyles = StyleSheet.create({
  paper: {
    width: PAPER_W, backgroundColor: SHEET_BLUE, borderWidth: 2, borderColor: "#111",
    paddingHorizontal: 26, paddingVertical: 20,
    ...(Platform.OS === "web" ? { boxShadow: "0 10px 34px rgba(20,20,20,0.16)" } as any : {}),
  },
  title: { fontFamily: SERIF, fontSize: 30, fontWeight: "700", color: "#111" },
  hRow: { flexDirection: "row", alignItems: "center", gap: 6, zIndex: 60 },
  hLabel: { fontFamily: SERIF, fontSize: 12, fontWeight: "700", color: "#111", width: 116, textAlign: "right" },
  hInput: { fontFamily: SERIF, fontSize: 12, fontWeight: "700", paddingVertical: 1 },
  table: { marginTop: 12, borderWidth: 1.4, borderColor: "#111" },
  tr: { flexDirection: "row", borderTopWidth: 1, borderColor: "#111", alignItems: "stretch", backgroundColor: "#fff" },
  td: {
    borderRightWidth: 1, borderColor: "#111",
    alignItems: "center", justifyContent: "center", paddingHorizontal: 3, paddingVertical: 3,
  },
  th: { fontFamily: SERIF, fontSize: 11, fontWeight: "700", fontStyle: "italic", color: "#111", textAlign: "center" },
  cellText: { fontSize: 12, color: "#111" },
  sumRow: { borderColor: "#111", backgroundColor: "#fff", paddingVertical: 4, alignItems: "center" },
  sumCell: {
    borderRightWidth: 1, borderColor: "#111", backgroundColor: "#fff",
    paddingVertical: 4, alignItems: "center", justifyContent: "center",
  },
  sumText: { fontSize: 11.5, fontWeight: "700", color: "#111", fontVariant: ["tabular-nums"] },
  noteRed: { fontSize: 11.5, fontWeight: "700", color: "#E00000" },
  noteHead: { fontSize: 11.5, fontWeight: "700", color: "#111", marginTop: 2 },
  termLine: { fontFamily: SERIF, fontSize: 10.5, color: "#111", textAlign: "center" },
  blueLine: { fontFamily: SERIF, fontSize: 10.5, fontWeight: "700", color: "#2E75B6", textAlign: "center" },
});

// ---------------------------------------------------------------------------
// Page shell — topbar with the action buttons + scrollable paper
// ---------------------------------------------------------------------------
export function TilesDocBuilder({ docType }: { docType: TilesDocType }) {
  const router = useRouter();
  const doc = useTilesDoc(docType);
  const isSelection = docType === "tiles_selection";
  const title = isSelection ? "Tiles Selection" : "Tiles Quotation";

  const saveLabel = doc.saveState === "saving" ? "Saving…"
    : doc.saveState === "saved" ? "Saved"
    : doc.saveState === "error" ? "Retry save" : "Save";

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surfaceSecondary }} edges={["top"]}>
      <View style={shellStyles.topbar}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}>
          <Pressable onPress={() => router.back()} hitSlop={10} style={shellStyles.backBtn} testID="tiles-back">
            <Feather name="chevron-left" size={20} color={colors.onSurface} />
          </Pressable>
          <View style={{ minWidth: 0, flex: 1 }}>
            <Text style={type.overline}>Ground Floor · Tiles</Text>
            <Text style={[type.titleMd, { marginTop: 1 }]} numberOfLines={1}>
              {title}{doc.docNumberServer ? `  ·  ${doc.docNumberServer}` : ""}
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
          <ActionBtn
            label={saveLabel}
            icon="save"
            onPress={doc.save}
            loading={doc.busy === "save"}
            testID="tiles-save"
          />
          <ActionBtn
            label={isSelection ? "Selection" : "Quotation"}
            icon="file-text"
            primary
            onPress={doc.generatePdf}
            loading={doc.busy === "pdf"}
            testID="tiles-generate-pdf"
          />
          {isSelection ? (
            <ActionBtn label="Print" icon="printer" onPress={doc.print} loading={doc.busy === "print"} testID="tiles-print" />
          ) : (
            <ActionBtn label="Place Order" icon="shopping-cart" onPress={doc.placeOrder} loading={doc.busy === "order"} testID="tiles-place-order" />
          )}
        </View>
      </View>

      {doc.loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.brand} />
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ paddingVertical: spacing.lg, paddingBottom: 80 }}>
          <ScrollView
            horizontal
            contentContainerStyle={{ flexGrow: 1, justifyContent: "center", paddingHorizontal: spacing.lg, paddingRight: 64 }}
            showsHorizontalScrollIndicator
          >
            {isSelection ? <SelectionPaper {...doc} /> : <QuotationPaper {...doc} />}
          </ScrollView>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function ActionBtn({
  label, icon, onPress, primary, loading, testID,
}: {
  label: string; icon: any; onPress: () => void; primary?: boolean; loading?: boolean; testID?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={loading}
      testID={testID}
      style={({ pressed }) => [
        shellStyles.actionBtn,
        primary && { backgroundColor: colors.brand, borderColor: colors.brand },
        { opacity: pressed || loading ? 0.75 : 1 },
      ]}
    >
      {loading
        ? <ActivityIndicator size="small" color={primary ? "#fff" : colors.brand} />
        : <Feather name={icon} size={13} color={primary ? "#fff" : colors.onSurface} />}
      <Text style={[shellStyles.actionLabel, primary && { color: "#fff" }]}>{label}</Text>
    </Pressable>
  );
}

const shellStyles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: 10, gap: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  backBtn: {
    width: 44, height: 44, borderRadius: radius.md, alignItems: "center", justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surface,
  },
  actionBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 12, height: 44, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  actionLabel: { fontSize: 13, fontFamily: type.titleMd.fontFamily, fontWeight: "600", color: colors.onSurface },
});
