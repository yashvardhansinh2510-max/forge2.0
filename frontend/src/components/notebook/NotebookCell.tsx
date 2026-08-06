import { Feather } from "@expo/vector-icons";
import React, { useEffect, useRef, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme/tokens";

import type { NotebookField, NotebookRow } from "./notebookTypes";
import { formatIndianDate, formatRupees } from "./notebookModel";

export type CellSaveState = "idle" | "saving" | "saved" | "error" | "conflict";

type Props = {
  row: NotebookRow;
  field: NotebookField;
  width: number;
  editable: boolean;
  saveState?: CellSaveState;
  onCommit: (value: string | number | null) => Promise<void>;
  onSelect?: () => void;
};

function displayValue(row: NotebookRow, field: NotebookField): string {
  const value = row[field];
  if (field === "quotation_price" || field === "estimated_value") return formatRupees(value as number | null | undefined);
  if (field === "quotation_date") return formatIndianDate(value as string | null | undefined);
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

export function NotebookCell({ row, field, width, editable, saveState = "idle", onCommit, onSelect }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(displayValue(row, field) === "—" ? "" : displayValue(row, field));
  const inputRef = useRef<TextInput>(null);

  useEffect(() => {
    if (!editing) setDraft(displayValue(row, field) === "—" ? "" : displayValue(row, field));
  }, [row, field, editing]);

  const commit = async () => {
    setEditing(false);
    const value = field === "quotation_price" || field === "estimated_value"
      ? (draft.trim() ? Number(draft.replace(/[^0-9.]/g, "")) : null)
      : draft;
    await onCommit(value);
  };

  const start = () => {
    if (!editable || row.status === "won" && !field.startsWith("quotation_")) return;
    onSelect?.();
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  if (field === "status" && editable) {
    return (
      <View style={[styles.cell, { width }]}>
        <Text style={styles.cellText}>{displayValue(row, field)}</Text>
        <View style={styles.choiceRow}>
          {(["new", "pending", "won", "lost"] as const).map((status) => {
            const disabled = status === "lost" && !row.notes.trim();
            return (
              <Pressable
                key={status}
                disabled={disabled}
                onPress={() => void onCommit(status)}
                style={[styles.choice, row.status === status && styles.choiceActive, disabled && styles.choiceDisabled]}
              >
                <Text style={[styles.choiceText, row.status === status && styles.choiceTextActive]}>{status[0].toUpperCase()}</Text>
              </Pressable>
            );
          })}
        </View>
        {saveState !== "idle" && <SaveState state={saveState} />}
      </View>
    );
  }

  return (
    <Pressable
      onPress={start}
      style={[styles.cell, { width }, editing && styles.cellEditing, Platform.OS === "web" ? ({ cursor: editable ? "text" : "default" } as any) : null]}
      accessibilityRole="button"
      accessibilityLabel={`${field} ${displayValue(row, field)}`}
    >
      {editing ? (
        <TextInput
          ref={inputRef}
          value={draft}
          onChangeText={setDraft}
          onBlur={() => void commit()}
          onSubmitEditing={() => void commit()}
          onKeyPress={(event) => { if (event.nativeEvent.key === "Escape") { setEditing(false); setDraft(displayValue(row, field)); } }}
          multiline={field === "notes" || field === "address"}
          style={styles.input}
          placeholder="—"
          placeholderTextColor={colors.onSurfaceSubtle}
          autoCapitalize="sentences"
        />
      ) : (
        <Text numberOfLines={field === "notes" || field === "address" ? 2 : 1} style={styles.cellText}>{displayValue(row, field)}</Text>
      )}
      {saveState !== "idle" && <SaveState state={saveState} />}
    </Pressable>
  );
}

function SaveState({ state }: { state: CellSaveState }) {
  const config = {
    saving: ["Saving…", colors.onSurfaceMuted], saved: ["Saved", colors.success],
    error: ["Error", colors.error], conflict: ["Changed", colors.warning], idle: ["", colors.onSurfaceMuted],
  }[state];
  return <View style={styles.state}><Feather name={state === "saved" ? "check" : state === "error" || state === "conflict" ? "alert-circle" : "loader"} size={11} color={config[1]} /><Text style={[styles.stateText, { color: config[1] }]}>{config[0]}</Text></View>;
}

const styles = StyleSheet.create({
  cell: { minHeight: 58, paddingHorizontal: spacing.sm, paddingVertical: spacing.sm, borderRightWidth: StyleSheet.hairlineWidth, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, justifyContent: "center", position: "relative" },
  cellEditing: { backgroundColor: colors.selection, borderColor: colors.brand, borderWidth: 1 },
  cellText: { ...type.bodySm, color: colors.onSurface, lineHeight: 19 },
  input: { ...type.bodySm, color: colors.onSurface, minHeight: 34, paddingVertical: 4, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: colors.brand },
  state: { position: "absolute", right: 5, bottom: 3, flexDirection: "row", alignItems: "center", gap: 2 },
  stateText: { fontSize: 9 },
  choiceRow: { flexDirection: "row", gap: 4, marginTop: 6 },
  choice: { width: 22, height: 22, alignItems: "center", justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary },
  choiceActive: { backgroundColor: colors.brand },
  choiceDisabled: { opacity: 0.28 },
  choiceText: { fontSize: 10, color: colors.onSurfaceMuted, fontWeight: "700" },
  choiceTextActive: { color: colors.onBrand },
});
