// BuildCon House · Follow-up Assignments — manager-only view of who has
// what assigned, how long it's been pending, and whether it's done.
// Backend: GET /followups/assignments (require_min_role("manager")).
import { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Avatar, Badge, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { useAuth } from "@/src/state/auth";
import { colors, spacing, type } from "@/src/theme/tokens";

type AssignmentRow = {
  id: string; assigned_to: string | null; assigned_to_name: string | null;
  customer_name: string; reason: string; category: string;
  status: "open" | "snoozed" | "done" | "dismissed"; bucket: string;
  days_pending: number; due_at: string; created_at: string;
};

const STATUS_TONE: Record<string, "brand" | "warning" | "success" | "neutral"> = {
  open: "brand", snoozed: "warning", done: "success", dismissed: "neutral",
};

const MANAGER_ROLES = ["owner", "admin", "manager"];

export default function FollowupAssignments() {
  const { staff } = useAuth();
  const [rows, setRows] = useState<AssignmentRow[] | null>(null);

  const load = useCallback(() => {
    api.get<AssignmentRow[]>("/followups/assignments")
      .then(setRows)
      .catch((e: any) => { toast.error(e?.detail || "Could not load assignments"); setRows([]); });
  }, []);

  useEffect(() => { load(); }, [load]);

  const allowed = !!staff && MANAGER_ROLES.includes(staff.role);
  if (!allowed) {
    return (
      <AdminPage title="Follow-up Assignments" overline="TEAM">
        <EmptyState icon="lock" title="Manager access only" subtitle="Ask an owner, admin or manager to share this view." />
      </AdminPage>
    );
  }

  return (
    <AdminPage title="Follow-up Assignments" overline="TEAM" subtitle="Who has what, how long it's been pending, and whether it's done.">
      {rows === null ? (
        <View style={{ gap: spacing.md }}>
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} h={56} />)}
        </View>
      ) : rows.length === 0 ? (
        <EmptyState icon="user-check" title="Nothing assigned" subtitle="Assignments will appear here once follow-ups are handed to someone." />
      ) : (
        <View style={styles.table}>
          {rows.map((r, i) => (
            <View key={r.id} style={[styles.row, i > 0 ? styles.rowBorder : null]}>
              <Avatar name={r.assigned_to_name || "—"} size={34} tone="brand" />
              <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                <Text style={type.bodyStrong} numberOfLines={1}>{r.assigned_to_name || "Unassigned"}</Text>
                <Text style={type.caption} numberOfLines={1}>{r.customer_name} · {r.reason}</Text>
              </View>
              <Text style={[type.bodySm, { width: 90, textAlign: "right" }]}>
                {r.days_pending} day{r.days_pending === 1 ? "" : "s"}
              </Text>
              <Badge label={r.status} tone={STATUS_TONE[r.status] || "neutral"} size="sm" />
            </View>
          ))}
        </View>
      )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  table: {
    borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, overflow: "hidden",
  },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.lg,
  },
  rowBorder: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
});
