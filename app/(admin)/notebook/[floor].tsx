import { useLocalSearchParams } from "expo-router";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError, api } from "@/src/api/client";
import { BottomSheet } from "@/src/components/BottomSheet";
import { useBp } from "@/src/design/responsive";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
import { FURNITURE_FLOOR_ID, KITCHEN_FLOOR_ID, NOTEBOOK_FLOOR_LABELS } from "@/src/constants/floors";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

import { NotebookGrid } from "@/src/components/notebook/NotebookGrid";
import type { CellSaveState } from "@/src/components/notebook/NotebookCell";
import { NotebookToolbar } from "@/src/components/notebook/NotebookToolbar";
import type { NotebookField, NotebookFilter, NotebookRow, NotebookView } from "@/src/components/notebook/notebookTypes";

type Draft = { customer_name: string; customer_phone: string; address: string; kitchen_type: "GI" | "SS"; referred_by: string; architect_interior_designer: string; notes: string };
type TimelineEvent = { id: string; event_type: string; summary?: string; created_at: string; actor_name?: string; payload?: Record<string, unknown> };

const EMPTY_DRAFT: Draft = { customer_name: "", customer_phone: "", address: "", kitchen_type: "GI", referred_by: "", architect_interior_designer: "", notes: "" };

export default function NotebookRoute() {
  const { floor: slug } = useLocalSearchParams<{ floor: string }>();
  const floorId = slug === "furniture" ? FURNITURE_FLOOR_ID : KITCHEN_FLOOR_ID;
  const floorName = NOTEBOOK_FLOOR_LABELS[floorId];
  const { isPhone } = useBp();
  useRequireFloorAccess(floorId);
  const [view, setView] = useState<NotebookView>("followups");
  const [filter, setFilter] = useState<NotebookFilter>("all");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<NotebookRow[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveStates, setSaveStates] = useState<Record<string, CellSaveState>>({});
  const [selected, setSelected] = useState<NotebookRow | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);

  const listPath = useCallback((cursor?: string | null) => {
    const params = new URLSearchParams({ view, limit: "100" });
    if (view === "followups" && filter !== "all" && filter !== "quotation") params.set("status", filter);
    if (query.trim()) params.set("q", query.trim());
    if (cursor) params.set("cursor", cursor);
    return `/followups/notebook/${floorId}?${params.toString()}`;
  }, [filter, floorId, query, view]);

  const load = useCallback(async (append = false) => {
    if (append) setLoadingMore(true); else setLoading(true);
    setError(null);
    try {
      const result = await api.get<{ rows: NotebookRow[]; next_cursor: string | null }>(listPath(append ? nextCursor : null), { floorId });
      setRows((current) => append ? [...current, ...result.rows] : result.rows);
      setNextCursor(result.next_cursor);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Notebook could not be loaded");
    } finally {
      setLoading(false); setLoadingMore(false);
    }
  }, [floorId, listPath, nextCursor]);

  useEffect(() => {
    const timer = setTimeout(() => { void load(false); }, 260);
    return () => clearTimeout(timer);
  }, [load, view, filter, query]);

  const selectRow = useCallback((row: NotebookRow) => {
    setSelected(row);
    void api.get<TimelineEvent[]>(`/followups/notebook/${floorId}/${row.id}/timeline`, { floorId }).then(setTimeline).catch(() => setTimeline([]));
  }, [floorId]);

  const setState = (key: string, state: CellSaveState) => setSaveStates((current) => ({ ...current, [key]: state }));

  const persistPatch = useCallback(async (row: NotebookRow, field: NotebookField, value: string | number | null) => {
    const key = `${row.id}:${field}`;
    setState(key, "saving");
    try {
      const updated = await api.patch<NotebookRow>(`/followups/notebook/${floorId}/${row.id}`, { field, value, updated_at: row.updated_at }, { floorId });
      setRows((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSelected((current) => current?.id === updated.id ? updated : current);
      setState(key, "saved");
      setTimeout(() => setState(key, "idle"), 1100);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        try {
          const detail = JSON.parse(cause.detail) as { row?: NotebookRow };
          if (detail.row) {
            setRows((current) => current.map((item) => item.id === detail.row!.id ? detail.row! : item));
            setSelected(detail.row);
          }
        } catch { /* The server's conflict message remains visible. */ }
        setState(key, "conflict");
      } else {
        setState(key, "error");
      }
      throw cause;
    }
  }, [floorId]);

  const onPatch = useCallback(async (row: NotebookRow, field: NotebookField, value: string | number | null) => {
    if (field === "status" && value === "won" && row.status !== "won") {
      await new Promise<void>((resolve) => Alert.alert("Mark Won?", "This locks Follow-up fields. Quotation fields remain editable after conversion.", [
        { text: "Cancel", style: "cancel", onPress: () => resolve() },
        { text: "Mark Won", onPress: () => { void persistPatch(row, field, value).catch(() => undefined).finally(resolve); } },
      ]));
      return;
    }
    await persistPatch(row, field, value);
  }, [persistPatch]);

  const convert = useCallback((row: NotebookRow) => {
    void api.post<NotebookRow>(`/followups/notebook/${floorId}/${row.id}/convert`, { updated_at: row.updated_at }, { floorId }).then((updated) => {
      setRows((current) => view === "followups" ? current.filter((item) => item.id !== updated.id) : current.map((item) => item.id === updated.id ? updated : item));
      setSelected(updated);
      setView("quotation"); setFilter("quotation");
    }).catch(() => undefined);
  }, [floorId, view]);

  const create = useCallback(async () => {
    if (!draft.customer_name.trim() || !draft.customer_phone.trim() || !draft.kitchen_type) return;
    try {
      const row = await api.post<NotebookRow>(`/followups/notebook/${floorId}`, draft, { floorId });
      setRows((current) => view === "followups" ? [row, ...current.filter((item) => item.id !== row.id)] : current);
      setCreating(false); setDraft(EMPTY_DRAFT); setSelected(row); setView("followups"); setFilter("all");
    } catch { /* Keep the draft visible; the next interaction can retry. */ }
  }, [draft, floorId, view]);

  const form = <NewFollowupForm draft={draft} setDraft={setDraft} onCreate={() => void create()} />;
  const selectedTimeline = useMemo(() => timeline.slice(0, 30), [timeline]);

  return (
    <View style={styles.page}>
      <View style={styles.pageContent}>
      <View style={styles.header}><View style={{ flex: 1 }}><Text style={styles.eyebrow}>BUSINESS NOTEBOOK</Text><Text style={styles.title}>{floorName}</Text><Text style={styles.subtitle}>A calm register for every customer conversation.</Text></View></View>
      <NotebookToolbar view={view} filter={filter} query={query} onViewChange={setView} onFilterChange={setFilter} onQueryChange={setQuery} onStartNew={() => setCreating(true)} />
      {creating && !isPhone ? <View style={styles.inlineCreate}>{form}</View> : null}
      {error ? <View style={styles.error}><Text style={styles.errorText}>{error}</Text><Pressable onPress={() => void load(false)}><Text style={styles.retry}>Retry</Text></Pressable></View> : null}
      {loading ? <View style={styles.loading}><Text style={styles.loadingText}>Opening notebook…</Text></View> : <NotebookGrid floorId={floorId} view={view} rows={rows} saveStates={saveStates} onPatch={onPatch} onConvert={convert} onSelectRow={selectRow} />}
      {!loading && nextCursor ? <Pressable disabled={loadingMore} onPress={() => void load(true)} style={styles.more}><Text style={styles.moreText}>{loadingMore ? "Loading…" : "Load more rows"}</Text></Pressable> : null}
      {selected ? <View style={styles.timelinePanel}><View style={styles.timelineHead}><Text style={styles.timelineTitle}>{selected.customer_name}</Text><Text style={styles.timelineCaption}>Immutable notebook history</Text></View>{selectedTimeline.length ? selectedTimeline.map((event) => <View key={event.id} style={styles.event}><View style={styles.eventDot} /><View style={{ flex: 1 }}><Text style={styles.eventSummary}>{event.summary || event.event_type}</Text><Text style={styles.eventMeta}>{event.actor_name || "System"} · {new Date(event.created_at).toLocaleDateString("en-IN")}</Text></View></View>) : <Text style={styles.loadingText}>No history yet.</Text>}</View> : null}
      {isPhone ? <BottomSheet visible={creating} onClose={() => setCreating(false)} title="New Follow-up" testID="notebook-new-followup">{form}</BottomSheet> : null}
      </View>
    </View>
  );
}

