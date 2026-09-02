import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { notebookApi, type NotebookCreate } from "@/src/api/notebook";
import { toast } from "@/src/components/Toast";
import { BottomSheet } from "@/src/components/BottomSheet";
import { Button, Chip, EmptyState, PageHeader, SearchField, TextField } from "@/src/components/ui";
import { columnsForView, FOLLOWUP_FILTERS, formatIndianDate, formatRupees } from "@/src/components/notebook/notebookModel";
import type { NotebookField, NotebookFilter, NotebookRow, NotebookStatus, NotebookView } from "@/src/components/notebook/notebookTypes";
import { useBp } from "@/src/design/responsive";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
import { layout } from "@/src/design/tokens";

const STATUS_LABELS: Record<NotebookStatus, string> = { new: "New", pending: "Pending", won: "Won", lost: "Lost" };
const EMPTY_DRAFT: NotebookCreate = { customer_name: "", customer_phone: "", address: "", referred_by: "", architect_interior_designer: "", notes: "" };

function valueForCell(row: NotebookRow, field: NotebookField): string {
  const value = row[field];
  if (field === "quotation_price" || field === "estimated_value") return formatRupees(value as number | null);
  if (field === "quotation_date") return formatIndianDate(value as string | null);
  if (field === "status") return STATUS_LABELS[value as NotebookStatus];
  return String(value ?? "");
}

function editableValue(field: NotebookField, value: string): unknown {
  if (field === "quotation_price" || field === "estimated_value") return value.trim() === "" ? null : Number(value.replace(/[^0-9.]/g, ""));
  return value;
}

