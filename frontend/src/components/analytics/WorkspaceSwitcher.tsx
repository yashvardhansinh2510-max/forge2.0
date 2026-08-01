import { usePathname, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme/tokens";

type Member = { label: string; route: string };
type Group = { key: string; label: string; members: Member[] };

/**
 * Navigation grouped by the question the owner is asking, not by engineering
 * boundary (spec §16.2). Routes and backend services are unchanged by this
 * grouping — it is presentation only.
 *
 * Each group opens to its first member, so a click is never spent on a menu.
 */
export const WORKSPACE_GROUPS: Group[] = [
  { key: "overview", label: "Overview", members: [
    { label: "Executive", route: "/(admin)/sales-data/executive" },
    { label: "Today's Priorities", route: "/(admin)/sales-data/today" },
  ] },
  { key: "money", label: "Money", members: [
    { label: "Revenue", route: "/(admin)/sales-data/sales" },
    { label: "Collections", route: "/(admin)/sales-data/collections" },
    { label: "Forecasting", route: "/(admin)/sales-data/forecasting" },
  ] },
  { key: "customers", label: "Customers", members: [
    { label: "Customers", route: "/(admin)/sales-data/customers" },
    { label: "Architects", route: "/(admin)/sales-data/referrals/architects" },
    { label: "Interior Designers", route: "/(admin)/sales-data/referrals/interior-designers" },
    { label: "Relationships", route: "/(admin)/sales-data/relationships" },
  ] },
  { key: "products", label: "Products", members: [
    { label: "Products", route: "/(admin)/sales-data/products" },
    { label: "Brands", route: "/(admin)/sales-data/brands" },
    { label: "Suppliers", route: "/(admin)/sales-data/suppliers" },
  ] },
  { key: "operations", label: "Operations", members: [
    { label: "Operations", route: "/(admin)/sales-data/operations" },
  ] },
];

export function WorkspaceSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  const activeGroup = WORKSPACE_GROUPS.find((g) => g.members.some((m) => pathname.startsWith(m.route.replace("/(admin)", ""))));

  return (
    <View style={{ gap: spacing.xs }}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
        {WORKSPACE_GROUPS.map((group) => {
          const isActive = activeGroup?.key === group.key;
          return (
            <Pressable
              key={group.key}
              testID={`workspace-group-${group.key}`}
              accessibilityLabel={group.label}
              onPress={() => {
                setOpenGroup(group.members.length > 1 ? (openGroup === group.key ? null : group.key) : null);
                router.push(group.members[0].route as never);
              }}
              style={{
                minHeight: 44,
                justifyContent: "center",
                paddingHorizontal: spacing.md,
                borderRadius: radius.pill,
                backgroundColor: isActive ? colors.brand : "transparent",
              }}
            >
              <Text style={[type.bodyStrong, { color: isActive ? colors.onBrand : colors.onSurface }]}>{group.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {openGroup ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
          {WORKSPACE_GROUPS.find((g) => g.key === openGroup)!.members.map((member) => (
            <Pressable
              key={member.route}
              testID={`workspace-member-${member.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
              accessibilityLabel={member.label}
              onPress={() => router.push(member.route as never)}
              style={{ minHeight: 44, justifyContent: "center", paddingHorizontal: spacing.md }}
            >
              <Text style={type.body}>{member.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      ) : null}
    </View>
  );
}
