// Place Order — Review & Confirm
// -----------------------------------------------------------------------------
// Renders brand-grouped preview cards for an approved quotation. Each card shows
// the items that will land on a single Purchase Order, with an editable
// supplier assignment and optional internal notes.
//
// Confirm → POST /quotations/:id/place-order/confirm → server creates one PO
// per brand, marks the quotation `ordered`, then we route to /purchase-orders.
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button, Card, IconButton } from "@/src/components/ui";
import { toast } from "@/src/components/Toast";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type PreviewItem = {
  line_id: string;
  product_id: string;
  sku: string;
  name: string;
  room?: string | null;
  qty: number;
  unit_cost: number;
};

type BrandCard = {
  brand_id: string | null;
  brand_name: string;
  items: PreviewItem[];
  subtotal: number;
  item_count: number;
  default_supplier?: { id: string; name: string } | null;
};

type Preview = {
  quotation_id: string;
  quotation_number: string;
  customer_id: string;
  customer_name: string;
  brands: BrandCard[];
  total_value: number;
};

type Supplier = { id: string; name: string; brand_id?: string | null; brand_name?: string | null };

export default function PlaceOrderReview() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [preview, setPreview] = useState<Preview | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierByBrand, setSupplierByBrand] = useState<Record<string, string>>({});
  const [notesByBrand, setNotesByBrand] = useState<Record<string, string>>({});
  const [expected, setExpected] = useState<string>("");
  const [projectName, setProjectName] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [p, s] = await Promise.all([
          api.get<Preview>(`/quotations/${id}/place-order/preview`),
          api.get<Supplier[]>("/suppliers"),
        ]);
        setPreview(p);
        setSuppliers(s);
        // pre-fill defaults
        const defaults: Record<string, string> = {};
        for (const b of p.brands) {
          if (b.default_supplier && b.brand_id) defaults[b.brand_id] = b.default_supplier.id;
        }
        setSupplierByBrand(defaults);
      } catch (e: any) {
        setError(e?.detail || "Failed to load preview");
      }
    })();
  }, [id]);

  const supplierOptionsFor = useCallback(
    (brand_id: string | null): Supplier[] => {
      if (!brand_id) return suppliers;
      const matched = suppliers.filter((s) => s.brand_id === brand_id);
      return matched.length ? matched : suppliers;
    },
    [suppliers],
  );

  const confirm = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const res = await api.post<{ purchase_orders: { id: string }[]; count: number }>(
        `/quotations/${id}/place-order/confirm`,
        {
          supplier_by_brand: supplierByBrand,
          notes_by_brand: notesByBrand,
          expected_delivery_at: expected || null,
          project_name: projectName || null,
        },
      );
      toast.success(`Order placed · ${res.count} Purchase Orders created`);
      router.replace("/(admin)/purchases" as any);
    } catch (e: any) {
      toast.error(e?.detail || "Could not place order");
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }}>
        <View style={{ padding: spacing.xxl, alignItems: "center", gap: spacing.md }}>
          <Feather name="alert-triangle" size={30} color={colors.warning} />
          <Text style={type.titleMd}>{error}</Text>
          <Button label="Back to quotation" onPress={() => router.back()} />
        </View>
      </SafeAreaView>
    );
  }

  if (!preview) {
    return <View style={{ flex: 1, backgroundColor: colors.surface }} />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.topbar}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Back</Text>
        </Pressable>
        <View style={{ alignItems: "center" }}>
          <Text style={{ fontSize: 12, fontWeight: "500", color: colors.onSurfaceMuted }}>Review Order</Text>
          <Text style={[type.mono, { fontSize: 12 }]}>{preview.quotation_number}</Text>
        </View>
        <View style={{ width: 60 }} />
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        keyboardVerticalOffset={Platform.OS === "ios" ? 0 : 24}
      >
        <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl }} keyboardShouldPersistTaps="handled">
        {/* Header summary */}
        <View>
          <Text style={type.displayLg}>{preview.customer_name}</Text>
          <Text style={[type.bodyMuted, { marginTop: 4 }]}>
            {preview.brands.length} brand{preview.brands.length !== 1 ? "s" : ""} · {preview.brands.reduce((s, b) => s + b.item_count, 0)} items · {money(preview.total_value)}
          </Text>
        </View>

        {/* Project / delivery */}
        <Card>
          <Text style={type.overline}>Order details</Text>
          <View style={{ marginTop: spacing.md, gap: spacing.md }}>
            <View>
              <Text style={styles.label}>Project name (optional)</Text>
              <TextInput
                value={projectName}
                onChangeText={setProjectName}
                placeholder="e.g. Sea View Villa – Alibaug"
                placeholderTextColor={colors.onSurfaceMuted}
                style={styles.textInput}
                testID="project-name"
              />
            </View>
            <View>
              <Text style={styles.label}>Expected delivery (optional)</Text>
              <TextInput
                value={expected}
                onChangeText={setExpected}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={colors.onSurfaceMuted}
                style={styles.textInput}
                testID="expected-delivery"
              />
            </View>
          </View>
        </Card>

        {/* Brand cards */}
        {preview.brands.map((b) => {
          const brandKey = b.brand_id || "__unassigned__";
          const options = supplierOptionsFor(b.brand_id);
          const selectedSupplier = supplierByBrand[brandKey];
          return (
            <Card key={brandKey}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <View>
                  <Text style={type.overline}>Purchase Order · {b.brand_name}</Text>
                  <Text style={{ fontSize: 18, fontWeight: "700", color: colors.onSurface, marginTop: 4 }}>{b.brand_name}</Text>
                  <Text style={type.caption}>{b.item_count} items</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={[type.caption, { color: colors.onSurfaceMuted }]}>Subtotal</Text>
                  <Text style={[type.mono, { fontSize: 15, fontWeight: "700", marginTop: 2 }]} numberOfLines={1}>{money(b.subtotal)}</Text>
                </View>
              </View>

              <View style={styles.itemsBox}>
                {b.items.slice(0, 6).map((it) => (
                  <View key={it.line_id} style={styles.itemRow}>
                    <Text style={[type.mono, { fontSize: 11, width: 90, color: colors.onSurfaceMuted }]}>{it.sku}</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: "500" }} numberOfLines={1}>{it.name}</Text>
                      {it.room ? <Text style={type.caption}>{it.room}</Text> : null}
                    </View>
                    <Text style={[type.mono, { fontSize: 11, width: 50, textAlign: "right" }]}>{it.qty} nos</Text>
                    <Text style={[type.mono, { fontSize: 12, width: 80, textAlign: "right", fontWeight: "600" }]} numberOfLines={1}>{money(it.unit_cost * it.qty)}</Text>
                  </View>
                ))}
                {b.items.length > 6 ? (
                  <Text style={[type.caption, { textAlign: "center", padding: 6, opacity: 0.7 }]}>
                    +{b.items.length - 6} more items…
                  </Text>
                ) : null}
              </View>

              <View style={{ gap: spacing.md, marginTop: spacing.md }}>
                <View>
                  <Text style={styles.label}>Supplier</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
                    {options.length === 0 ? (
                      <Text style={type.caption}>No suppliers configured — add one from Settings</Text>
                    ) : (
                      options.map((s) => {
                        const on = selectedSupplier === s.id;
                        return (
                          <Pressable
                            key={s.id}
                            testID={`supplier-${s.id}`}
                            onPress={() => setSupplierByBrand((prev) => ({ ...prev, [brandKey]: s.id }))}
                            style={[styles.supplierChip, on && { borderColor: colors.brand, backgroundColor: colors.brand }]}
                          >
                            <Feather name="truck" size={12} color={on ? colors.onBrand : colors.onSurfaceMuted} />
                            <Text style={{ fontSize: 12, fontWeight: "600", color: on ? colors.onBrand : colors.onSurface }}>{s.name}</Text>
                          </Pressable>
                        );
                      })
                    )}
                  </ScrollView>
                </View>
                <View>
                  <Text style={styles.label}>Internal notes (optional)</Text>
                  <TextInput
                    value={notesByBrand[brandKey] || ""}
                    onChangeText={(v) => setNotesByBrand((prev) => ({ ...prev, [brandKey]: v }))}
                    placeholder="e.g. Priority order, deliver by month-end"
                    placeholderTextColor={colors.onSurfaceMuted}
                    style={[styles.textInput, { minHeight: 56 }]}
                    multiline
                    testID={`notes-${brandKey}`}
                  />
                </View>
              </View>
            </Card>
          );
        })}

        {/* Confirm bar */}
        <View style={styles.confirmBar}>
          <View style={{ flex: 1 }}>
            <Text style={type.caption}>Total order value</Text>
            <Text style={{ fontSize: 20, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"] }} numberOfLines={1}>
              {money(preview.total_value)}
            </Text>
          </View>
          <Button label="Cancel" variant="ghost" onPress={() => router.back()} />
          <Button
            label={`Generate ${preview.brands.length} PO${preview.brands.length !== 1 ? "s" : ""}`}
            icon="check"
            onPress={confirm}
            loading={busy}
            testID="confirm-place-order"
          />
        </View>
      </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  label: { fontSize: 11, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.6, color: colors.onSurfaceMuted, marginBottom: 4 },
  textInput: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    padding: 10, fontSize: 14, backgroundColor: colors.surface, color: colors.onSurface,
  },
  itemsBox: {
    marginTop: spacing.md,
    borderRadius: radius.md, backgroundColor: colors.surfaceTertiary,
    padding: 4, gap: 2,
  },
  itemRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: 8, paddingVertical: 6, borderRadius: radius.sm,
    backgroundColor: colors.surfaceSecondary,
  },
  supplierChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: 12, height: 34, borderRadius: 999,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  confirmBar: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    padding: spacing.md, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
});