export function NotebookScreen({ floorId, floorName, view }: { floorId: string; floorName: string; view: NotebookView }) {
  const { isPhone, isTabletPortrait } = useBp();
  // A portrait tablet has less usable width than its viewport suggests once
  // the persistent admin rail is present. Keep the dense spreadsheet for
  // landscape/desktop and use the same readable cards as phones here.
  const useCardList = isPhone || isTabletPortrait;
  const kitchen = floorId === "second-floor";
  const columns = useMemo(() => columnsForView(view, floorId), [floorId, view]);
  const [rows, setRows] = useState<NotebookRow[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [filter, setFilter] = useState<Exclude<NotebookFilter, "quotation">>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const requestIdRef = useRef(0);
  const [editing, setEditing] = useState<{ id: string; field: NotebookField } | null>(null);
  const [cellValue, setCellValue] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [conflictCells, setConflictCells] = useState<Set<string>>(new Set());
  const [draftOpen, setDraftOpen] = useState(false);
  const [draft, setDraft] = useState<NotebookCreate>({ ...EMPTY_DRAFT, ...(kitchen ? { kitchen_type: "GI" as const } : {}) });

  const load = useCallback(async (cursor?: string, append = false) => {
    const requestId = ++requestIdRef.current;
    if (append) setLoadingMore(true); else setLoading(true);
    try {
      const result = await notebookApi.list(floorId, { view, status: view === "followups" ? filter : undefined, q: search.trim() || undefined, cursor });
      if (requestId !== requestIdRef.current) return;
      setRows((current) => append ? [...current, ...result.rows] : result.rows);
      setNextCursor(result.next_cursor);
    } catch (error: any) {
      if (requestId === requestIdRef.current) toast.error(error?.detail || "Could not load the notebook");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false); setLoadingMore(false);
      }
    }
  }, [filter, floorId, search, view]);

  useEffect(() => {
    const timer = setTimeout(() => { void load(); }, search ? 250 : 0);
    return () => { clearTimeout(timer); requestIdRef.current += 1; };
  }, [load, search]);

  const beginEdit = (row: NotebookRow, field: NotebookField) => {
    if (row.status === "won" && !["quotation_price", "estimated_value", "quotation_date"].includes(field)) return;
    setEditing({ id: row.id, field });
    const raw = row[field];
    setCellValue(raw === null || raw === undefined ? "" : String(raw));
  };
  const patch = async (row: NotebookRow, field: NotebookField, raw: string) => {
    const key = `${row.id}:${field}`;
    const value = editableValue(field, raw);
    if ((field === "quotation_price" || field === "estimated_value") && raw.trim() && Number.isNaN(value)) { toast.error("Enter a valid amount"); return; }
    if (field === "status" && value === "lost" && !row.notes.trim()) { toast.error("Add a note before marking Lost"); return; }
    if (field === "status" && value === "won" && Platform.OS === "web" && !globalThis.confirm("Mark this follow-up as Won?")) return;
    setSaving(key);
    try {
      const updated = await notebookApi.patch(floorId, row.id, field, value, row.updated_at);
      setRows((current) => current.map((item) => item.id === row.id ? updated : item));
      toast.success("Saved");
    } catch (error: any) {
      if (error?.status === 409) {
        let conflict: { row?: NotebookRow; changed_fields?: string[] } = {};
        try { conflict = JSON.parse(error.detail); } catch { /* retain the confirmed value if a proxy stripped detail */ }
        if (conflict.row) setRows((current) => current.map((item) => item.id === row.id ? conflict.row! : item));
        setConflictCells(new Set((conflict.changed_fields?.length ? conflict.changed_fields : [field]).map((changed) => `${row.id}:${changed === "notebook_status" ? "status" : changed}`)));
        toast.error("This row changed elsewhere; the refreshed cells are highlighted.");
      }
      else toast.error(error?.detail || "Could not save this field");
    } finally { setSaving(null); setEditing(null); }
  };
  const convert = async (row: NotebookRow) => {
    setSaving(`${row.id}:convert`);
    try {
      await notebookApi.convert(floorId, row.id, {}, row.updated_at);
      setRows((current) => current.filter((item) => item.id !== row.id));
      toast.success("Moved to Quotation Follow-ups");
    } catch (error: any) { toast.error(error?.detail || "Could not convert this follow-up"); }
    finally { setSaving(null); }
  };
  const create = async () => {
    if (!draft.customer_name.trim() || !draft.customer_phone.trim() || (kitchen && !draft.kitchen_type)) { toast.error("Enter the required customer details"); return; }
    setSaving("draft");
    try {
      const row = await notebookApi.create(floorId, draft);
      setRows((current) => [row, ...current.filter((item) => item.id !== row.id)]);
      setDraft({ ...EMPTY_DRAFT, ...(kitchen ? { kitchen_type: "GI" as const } : {}) }); setDraftOpen(false);
      toast.success("Follow-up added");
    } catch (error: any) { toast.error(error?.detail || "Could not add the follow-up"); }
    finally { setSaving(null); }
  };

  const draftFields = (
    <View style={{ gap: spacing.md }}>
      <TextField label="Customer Name *" value={draft.customer_name} onChangeText={(customer_name) => setDraft((d) => ({ ...d, customer_name }))} />
      <TextField label="Mobile Number *" keyboardType="phone-pad" value={draft.customer_phone} onChangeText={(customer_phone) => setDraft((d) => ({ ...d, customer_phone }))} />
      {kitchen ? <View><Text style={type.label}>Kitchen Type *</Text><View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs }}>{(["GI", "SS"] as const).map((kind) => <Chip key={kind} label={kind} active={draft.kitchen_type === kind} onPress={() => setDraft((d) => ({ ...d, kitchen_type: kind }))} />)}</View></View> : null}
      <TextField label="Address" value={draft.address} onChangeText={(address) => setDraft((d) => ({ ...d, address }))} />
      <TextField label="Referred By" value={draft.referred_by} onChangeText={(referred_by) => setDraft((d) => ({ ...d, referred_by }))} />
      <TextField label="Architect / Interior Designer" value={draft.architect_interior_designer} onChangeText={(architect_interior_designer) => setDraft((d) => ({ ...d, architect_interior_designer }))} />
      <TextField label="Notes" multiline value={draft.notes} onChangeText={(notes) => setDraft((d) => ({ ...d, notes }))} />
      <Button label="Add Follow-up" icon="plus" onPress={() => void create()} loading={saving === "draft"} />
    </View>
  );

  const phoneRows = (
    <View style={styles.phoneList}>
      {rows.map((row) => {
        const statusEditing = editing?.id === row.id && editing.field === "status";
        const summaryFields = columns.filter((column) => !["customer_name", "customer_phone", "status"].includes(column.key));
        return (
          <View key={row.id} style={styles.phoneCard}>
            <View style={styles.phoneCardHeader}>
              <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                <Text style={styles.phoneName}>{row.customer_name}</Text>
                <Text selectable style={styles.phonePhone}>{row.customer_phone}</Text>
              </View>
              <Pressable
                onPress={() => beginEdit(row, "status")}
                accessibilityRole="button"
                accessibilityLabel={`Edit status for ${row.customer_name}`}
                style={styles.statusButton}
              >
                <Text style={styles.statusButtonText}>{STATUS_LABELS[row.status]}</Text>
              </Pressable>
            </View>
            {statusEditing ? (
              <View style={styles.phoneStatusChoices}>
                {(Object.keys(STATUS_LABELS) as NotebookStatus[]).map((status) => (
                  <Chip key={status} label={STATUS_LABELS[status]} active={row.status === status} onPress={() => void patch(row, "status", status)} />
                ))}
              </View>
            ) : null}
            <View style={styles.phoneFields}>
              {summaryFields.map((column) => {
                const key = `${row.id}:${column.key}`;
                const active = editing?.id === row.id && editing.field === column.key;
                const value = valueForCell(row, column.key);
                if (!value || value === "—") return null;
                return (
                  <Pressable
                    key={column.key}
                    onPress={() => beginEdit(row, column.key)}
                    accessibilityRole="button"
                    accessibilityLabel={`Edit ${column.label} for ${row.customer_name}`}
                    accessibilityState={{ busy: saving === key }}
                    style={[styles.phoneField, active && styles.activeCell, conflictCells.has(key) && styles.conflictCell]}
                  >
                    <Text style={styles.phoneFieldLabel}>{column.label}</Text>
                    {active ? (
                      <TextInput
                        autoFocus
                        value={cellValue}
                        onChangeText={setCellValue}
                        onBlur={() => void patch(row, column.key, cellValue)}
                        onSubmitEditing={() => void patch(row, column.key, cellValue)}
                        accessibilityLabel={`${column.label} for ${row.customer_name}`}
                        style={styles.phoneFieldInput}
                      />
                    ) : <Text style={styles.phoneFieldValue}>{value}</Text>}
                    {saving === key ? <Text style={styles.saveText}>Saving…</Text> : null}
                  </Pressable>
                );
              })}
            </View>
            {view === "followups" ? (
              <Button label="Move to quotation follow-up" size="sm" variant="secondary" onPress={() => void convert(row)} loading={saving === `${row.id}:convert`} fullWidth />
            ) : null}
          </View>
        );
      })}
    </View>
  );

  return <SafeAreaView style={{ flex: 1 }} edges={isPhone ? [] : ["top"]}>
    <PageHeader title={`${floorName} ${view === "quotation" ? "Quotation Follow-ups" : "Follow-ups"}`} overline="DIGITAL NOTEBOOK" subtitle={view === "quotation" ? "Converted customer follow-ups" : "A simple customer follow-up register"} actions={!useCardList && view === "followups" ? <Button label="New Follow-up" icon="plus" onPress={() => setDraftOpen(true)} /> : undefined} />
    <ScrollView contentContainerStyle={{ padding: isPhone ? spacing.md : spacing.xl, paddingBottom: isPhone ? layout.bottomBar + spacing.xl : spacing.xl, gap: spacing.lg }} keyboardShouldPersistTaps="handled">
      <SearchField value={search} onChangeText={setSearch} onClear={() => setSearch("")} placeholder="Search customer, mobile, address, referral or notes" />
      {useCardList && view === "followups" ? <Button label="New Follow-up" icon="plus" onPress={() => setDraftOpen(true)} fullWidth /> : null}
      {view === "followups" ? <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>{FOLLOWUP_FILTERS.map((item) => <Chip key={item} label={item === "all" ? "All" : STATUS_LABELS[item]} active={filter === item} onPress={() => setFilter(item)} />)}</View> : null}
      {!isPhone && draftOpen && view === "followups" ? <View style={styles.draft}>{draftFields}</View> : null}
      {loading ? <ActivityIndicator color={colors.brand} /> : rows.length === 0 ? <EmptyState icon="book-open" title="No follow-ups yet." subtitle="Add the first customer to this notebook." action={view === "followups" ? <Button label="New Follow-up" icon="plus" onPress={() => setDraftOpen(true)} /> : undefined} /> : useCardList ? phoneRows : <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={styles.grid}>
        <View>
          <View style={styles.header}>{columns.map((column) => <Text key={column.key} style={[styles.headerCell, { width: column.minWidth }]}>{column.label}</Text>)}{view === "followups" ? <Text style={[styles.headerCell, { width: 160 }]}>Action</Text> : null}</View>
          {rows.map((row) => <View key={row.id} style={styles.row}>{columns.map((column) => {
            const key = `${row.id}:${column.key}`; const active = editing?.id === row.id && editing.field === column.key;
            if (column.key === "status" && active) return <View key={column.key} style={[styles.cell, { width: column.minWidth, flexDirection: "row", gap: 4 }]}>{(Object.keys(STATUS_LABELS) as NotebookStatus[]).map((status) => <Chip key={status} label={STATUS_LABELS[status]} active={row.status === status} onPress={() => void patch(row, "status", status)} />)}</View>;
            return <Pressable
              key={column.key}
              onPress={() => beginEdit(row, column.key)}
              accessibilityRole="button"
              accessibilityLabel={`Edit ${column.label} for ${row.customer_name}`}
              accessibilityState={{ busy: saving === key }}
              style={[styles.cell, { width: column.minWidth }, active && styles.activeCell, conflictCells.has(key) && styles.conflictCell]}
            >
              {active ? <TextInput autoFocus value={cellValue} onChangeText={setCellValue} onBlur={() => void patch(row, column.key, cellValue)} onSubmitEditing={() => void patch(row, column.key, cellValue)} accessibilityLabel={`${column.label} for ${row.customer_name}`} style={styles.input} /> : <Text numberOfLines={2} style={styles.cellText}>{valueForCell(row, column.key)}</Text>}
              {saving === key ? <Text style={styles.saveText}>Saving…</Text> : null}
            </Pressable>;
          })}{view === "followups" ? <View style={[styles.cell, { width: 160 }]}>{saving === `${row.id}:convert` ? <ActivityIndicator color={colors.brand} /> : <Button label="To quotation" size="sm" variant="secondary" onPress={() => void convert(row)} />}</View> : null}</View>)}</View>
      </ScrollView>}
      {nextCursor ? <Button label="Load more" variant="secondary" onPress={() => void load(nextCursor, true)} loading={loadingMore} /> : null}
    </ScrollView>
    {isPhone ? <BottomSheet visible={draftOpen} onClose={() => setDraftOpen(false)} title="New Follow-up">{draftFields}</BottomSheet> : null}
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  draft: { backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, borderRadius: radius.lg, padding: spacing.lg },
  grid: { minWidth: "100%" }, header: { flexDirection: "row", backgroundColor: colors.surfaceTertiary, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  headerCell: { padding: spacing.md, fontFamily: type.titleMd.fontFamily, fontSize: 12, fontWeight: "600", color: colors.onSurfaceSecondary },
  row: { flexDirection: "row", borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  cell: { minHeight: 52, padding: spacing.md, borderRightWidth: StyleSheet.hairlineWidth, borderColor: colors.border, justifyContent: "center" },
  activeCell: { backgroundColor: colors.brandTint }, conflictCell: { backgroundColor: colors.warningBg }, cellText: { fontFamily: type.body.fontFamily, fontSize: 14, color: colors.onSurface }, input: { fontFamily: type.body.fontFamily, color: colors.onSurface, fontSize: 14, padding: 0, minHeight: 30 }, saveText: { color: colors.onSurfaceMuted, fontSize: 11, marginTop: 2 },
  phoneList: { gap: spacing.md },
  phoneCard: { gap: spacing.md, padding: spacing.md, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  phoneCardHeader: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  phoneName: { fontFamily: type.titleMd.fontFamily, fontSize: 16, fontWeight: "700", color: colors.onSurface, lineHeight: 22 },
  phonePhone: { fontFamily: type.body.fontFamily, fontSize: 14, color: colors.onSurfaceSecondary },
  statusButton: { minHeight: 44, justifyContent: "center", paddingHorizontal: 10, borderRadius: radius.md, backgroundColor: colors.surfaceTertiary },
  statusButtonText: { fontFamily: type.label.fontFamily, fontSize: 12, fontWeight: "700", color: colors.onSurface },
  phoneStatusChoices: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  phoneFields: { gap: spacing.xs },
  phoneField: { minHeight: 44, paddingVertical: spacing.xs, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  phoneFieldLabel: { fontFamily: type.label.fontFamily, fontSize: 11, fontWeight: "700", color: colors.onSurfaceMuted, textTransform: "uppercase", letterSpacing: 0.5 },
  phoneFieldValue: { fontFamily: type.body.fontFamily, fontSize: 14, lineHeight: 20, color: colors.onSurface, marginTop: 2 },
  phoneFieldInput: { fontFamily: type.body.fontFamily, fontSize: 15, color: colors.onSurface, paddingVertical: 4, minHeight: 32, marginTop: 2 },
});