function NewFollowupForm({ draft, setDraft, onCreate }: { draft: Draft; setDraft: React.Dispatch<React.SetStateAction<Draft>>; onCreate: () => void }) {
  const field = (key: keyof Draft, label: string, required = false, multiline = false) => <View style={styles.formField} key={key}><Text style={styles.formLabel}>{label}{required ? " *" : ""}</Text><TextInput value={draft[key]} onChangeText={(value) => setDraft((current) => ({ ...current, [key]: value }))} placeholder={label} placeholderTextColor={colors.onSurfaceSubtle} style={[styles.formInput, multiline && styles.formMultiline]} multiline={multiline} /></View>;
  return <View style={styles.form}><Text style={styles.formHint}>Required fields autosave the new row to the notebook.</Text>{field("customer_name", "Customer Name", true)}{field("customer_phone", "Mobile Number", true)}{field("address", "Address", false, true)}<View style={styles.formField}><Text style={styles.formLabel}>Kitchen Type *</Text><View style={styles.typeRow}>{(["GI", "SS"] as const).map((kind) => <Pressable key={kind} onPress={() => setDraft((current) => ({ ...current, kitchen_type: kind }))} style={[styles.typeButton, draft.kitchen_type === kind && styles.typeButtonActive]}><Text style={[styles.typeText, draft.kitchen_type === kind && styles.typeTextActive]}>{kind}</Text></Pressable>)}</View></View>{field("referred_by", "Referred By")}{field("architect_interior_designer", "Architect / Interior Designer")}{field("notes", "Notes", false, true)}<Pressable onPress={onCreate} disabled={!draft.customer_name.trim() || !draft.customer_phone.trim()} style={[styles.addButton, (!draft.customer_name.trim() || !draft.customer_phone.trim()) && styles.addButtonDisabled]}><Text style={styles.addButtonText}>Add to notebook</Text></Pressable></View>;
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.surface },
  pageContent: { flex: 1, padding: spacing.xl, gap: spacing.md, maxWidth: 1700, width: "100%", alignSelf: "center" },
  header: { flexDirection: "row", alignItems: "flex-start", marginBottom: spacing.sm },
  eyebrow: { ...type.caption, color: colors.onSurfaceMuted, letterSpacing: 1.6, fontWeight: "700" },
  title: { ...type.displayMd, color: colors.onSurface, marginTop: 4 },
  subtitle: { ...type.bodySm, color: colors.onSurfaceSecondary, marginTop: 5 },
  inlineCreate: { padding: spacing.lg, borderWidth: 1, borderColor: colors.brandBorder, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  form: { gap: spacing.sm },
  formHint: { ...type.caption, color: colors.onSurfaceMuted, marginBottom: 4 },
  formField: { gap: 4 },
  formLabel: { ...type.caption, color: colors.onSurfaceMuted, fontWeight: "700" },
  formInput: { minHeight: 42, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: 10, backgroundColor: colors.surfaceSecondary, ...type.bodySm },
  formMultiline: { minHeight: 68, paddingTop: 10, textAlignVertical: "top" },
  typeRow: { flexDirection: "row", gap: 8 },
  typeButton: { minHeight: 42, minWidth: 74, paddingHorizontal: 18, justifyContent: "center", alignItems: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  typeButtonActive: { borderColor: colors.brand, backgroundColor: colors.brandTint },
  typeText: { ...type.bodySm, color: colors.onSurfaceMuted, fontWeight: "700" },
  typeTextActive: { color: colors.brand },
  addButton: { alignSelf: "flex-start", minHeight: 44, paddingHorizontal: 18, justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.brand, marginTop: spacing.sm },
  addButtonDisabled: { opacity: 0.45 },
  addButtonText: { ...type.bodySm, color: colors.onBrand, fontWeight: "700" },
  loading: { minHeight: 260, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  loadingText: { ...type.bodySm, color: colors.onSurfaceMuted },
  error: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: spacing.md, borderRadius: radius.sm, backgroundColor: colors.errorBg },
  errorText: { ...type.bodySm, color: colors.error },
  retry: { ...type.bodySm, color: colors.brand, fontWeight: "700" },
  more: { alignSelf: "center", minHeight: 42, paddingHorizontal: spacing.lg, justifyContent: "center", borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.sm },
  moreText: { ...type.bodySm, color: colors.brand, fontWeight: "700" },
  timelinePanel: { marginTop: spacing.md, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  timelineHead: { marginBottom: spacing.md },
  timelineTitle: { ...type.titleSm, color: colors.onSurface },
  timelineCaption: { ...type.caption, color: colors.onSurfaceMuted, marginTop: 3 },
  event: { flexDirection: "row", gap: 10, paddingVertical: spacing.sm, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  eventDot: { width: 8, height: 8, borderRadius: 8, marginTop: 5, backgroundColor: colors.brand },
  eventSummary: { ...type.bodySm, color: colors.onSurface },
  eventMeta: { ...type.caption, color: colors.onSurfaceMuted, marginTop: 2 },
});
