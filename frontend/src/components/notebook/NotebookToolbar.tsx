import { Feather } from "@expo/vector-icons";
import React from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme/tokens";

import type { NotebookFilter, NotebookView } from "./notebookTypes";

type Props = {
  view: NotebookView;
  filter: NotebookFilter;
  query: string;
  onViewChange: (view: NotebookView) => void;
  onFilterChange: (filter: NotebookFilter) => void;
  onQueryChange: (query: string) => void;
  onStartNew: () => void;
};

export function NotebookToolbar({ view, filter, query, onViewChange, onFilterChange, onQueryChange, onStartNew }: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.topRow}>
        <View style={styles.viewTabs}>
          <Pressable onPress={() => { onViewChange("followups"); onFilterChange("all"); }} style={[styles.tab, view === "followups" && styles.tabActive]}><Text style={[styles.tabText, view === "followups" && styles.tabTextActive]}>Follow-ups</Text></Pressable>
          <Pressable onPress={() => { onViewChange("quotation"); onFilterChange("quotation"); }} style={[styles.tab, view === "quotation" && styles.tabActive]}><Text style={[styles.tabText, view === "quotation" && styles.tabTextActive]}>Quotation Follow-ups</Text></Pressable>
        </View>
        <Pressable onPress={onStartNew} style={styles.newButton} accessibilityRole="button"><Feather name="plus" size={15} color={colors.onBrand} /><Text style={styles.newText}>New Follow-up</Text></Pressable>
      </View>
      <View style={styles.bottomRow}>
        <View style={styles.filters}>
          {(["all", "pending", "won", "lost", "new", "quotation"] as NotebookFilter[]).map((value) => (
            <Pressable key={value} onPress={() => value === "quotation" ? (onViewChange("quotation"), onFilterChange("quotation")) : onFilterChange(value)} style={[styles.filter, filter === value && styles.filterActive]}>
              <Text style={[styles.filterText, filter === value && styles.filterTextActive]}>{value === "all" ? "All" : value === "quotation" ? "Quotation" : value[0].toUpperCase() + value.slice(1)}</Text>
            </Pressable>
          ))}
        </View>
        <View style={styles.searchWrap}><Feather name="search" size={14} color={colors.onSurfaceMuted} /><TextInput value={query} onChangeText={onQueryChange} placeholder="Search notebook" placeholderTextColor={colors.onSurfaceSubtle} style={styles.search} returnKeyType="search" /></View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md, marginBottom: spacing.md },
  topRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  viewTabs: { flexDirection: "row", borderBottomWidth: 1, borderColor: colors.border, flexShrink: 1 },
  tab: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, minHeight: 42, justifyContent: "center" },
  tabActive: { borderBottomWidth: 2, borderColor: colors.brand },
  tabText: { ...type.bodySm, color: colors.onSurfaceMuted, fontWeight: "600" },
  tabTextActive: { color: colors.brand },
  newButton: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, borderRadius: radius.sm, backgroundColor: colors.brand },
  newText: { ...type.bodySm, color: colors.onBrand, fontWeight: "700" },
  bottomRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md, flexWrap: "wrap" },
  filters: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  filter: { minHeight: 36, paddingHorizontal: 11, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary },
  filterActive: { backgroundColor: colors.brandTintStrong },
  filterText: { fontSize: 12, color: colors.onSurfaceMuted, fontWeight: "600" },
  filterTextActive: { color: colors.brand },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: 6, minWidth: 220, height: 38, paddingHorizontal: 10, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  search: { flex: 1, ...type.bodySm, color: colors.onSurface, paddingVertical: 0 },
});

