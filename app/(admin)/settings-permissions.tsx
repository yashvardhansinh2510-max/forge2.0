// Settings > Team > Permissions — a read-only reference of what each role
// can do. Role data comes entirely from GET /api/roles (useRoles()) — this
// screen has never hardcoded a role list since the Team Management session;
// auth.ROLE_HIERARCHY/ROLE_LABELS/ROLE_CAPABILITIES on the backend is the
// single source of truth. Not an editor — roles are intentionally a fixed
// hierarchy, not a speculative dynamic-permissions builder.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { ActivityIndicator, ScrollView, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Card } from "@/src/components/ui";
import { useRoles } from "@/src/hooks/use-roles";
import { colors, spacing, type } from "@/src/theme/tokens";

export default function SettingsPermissions() {
  const router = useRouter();
  const { roles, loading } = useRoles();
  return (
    <AdminPage title="Roles & permissions" subtitle="Fixed hierarchy — enforced on every request" back={() => router.back()}>
      {loading && roles.length === 0 ? (
        <ActivityIndicator color={colors.onSurfaceMuted} />
      ) : (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: spacing.md }}>
          {roles.map((r) => (
            <Card key={r.role} style={{ gap: 6 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Feather name="shield" size={14} color={colors.brand} />
                  <Text style={type.bodyStrong}>{r.label}</Text>
                </View>
                <Text style={type.caption}>Level {r.level}</Text>
              </View>
              {r.capabilities.map((c, i) => (
                <Text key={i} style={type.bodyMuted}>• {c}</Text>
              ))}
            </Card>
          ))}
        </ScrollView>
      )}
    </AdminPage>
  );
}
