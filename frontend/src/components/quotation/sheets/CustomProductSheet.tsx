// CustomProductSheet — quick-add sheet for a one-off custom product.
// Two modes controlled by a checkbox:
//   [ ] Save as catalogue product   → persists via /products/custom (is_custom=true)
//   [x] Save                        → available in future quotations, searchable
//   [ ] Unsaved                     → lives ONLY inside this quotation
// In both cases a line is inserted into the current room.
// -----------------------------------------------------------------------------
import { Feather } from "@expo/vector-icons";
import { useEffect, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { colors, radius, shadow, spacing } from "@/src/theme/tokens";
import { useBuilder } from "../context/BuilderContext";
import type { Product } from "../helpers/types";

export function CustomProductSheet() {
  const b = useBuilder();
  const open = b.customProductSheetOpen;

  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [brandId, setBrandId] = useState<string | null>(null);
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [price, setPrice] = useState("");
  const [mrp, setMrp] = useState("");
  const [finish, setFinish] = useState("");
  const [description, setDescription] = useState("");
  const [saveToCatalog, setSaveToCatalog] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(""); setSku(""); setPrice(""); setMrp(""); setFinish(""); setDescription("");
    setBrandId(b.selectedBrandId ?? b.brands[0]?.id ?? null);
    setCategoryId(b.selectedCategoryId ?? b.categories[0]?.id ?? null);
    setSaveToCatalog(true);
  }, [open, b.selectedBrandId, b.selectedCategoryId, b.brands, b.categories]);

  const commit = async () => {
    if (!name.trim()) { toast.error("Name is required"); return; }
    if (!brandId || !categoryId) { toast.error("Pick a brand and category"); return; }
    const p = Number(price) || 0;
    if (p <= 0) { toast.error("Enter a valid price"); return; }

    setBusy(true);
    try {
      if (saveToCatalog) {
        // Persist to catalog with is_custom=true so it's searchable in future.
        const prod = await api.post<Product>("/products/custom", {
          name: name.trim(),
          sku: sku.trim() || `CUSTOM-${Date.now().toString(36).toUpperCase()}`,
          brand_id: brandId, category_id: categoryId,
          price: p, mrp: Number(mrp) || p,
          finish: finish.trim() || null, description: description.trim() || null,
          is_custom: true,
        });
        b.addFromProduct(prod);
        toast.success(`Added · ${prod.sku}`);
      } else {
        // In-quotation only. Fabricate a synthetic "product" object.
        const localId = `custom-${Date.now()}`;
        const prod: Product = {
          id: localId,
          name: name.trim(),
          sku: sku.trim() || `INLINE-${Date.now().toString(36).toUpperCase()}`,
          brand_id: brandId, category_id: categoryId,
          price: p, mrp: Number(mrp) || p,
          finish: finish.trim() || null,
          images: [], variants: [],
        } as Product;
        b.addFromProduct(prod);
        toast.success("Added inline");
      }
      b.setCustomProductSheetOpen(false);
    } catch (e: any) {
      toast.error(e?.detail || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={() => b.setCustomProductSheetOpen(false)}>
      <Pressable style={styles.backdrop} onPress={() => b.setCustomProductSheetOpen(false)}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <View style={styles.head}>
            <View style={{ flex: 1 }}>
              <Text style={styles.title}>Custom product</Text>
              <Text style={styles.subtitle}>Add a one-off item — optionally save it to the catalog.</Text>
            </View>
            <Pressable onPress={() => b.setCustomProductSheetOpen(false)} style={styles.close} hitSlop={6}>
              <Feather name="x" size={16} color={colors.onSurface} />
            </Pressable>
          </View>

          <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: 12 }}>
            <Field label="Product name *">
              <TextInput value={name} onChangeText={setName} placeholder="e.g. Custom stone-cladding sink" style={styles.input} testID="cp-name" />
            </Field>
            <Field label="SKU (optional — auto if blank)">
              <TextInput value={sku} onChangeText={setSku} placeholder="e.g. CUSTOM-STONE-SINK" style={styles.input} autoCapitalize="characters" />
            </Field>

            <View style={styles.grid}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Brand *</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingVertical: 2 }}>
                  {b.brands.map((br) => {
                    const on = brandId === br.id;
                    return (
                      <Pressable key={br.id} onPress={() => setBrandId(br.id)} style={[styles.pill, on && styles.pillActive]}>
                        <Text style={[styles.pillLabel, on && styles.pillLabelActive]}>{br.name}</Text>
                      </Pressable>
                    );
                  })}
                </ScrollView>
              </View>
            </View>

            <View>
              <Text style={styles.label}>Category *</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingVertical: 2 }}>
                {b.categories.map((c) => {
                  const on = categoryId === c.id;
                  return (
                    <Pressable key={c.id} onPress={() => setCategoryId(c.id)} style={[styles.pill, on && styles.pillActive]}>
                      <Text style={[styles.pillLabel, on && styles.pillLabelActive]}>{c.name}</Text>
                    </Pressable>
                  );
                })}
              </ScrollView>
            </View>

            <View style={styles.grid}>
              <Field label="Price *" flex={1}>
                <TextInput value={price} onChangeText={setPrice} placeholder="0" keyboardType="numeric" style={styles.input} testID="cp-price" />
              </Field>
              <Field label="MRP" flex={1}>
                <TextInput value={mrp} onChangeText={setMrp} placeholder="0" keyboardType="numeric" style={styles.input} />
              </Field>
              <Field label="Finish" flex={1.2}>
                <TextInput value={finish} onChangeText={setFinish} placeholder="Chrome, Matt Black …" style={styles.input} />
              </Field>
            </View>

            <Field label="Description">
              <TextInput
                value={description} onChangeText={setDescription}
                placeholder="Optional — shown on quotation & PDF"
                multiline style={[styles.input, { minHeight: 60 }]}
              />
            </Field>

            <Pressable onPress={() => setSaveToCatalog((v) => !v)} style={styles.checkbox} testID="cp-save">
              <View style={[styles.checkboxBox, saveToCatalog && styles.checkboxBoxOn]}>
                {saveToCatalog ? <Feather name="check" size={11} color={colors.onBrand} /> : null}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.checkboxLabel}>Save as catalogue product</Text>
                <Text style={styles.checkboxHint}>
                  {saveToCatalog
                    ? "Appears in future quotations, searchable, editable."
                    : "Lives only inside this quotation — won’t pollute the catalog."}
                </Text>
              </View>
            </Pressable>
          </ScrollView>

          <View style={styles.footer}>
            <Pressable onPress={() => b.setCustomProductSheetOpen(false)} style={styles.secondary}>
              <Text style={styles.secondaryLabel}>Cancel</Text>
            </Pressable>
            <Pressable onPress={commit} style={[styles.primary, busy && { opacity: 0.6 }]} disabled={busy} testID="cp-commit">
              <Feather name={saveToCatalog ? "save" : "plus"} size={13} color={colors.onBrand} />
              <Text style={styles.primaryLabel}>{saveToCatalog ? "Save & add" : "Add inline"}</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function Field({ label, children, flex }: { label: string; children: React.ReactNode; flex?: number }) {
  return (
    <View style={{ flex, gap: 4 }}>
      <Text style={styles.label}>{label}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(9,9,11,0.55)", alignItems: "center", justifyContent: "center", padding: 24 },
  sheet: { width: "100%", maxWidth: 640, maxHeight: "92%", backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, overflow: "hidden", ...shadow.strong },

  head: { flexDirection: "row", padding: spacing.lg, alignItems: "flex-start", gap: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.2 },
  subtitle: { fontSize: 12, color: colors.onSurfaceMuted, marginTop: 2 },
  close: { width: 30, height: 30, borderRadius: radius.md, alignItems: "center", justifyContent: "center", borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },

  label: { fontSize: 11, fontWeight: "700", color: colors.onSurfaceMuted, letterSpacing: 1.1, textTransform: "uppercase", marginBottom: 4 },
  input: {
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: 10, paddingVertical: 8, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },

  grid: { flexDirection: "row", gap: 10 },

  pill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary },
  pillActive: { backgroundColor: colors.brand },
  pillLabel: { fontSize: 11, fontWeight: "600", color: colors.onSurfaceSecondary },
  pillLabelActive: { color: colors.onBrand },

  checkbox: { flexDirection: "row", alignItems: "flex-start", gap: 8, padding: 10, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary },
  checkboxBox: { width: 18, height: 18, borderRadius: 4, borderWidth: 1.5, borderColor: colors.borderStrong, alignItems: "center", justifyContent: "center", marginTop: 1 },
  checkboxBoxOn: { backgroundColor: colors.brand, borderColor: colors.brand },
  checkboxLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  checkboxHint: { fontSize: 11, color: colors.onSurfaceMuted, marginTop: 2 },

  footer: { flexDirection: "row", justifyContent: "flex-end", gap: 8, padding: spacing.lg, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surface },
  secondary: { paddingHorizontal: 14, paddingVertical: 9, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  secondaryLabel: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  primary: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.md, backgroundColor: colors.brand },
  primaryLabel: { fontSize: 12, fontWeight: "700", color: colors.onBrand, letterSpacing: 0.2 },
});
