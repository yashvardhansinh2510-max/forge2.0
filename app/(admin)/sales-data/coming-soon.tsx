import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { WORKSPACE_GROUPS } from "@/src/components/analytics/WorkspaceSwitcher";
import { Badge, Button, Card, EmptyState } from "@/src/components/ui";
import { useAuth } from "@/src/state/auth";
import { colors, spacing, type } from "@/src/theme/tokens";

const ANALYTICS_ROLES = ["owner", "admin", "manager"];

/**
 * The landing place for a Sales Data workspace that is on the roadmap but
 * not yet built.
 *
 * It exists so the navigation can already carry the complete Sales Data
 * architecture without any entry leading to an "Unmatched route" screen.
 * Every workspace in `WORKSPACE_GROUPS` marked `implemented: false` routes
 * here with its own label, so shipping one later is a one-line change in
 * that list plus the real screen — no navigation redesign, and nothing to
 * throw away.
 */
export default function ComingSoonWorkspace() {
  const { staff } = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{ workspace?: string }>();

  const label = params.workspace || "This workspace";
  const planned = WORKSPACE_GROUPS
    .flatMap((group) => group.members)
    .filter((member) => !member.implemented)
    .map((member) => member.label);

  if (staff && !ANALYTICS_ROLES.includes(staff.role)) {
    return <Redirect href="/(admin)/dashboard" />;
  }

  return (
    <AdminPage title={label} subtitle="Planned — not yet available">
      <EmptyState
        icon="clock"
        tone="brand"
        title={`${label} is coming soon`}
        subtitle="The launch dashboard covers revenue, orders, payments, brands, customers, products, referrals and recent orders. This workspace builds on the same data and arrives in a later milestone."
        action={
          <Button
            label="Back to Sales Data"
            icon="arrow-left"
            onPress={() => router.push("/(admin)/sales-data" as never)}
          />
        }
      />

      <Card testID="coming-soon-roadmap" variant="flat" padding={spacing.xl}>
        <View style={{ gap: spacing.md }}>
          <Text style={type.titleSm}>Also planned</Text>
          <Text style={[type.caption, { color: colors.onSurfaceMuted }]}>
            Every one of these reuses the analytics foundation already in place.
          </Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {planned.map((name) => (
              <Badge key={name} label={name} tone={name === label ? "brand" : "neutral"} />
            ))}
          </View>
        </View>
      </Card>
    </AdminPage>
  );
}
