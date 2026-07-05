// Scaffold factory — production-ready empty screens for modules that will ship next.
import { Feather } from "@expo/vector-icons";
import { StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Card } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

export function ScaffoldScreen({
  title, subtitle, icon, features,
}: {
  title: string; subtitle: string; icon: keyof typeof Feather.glyphMap;
  features: string[];
}) {
  return (
    <AdminPage title={title} subtitle={subtitle}>
      <Card style={styles.hero}>
        <View style={styles.iconWrap}>
          <Feather name={icon} size={26} color={colors.brand} />
        </View>
        <Text style={[type.titleLg, { marginTop: spacing.md }]}>Coming in the next iteration</Text>
        <Text style={[type.bodyMuted, { textAlign: "center", maxWidth: 480, marginTop: 4 }]}>
          Data models, RBAC and API contracts for {title.toLowerCase()} are already in place. UI polish ships next.
        </Text>
        <View style={{ marginTop: spacing.lg, gap: 8, alignSelf: "stretch" }}>
          {features.map((f) => (
            <View key={f} style={styles.featRow}>
              <Feather name="check" size={14} color={colors.success} />
              <Text style={type.body}>{f}</Text>
            </View>
          ))}
        </View>
      </Card>
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  hero: { alignItems: "center", padding: spacing.xxl },
  iconWrap: {
    width: 60, height: 60, borderRadius: radius.lg, backgroundColor: colors.brandTint,
    alignItems: "center", justifyContent: "center",
  },
  featRow: { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, backgroundColor: colors.surfaceTertiary, borderRadius: radius.md },
});
