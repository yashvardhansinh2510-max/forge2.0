import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Card, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, spacing, type } from "@/src/theme/tokens";

type N = { id: string; title: string; body?: string; kind: "info" | "success" | "warning" | "error"; created_at: string; read: boolean };

export default function Notifications() {
  const [items, setItems] = useState<N[] | null>(null);
  useEffect(() => { api.get<N[]>("/notifications").then(setItems); }, []);
  return (
    <AdminPage title="Notifications" subtitle="Alerts, approvals & system events.">
      {!items ? (
        <Card style={{ padding: 0 }}>{Array.from({ length: 3 }).map((_, i) => <View key={i} style={styles.row}><Skeleton w="80%" /></View>)}</Card>
      ) : items.length === 0 ? (
        <EmptyState icon="bell" title="You're all caught up" subtitle="No notifications right now." />
      ) : (
        <Card style={{ padding: 0 }}>
          {items.map((n, i) => (
            <View key={n.id} style={[styles.row, { borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth, borderColor: colors.border }]}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 14, fontWeight: "600" }}>{n.title}</Text>
                {n.body ? <Text style={type.caption}>{n.body}</Text> : null}
              </View>
              <Text style={type.caption}>{new Date(n.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</Text>
            </View>
          ))}
        </Card>
      )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md },
});
