// Settings > Team > Permissions — a read-only reference of what each fixed
// role can do. The role hierarchy itself (auth.py ROLE_HIERARCHY) is enforced
// server-side on every request already; this screen only makes that existing
// enforcement legible in the UI. Not an editor — roles are intentionally a
// fixed hierarchy, not a speculative dynamic-permissions builder.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { ScrollView, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Card } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme/tokens";

const ROLES: { role: string; label: string; level: number; can: string[] }[] = [
  { role: "owner", label: "Owner", level: 100, can: ["Everything, including team management and settings"] },
  { role: "admin", label: "Admin", level: 90, can: ["Team management", "Company & PDF settings", "Catalog backup/export"] },
  { role: "manager", label: "Manager", level: 70, can: ["View team", "Approve catalog imports", "Full sales & purchase access"] },
  { role: "accounts", label: "Accounts", level: 60, can: ["Payments & receivables", "Financial reporting"] },
  { role: "purchase", label: "Purchase", level: 50, can: ["Purchase orders", "Catalog imports", "Supplier management"] },
  { role: "sales", label: "Sales", level: 40, can: ["Quotations", "Customers", "Follow-ups"] },
  { role: "warehouse", label: "Warehouse", level: 30, can: ["Stock movements", "Purchase receiving"] },
  { role: "worker", label: "Worker", level: 10, can: ["View-only access to assigned tasks"] },
];

export default function SettingsPermissions() {
  const router = useRouter();
  return (
    <AdminPage title="Roles & permissions" subtitle="Fixed hierarchy — enforced on every request" back={() => router.back()}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: spacing.md }}>
        {ROLES.map((r) => (
          <Card key={r.role} style={{ gap: 6 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Feather name="shield" size={14} color={colors.brand} />
                <Text style={type.bodyStrong}>{r.label}</Text>
              </View>
              <Text style={type.caption}>Level {r.level}</Text>
            </View>
            {r.can.map((c, i) => (
              <Text key={i} style={type.bodyMuted}>• {c}</Text>
            ))}
          </Card>
        ))}
      </ScrollView>
    </AdminPage>
  );
}
