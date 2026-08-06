import { Feather } from "@expo/vector-icons";
import React, { useEffect, useMemo, useState } from "react";
import { FlatList, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { useBp } from "@/src/design/responsive";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
import { storage } from "@/src/utils/storage";

import { columnsForView } from "./notebookModel";
import { CellSaveState, NotebookCell } from "./NotebookCell";
import type { NotebookField, NotebookRow, NotebookView } from "./notebookTypes";

const ACTION_WIDTH = 145;

type Props = {
  floorId: string;
  view: NotebookView;
  rows: NotebookRow[];
  saveStates: Record<string, CellSaveState>;
  onPatch: (row: NotebookRow, field: NotebookField, value: string | number | null) => Promise<void>;
  onConvert: (row: NotebookRow) => void;
  onSelectRow: (row: NotebookRow) => void;
};

export function NotebookGrid({ floorId, view, rows, saveStates, onPatch, onConvert, onSelectRow }: Props) {
  const { isPhone } = useBp();
  const columns = columnsForView(view);
  const [widths, setWidths] = useState<Record<string, number>>({});
  const key = `notebook.column-widths.${floorId}.${view}`;

  useEffect(() => {
    void storage.getItem<string>(key, "").then((stored) => {
      if (!stored) return;
      try { setWidths(JSON.parse(stored) as Record<string, number>); } catch { setWidths({}); }
    });
  }, [key]);

  const resolvedWidths = useMemo(() => Object.fromEntries(columns.map((column) => [column.key, Math.max(column.minWidth, widths[column.key] || column.minWidth)])), [columns, widths]);
  const totalWidth = columns.reduce((sum, column) => sum + resolvedWidths[column.key], ACTION_WIDTH);

  const resize = (field: string) => {
    const next = { ...widths, [field]: (resolvedWidths[field] || 120) + 24 };
    setWidths(next);
    void storage.setItem(key, JSON.stringify(next));
  };

  const header = (
    <View style={[styles.header, { width: totalWidth }]}>
      {columns.map((column, index) => (
        <View key={column.key} style={[styles.headerCell, { width: resolvedWidths[column.key] }, index === 0 && styles.stickyColumn]}>
          <Text numberOfLines={2} style={styles.headerText}>{column.label}</Text>
          {Platform.OS === "web" && !isPhone ? <Pressable accessibilityLabel={`Widen ${column.label}`} onPress={() => resize(column.key)} style={styles.resizeHandle}><Feather name="more-vertical" size={13} color={colors.onSurfaceSubtle} /></Pressable> : null}
        </View>
      ))}
      <View style={[styles.headerCell, { width: ACTION_WIDTH }]}><Text style={styles.headerText}>Actions</Text></View>
    </View>
  );

  return (
    <View style={styles.frame}>
      <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={{ minWidth: totalWidth }}>
        <FlatList
          data={rows}
          keyExtractor={(row) => row.id}
          ListHeaderComponent={header}
          stickyHeaderIndices={[0]}
          removeClippedSubviews
          initialNumToRender={24}
          maxToRenderPerBatch={32}
          windowSize={9}
          renderItem={({ item: row }) => (
            <View style={[styles.row, { width: totalWidth }]}>
              {columns.map((column, index) => (
                <View key={column.key} style={[index === 0 && styles.stickyColumn]}>
                  <NotebookCell
                    row={row}
                    field={column.key}
                    width={resolvedWidths[column.key]}
                    editable={row.status !== "won" || Boolean(column.quotationOnly)}
                    saveState={saveStates[`${row.id}:${column.key}`]}
                    onSelect={() => onSelectRow(row)}
                    onCommit={(value) => onPatch(row, column.key, value)}
                  />
                </View>
              ))}
              <View style={[styles.actionCell, { width: ACTION_WIDTH }]}>
                {!row.is_converted ? <Pressable onPress={() => onConvert(row)} style={styles.convertButton}><Text style={styles.convertText}>Convert to quotation</Text></Pressable> : <Text style={styles.converted}>Quotation follow-up</Text>}
              </View>
            </View>
          )}
          ListEmptyComponent={<View style={styles.empty}><Text style={styles.emptyTitle}>No follow-ups yet.</Text><Text style={styles.emptyText}>Start the notebook with a new customer row.</Text></View>}
        />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  header: { flexDirection: "row", backgroundColor: colors.surfaceTertiary, borderBottomWidth: 1, borderBottomColor: colors.borderStrong, minHeight: 48 },
  headerCell: { minHeight: 48, paddingHorizontal: spacing.sm, paddingVertical: spacing.sm, justifyContent: "center", borderRightWidth: StyleSheet.hairlineWidth, borderColor: colors.borderStrong, position: "relative" },
  headerText: { ...type.caption, color: colors.onSurfaceMuted, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5 },
  resizeHandle: { position: "absolute", right: 0, top: 0, bottom: 0, width: 18, alignItems: "center", justifyContent: "center" },
  stickyColumn: { backgroundColor: colors.surfaceSecondary },
  row: { flexDirection: "row", minHeight: 58 },
  actionCell: { minHeight: 58, padding: spacing.sm, justifyContent: "center", borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  convertButton: { borderWidth: 1, borderColor: colors.brandBorder, borderRadius: radius.sm, paddingHorizontal: 8, paddingVertical: 8, alignItems: "center" },
  convertText: { fontSize: 11, color: colors.brand, fontWeight: "700", textAlign: "center" },
  converted: { fontSize: 11, color: colors.success, textAlign: "center" },
  empty: { minHeight: 210, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  emptyTitle: { ...type.titleSm, color: colors.onSurface },
  emptyText: { ...type.bodySm, color: colors.onSurfaceMuted, marginTop: 6 },
});
