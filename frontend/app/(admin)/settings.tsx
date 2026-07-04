import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Card } from "@/src/components/ui";
import { useAuth } from "@/src/state/auth";
import { colors, radius, roleLabels, spacing, type } from "@/src/theme/tokens";

export default function Settings() {
  const { staff, logout } = useAuth();
  const router = useRouter();

  const sections = [
    { title: "Profile", items: [
      { label: "Name", value: staff?.full_name },
      { label: "Email", value: staff?.email },
      { label: "Role", value: roleLabels[staff?.role || ""] },
    ] },
    { title: "Organization", items: [
      { label: "Company", value: "Forge Distributors Pvt Ltd" },
      { label: "Plan", value: "Founding — Unlimited" },
      { label: "Time zone", value: "Asia/Kolkata (GMT+5:30)" },
    ] },
  ];

  return (
    <AdminPage title="Settings" subtitle="Profile, organization & preferences.">
      {sections.map((s) => (
        <Card key={s.title} style={{ padding: 0 }}>
          <Text style={[type.overline, { padding: spacing.md, paddingBottom: 4 }]}>{s.title}</Text>
          {s.items.map((it, i) => (
            <View key={it.label} style={[styles.row, { borderTopWidth: i === 0 ? StyleSheet.hairlineWidth : StyleSheet.hairlineWidth, borderColor: colors.border }]}>
              <Text style={type.bodyMuted}>{it.label}</Text>
              <Text style={{ fontSize: 14, fontWeight: "500" }}>{it.value || "—"}</Text>
            </View>
          ))}
        </Card>
      ))}

      <Pressable
        testID="settings-logout"
        onPress={async () => { await logout(); router.replace("/(auth)/login"); }}
        style={styles.logout}
      >
        <Feather name="log-out" size={16} color={colors.error} />
        <Text style={{ color: colors.error, fontWeight: "600" }}>Sign out</Text>
      </Pressable>
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: spacing.md },
  logout: {
    flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8,
    padding: spacing.md, backgroundColor: colors.errorBg, borderRadius: radius.md,
  },
});
