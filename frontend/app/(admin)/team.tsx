import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Badge, Card, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, roleLabels, spacing, type } from "@/src/theme/tokens";

type U = { id: string; full_name: string; email: string; role: string; active: boolean };

export default function Team() {
  const [items, setItems] = useState<U[] | null>(null);
  useEffect(() => { api.get<U[]>("/team").then(setItems).catch(() => setItems([])); }, []);

  return (
    <AdminPage title="Team" subtitle="Roles, access & performance.">
      {!items ? <Card style={{ padding: 0 }}>{Array.from({ length: 4 }).map((_, i) => <View key={i} style={styles.row}><Skeleton w="60%" /></View>)}</Card>
        : items.length === 0 ? <EmptyState icon="user-check" title="No team members" subtitle="Only Manager / Admin / Owner can access team management." />
        : (
          <Card style={{ padding: 0 }}>
            {items.map((u, i) => (
              <View key={u.id} style={[styles.row, { borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth, borderColor: colors.border }]}>
                <View style={styles.avatar}><Text style={{ color: colors.onBrand, fontWeight: "700" }}>{u.full_name[0]}</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 14, fontWeight: "600" }}>{u.full_name}</Text>
                  <Text style={type.caption}>{u.email}</Text>
                </View>
                <Badge label={roleLabels[u.role] || u.role} />
              </View>
            ))}
          </Card>
        )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md },
  avatar: { width: 36, height: 36, borderRadius: 999, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
});
