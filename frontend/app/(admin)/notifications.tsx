// BuildCon House · Notifications
import { Feather } from "@expo/vector-icons";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type N = {
  id: string;
  title: string;
  body?: string;
  kind: "info" | "success" | "warning" | "error";
  created_at: string;
  read: boolean;
};

const iconMap = {
  info:    { icon: "info" as const,          bg: colors.infoBg,    fg: colors.info },
  success: { icon: "check-circle" as const,  bg: colors.successBg, fg: colors.success },
  warning: { icon: "alert-triangle" as const, bg: colors.warningBg, fg: colors.warning },
  error:   { icon: "x-circle" as const,      bg: colors.errorBg,   fg: colors.error },
};

export default function Notifications() {
  const [items, setItems] = useState<N[] | null>(null);
  useEffect(() => { api.get<N[]>("/notifications").then(setItems).catch(() => setItems([])); }, []);

  const unread = (items || []).filter((n) => !n.read).length;

  return (
    <AdminPage
      title="Notifications"
      subtitle={unread ? `${unread} unread · alerts & approvals` : "You’re all caught up"}
    >
      {!items ? (
        <View style={{ gap: spacing.sm }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <View key={i} style={[styles.card, { flexDirection: "row", gap: spacing.md }]}>
              <Skeleton w={40} h={40} radius={20} />
              <View style={{ flex: 1, gap: 6 }}>
                <Skeleton w="70%" h={14} />
                <Skeleton w="50%" h={12} />
              </View>
            </View>
          ))}
        </View>
      ) : items.length === 0 ? (
        <EmptyState icon="bell" title="You're all caught up" subtitle="No notifications right now." />
      ) : (
        <View style={{ gap: spacing.sm }}>
          {items.map((n) => {
            const skin = iconMap[n.kind] || iconMap.info;
            return (
              <View
                key={n.id}
                style={[styles.card, {
                  flexDirection: "row",
                  gap: spacing.md,
                  borderColor: n.read ? colors.border : colors.brandBorder,
                  backgroundColor: n.read ? colors.surfaceSecondary : colors.brandTint + "80",
                }]}
              >
                <View style={[styles.iconWrap, { backgroundColor: skin.bg }]}>
                  <Feather name={skin.icon} size={16} color={skin.fg} />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm }}>
                    <Text style={{
                      fontSize: 14,
                      fontFamily: type.titleMd.fontFamily,
                      fontWeight: "600",
                      color: colors.onSurface,
                      flex: 1,
                      minWidth: 0,
                    }} numberOfLines={1}>
                      {n.title}
                    </Text>
                    <Text style={type.caption}>
                      {new Date(n.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                    </Text>
                  </View>
                  {n.body ? (
                    <Text style={[type.bodyMuted, { marginTop: 2, fontSize: 13 }]} numberOfLines={2}>
                      {n.body}
                    </Text>
                  ) : null}
                </View>
                {!n.read ? <View style={styles.unreadDot} /> : null}
              </View>
            );
          })}
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
    alignItems: "flex-start",
  },
  iconWrap: {
    width: 36, height: 36, borderRadius: 10,
    alignItems: "center", justifyContent: "center",
  },
  unreadDot: {
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: colors.brand,
    marginTop: 6,
  },
});
