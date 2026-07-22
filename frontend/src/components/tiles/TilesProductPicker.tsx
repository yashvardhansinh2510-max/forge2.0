// TilesProductPicker — text-only product search for the tiles document
// builders. SKU + product-name search against the existing catalog API,
// deliberately WITHOUT thumbnails (the printed document carries the photo;
// the picker stays fast and scannable). Keyboard friendly: type → ↑/↓ to
// highlight → Enter to add; Esc closes.
import { Feather } from "@expo/vector-icons";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator, FlatList, Modal, Platform, Pressable, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import type { Product } from "@/src/components/quotation/helpers/types";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

export function TilesProductPicker({
  open, onClose, onPick,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (product: Product) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listRef = useRef<FlatList<Product>>(null);

  const search = useCallback(async (q: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "30" });
      if (q.trim()) params.set("q", q.trim());
      const res = await api.get<{ items: Product[]; total: number }>(`/products?${params.toString()}`);
      setResults(res.items || []);
      setHighlight(0);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    void search("");
  }, [open, search]);

  useEffect(() => {
    if (!open) return;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => { void search(query); }, 250);
    return () => { if (debounce.current) clearTimeout(debounce.current); };
  }, [query, open, search]);

  const pick = useCallback((product: Product | undefined) => {
    if (!product) return;
    onPick(product);
    onClose();
  }, [onPick, onClose]);

  const move = useCallback((delta: number) => {
    setHighlight((cur) => {
      const next = Math.min(Math.max(cur + delta, 0), Math.max(results.length - 1, 0));
      listRef.current?.scrollToIndex({ index: next, viewPosition: 0.5 });
      return next;
    });
  }, [results.length]);

  const onKeyPress = useCallback((e: any) => {
    if (Platform.OS !== "web") return;
    const key = e?.nativeEvent?.key;
    if (key === "ArrowDown") { e.preventDefault?.(); move(1); }
    else if (key === "ArrowUp") { e.preventDefault?.(); move(-1); }
    else if (key === "Escape") onClose();
  }, [move, onClose]);

  return (
    <Modal visible={open} animationType="fade" transparent onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.panel} onPress={() => {}}>
          <SafeAreaView edges={[]} style={{ maxHeight: "100%" }}>
            <View style={styles.searchRow}>
              <Feather name="search" size={16} color={colors.onSurfaceMuted} />
              <TextInput
                autoFocus
                value={query}
                onChangeText={setQuery}
                onKeyPress={onKeyPress}
                onSubmitEditing={() => pick(results[highlight])}
                blurOnSubmit={false}
                placeholder="Search by SKU or product name…"
                placeholderTextColor={colors.onSurfaceMuted}
                style={styles.input}
                testID="tiles-picker-search"
              />
              {loading ? <ActivityIndicator size="small" color={colors.brand} /> : null}
              <Pressable onPress={onClose} hitSlop={10} testID="tiles-picker-close">
                <Feather name="x" size={18} color={colors.onSurface} />
              </Pressable>
            </View>
            <FlatList
              ref={listRef}
              data={results}
              keyExtractor={(p) => p.id}
              keyboardShouldPersistTaps="always"
              onScrollToIndexFailed={() => {}}
              style={{ flexGrow: 0 }}
              renderItem={({ item, index }) => (
                <Pressable
                  onPress={() => pick(item)}
                  onHoverIn={() => setHighlight(index)}
                  style={[styles.row, index === highlight && styles.rowActive]}
                  testID={`tiles-picker-row-${item.sku}`}
                >
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text numberOfLines={1} style={styles.rowName}>{item.name}</Text>
                    <Text numberOfLines={1} style={styles.rowMeta}>
                      {item.sku}
                      {item.size ? `  ·  ${item.size}` : ""}
                      {item.brand_name ? `  ·  ${item.brand_name}` : ""}
                    </Text>
                  </View>
                  <Text style={styles.rowPrice}>{item.price ? money(item.price) : ""}</Text>
                </Pressable>
              )}
              ListEmptyComponent={!loading ? (
                <Text style={styles.empty}>No products match “{query}”.</Text>
              ) : null}
            />
            {Platform.OS === "web" ? (
              <Text style={styles.hint}>↑↓ to highlight · Enter to add · Esc to close</Text>
            ) : null}
          </SafeAreaView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1, backgroundColor: "rgba(20,20,20,0.45)",
    alignItems: "center", justifyContent: "flex-start",
    paddingTop: 80, paddingHorizontal: spacing.lg,
  },
  panel: {
    width: "100%", maxWidth: 620, maxHeight: 480,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    overflow: "hidden",
    ...(Platform.OS === "web" ? { boxShadow: "0 18px 50px rgba(0,0,0,0.25)" } as any : {}),
  },
  searchRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  input: {
    flex: 1, fontSize: 15, color: colors.onSurface, paddingVertical: 4,
    ...(Platform.OS === "web" ? { outlineStyle: "none" } as any : {}),
  },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.divider,
  },
  rowActive: { backgroundColor: colors.brandTint },
  rowName: { fontSize: 14, fontFamily: type.titleMd.fontFamily, fontWeight: "600", color: colors.onSurface },
  rowMeta: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 1 },
  rowPrice: { fontSize: 13, fontVariant: ["tabular-nums"], color: colors.onSurfaceSecondary },
  empty: { padding: spacing.lg, fontSize: 13, color: colors.onSurfaceMuted, textAlign: "center" },
  hint: {
    paddingHorizontal: spacing.lg, paddingVertical: 8, fontSize: 11,
    color: colors.onSurfaceMuted, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.divider,
  },
});
