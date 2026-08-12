// ScaffoldScreen — premium "coming next iteration" surface for modules whose
// UI hasn't shipped yet. Composed from the shared DS (HeroBanner + Card + Badge).
// Every scaffold screen looks identical to the rest of the app.
import { Feather } from "@expo/vector-icons";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Badge, HeroBanner, PageHeader } from "@/src/components/ui";
import { colors, icon as iconSize, radius, spacing, type } from "@/src/theme/tokens";

export function ScaffoldScreen({
  title, subtitle, icon, features, overline,
}: {
  title: string;
  subtitle: string;
  icon: keyof typeof Feather.glyphMap;
  features: string[];
  overline?: string;
}) {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <PageHeader title={title} subtitle={subtitle} overline={overline || "IN PROGRESS"} />
      <ScrollView
        contentContainerStyle={{
          padding: spacing.xl,
          gap: spacing.lg,
          paddingBottom: spacing.xxxl,
        }}
        showsVerticalScrollIndicator={false}
      >
        <HeroBanner
          overline="COMING IN THE NEXT ITERATION"
          title={`${title} — under construction`}
          subtitle="Data models, RBAC and API contracts are already in place. The UI ships as part of the Phase 4 workflow polish."
          icon={icon}
        />

        <View style={styles.card}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md }}>
            <Text style={type.overline}>What&apos;s planned</Text>
            <Badge label={`${features.length} milestones`} tone="brand" size="sm" />
          </View>
          <View style={{ gap: spacing.sm }}>
            {features.map((f, i) => (
              <View key={i} style={styles.featRow}>
                <View style={styles.featIcon}>
                  <Feather name="check" size={iconSize.sm} color={colors.success} />
                </View>
                <Text style={[type.body, { flex: 1 }]}>{f}</Text>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: spacing.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  featRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surfaceSubtle,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  featIcon: {
    width: 28,
    height: 28,
    borderRadius: radius.sm,
    backgroundColor: colors.successBg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.successBorder,
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
});
