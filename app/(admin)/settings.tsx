// BuildCon House · Settings
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Avatar, Card } from "@/src/components/ui";
import { useAuth } from "@/src/state/auth";
import { brand, colors, radius, roleLabels, spacing, type } from "@/src/theme/tokens";

export default function Settings() {
  const { staff, logout } = useAuth();
  const router = useRouter();

  const sections = [
    { title: "Profile", items: [
      { label: "Name", value: staff?.full_name, icon: "user" as const },
      { label: "Email", value: staff?.email, icon: "mail" as const },
      { label: "Role", value: roleLabels[staff?.role || ""], icon: "shield" as const },
    ] },
    { title: "Organization", items: [
      { label: "Company", value: brand.name, icon: "home" as const },
      { label: "Plan", value: "Founding — Unlimited", icon: "star" as const },
      { label: "Time zone", value: "Asia/Kolkata (GMT+5:30)", icon: "clock" as const },
    ] },
  ];

  return (
    <AdminPage title="Settings" subtitle="Profile, organization & preferences">
      {/* Profile hero */}
      <View style={styles.hero}>
        <Avatar name={staff?.full_name} size={64} tone="brand" />
        <View style={{ alignItems: "center", gap: 4 }}>
          <Text style={type.titleLg}>{staff?.full_name || "—"}</Text>
          <Text style={type.bodyMuted}>{staff?.email}</Text>
          <View style={styles.rolePill}>
            <Feather name="shield" size={11} color={colors.brand} />
            <Text style={styles.rolePillText}>{roleLabels[staff?.role || ""] || staff?.role || "Team"}</Text>
          </View>
        </View>
      </View>

      {sections.map((s) => (
        <Card key={s.title} style={{ padding: 0 }} variant="flat">
          <Text style={[type.overline, { padding: spacing.md, paddingBottom: 8 }]}>{s.title}</Text>
          {s.items.map((it, i) => (
            <View
              key={it.label}
              style={[styles.row, i === 0 ? null : { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.divider }]}
            >
              <View style={styles.itemIcon}>
                <Feather name={it.icon} size={14} color={colors.onSurfaceMuted} />
              </View>
              <Text style={[type.bodyMuted, { flex: 1 }]}>{it.label}</Text>
              <Text style={{
                fontSize: 14,
                fontFamily: type.bodyStrong.fontFamily,
                fontWeight: "500",
                color: colors.onSurface,
              }}>{it.value || "—"}</Text>
            </View>
          ))}
        </Card>
      ))}

      <Pressable
        testID="settings-logout"
        onPress={async () => { await logout(); router.replace("/(auth)/login"); }}
        style={({ pressed }) => [styles.logout, { opacity: pressed ? 0.88 : 1 }]}
      >
        <Feather name="log-out" size={16} color={colors.error} />
        <Text style={{
          color: colors.error,
          fontSize: 14,
          fontFamily: type.titleMd.fontFamily,
          fontWeight: "600",
        }}>Sign out</Text>
      </Pressable>

      <Text style={[type.caption, { textAlign: "center", marginTop: spacing.sm }]}>
        {brand.name} · {brand.tagline}
      </Text>
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  hero: {
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  rolePill: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill,
    backgroundColor: colors.brandTint,
    marginTop: 4,
  },
  rolePillText: {
    fontSize: 11,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "600",
    color: colors.brand,
    letterSpacing: 0.1,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
  },
  itemIcon: {
    width: 32, height: 32, borderRadius: 10,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center", justifyContent: "center",
  },
  logout: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 8,
    padding: spacing.md,
    backgroundColor: colors.errorBg,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.errorBorder,
  },
});
