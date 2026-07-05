// BuildCon House · Team
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Avatar, Badge, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, radius, roleLabels, spacing, type } from "@/src/theme/tokens";

type U = { id: string; full_name: string; email: string; role: string; active: boolean };

export default function Team() {
  const [items, setItems] = useState<U[] | null>(null);
  useEffect(() => { api.get<U[]>("/team").then(setItems).catch(() => setItems([])); }, []);

  return (
    <AdminPage title="Team" subtitle="Roles, access & performance">
      {!items ? (
        <View style={{ gap: spacing.sm }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <View key={i} style={[styles.card, { flexDirection: "row", gap: spacing.md }]}>
              <Skeleton w={44} h={44} radius={22} />
              <View style={{ flex: 1, gap: 6 }}>
                <Skeleton w="60%" h={14} />
                <Skeleton w="40%" h={12} />
              </View>
            </View>
          ))}
        </View>
      ) : items.length === 0 ? (
        <EmptyState icon="user-check" title="No team members" subtitle="Only Manager, Admin & Owner roles can access team management." />
      ) : (
        <View style={{ gap: spacing.sm }}>
          {items.map((u) => (
            <View key={u.id} style={[styles.card, { flexDirection: "row", gap: spacing.md, alignItems: "center" }]}>
              <Avatar name={u.full_name} size={44} tone="brand" />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text numberOfLines={1} style={{
                  fontSize: 15,
                  fontFamily: type.titleMd.fontFamily,
                  fontWeight: "600",
                  color: colors.onSurface,
                  letterSpacing: -0.1,
                }}>{u.full_name}</Text>
                <Text numberOfLines={1} style={type.caption}>{u.email}</Text>
              </View>
              <View style={{ alignItems: "flex-end", gap: 4 }}>
                <Badge label={roleLabels[u.role] || u.role} tone={u.active ? "brand" : "neutral"} size="sm" />
                {!u.active ? <Badge label="Inactive" tone="warning" size="sm" /> : null}
              </View>
            </View>
          ))}
        </View>
      )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
  },
});
