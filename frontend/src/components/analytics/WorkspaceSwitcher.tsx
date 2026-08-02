import { usePathname, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme/tokens";

type Member = {
  label: string;
  route: string;
  /** False while the workspace is on the roadmap but not yet built. Those
   *  entries stay in the navigation — the architecture is the final one — but
   *  route to the Coming Soon placeholder instead of an unmatched route. */
  implemented: boolean;
};
type Group = { key: string; label: string; members: Member[] };

const COMING_SOON_ROUTE = "/(admin)/sales-data/coming-soon";

/**
 * Navigation grouped by the question the owner is asking, not by engineering
 * boundary (spec §16.2). Routes and backend services are unchanged by this
 * grouping — it is presentation only.
 *
 * This list is the complete Sales Data architecture, not just what ships
 * today. Milestone 4 builds the launch dashboard and the workspaces marked
 * `implemented: true`; the rest are real roadmap entries that already have
 * their place in the navigation, so a later milestone adds a screen and flips
 * one flag rather than requiring another navigation redesign.
 *
 * Each group opens to its first implemented member, so a click is never spent
 * on a menu and never lands on a placeholder when real data is one tap away.
 */
export const WORKSPACE_GROUPS: Group[] = [
  { key: "overview", label: "Overview", members: [
    { label: "Sales Data", route: "/(admin)/sales-data", implemented: true },
    { label: "Executive", route: "/(admin)/sales-data/executive", implemented: true },
    { label: "Today's Priorities", route: "/(admin)/sales-data/today", implemented: true },
  ] },
  { key: "money", label: "Money", members: [
    { label: "Revenue", route: "/(admin)/sales-data/sales", implemented: false },
    { label: "Collections", route: "/(admin)/sales-data/collections", implemented: false },
    { label: "Forecasting", route: "/(admin)/sales-data/forecasting", implemented: false },
  ] },
  { key: "customers", label: "Customers", members: [
    { label: "Customers", route: "/(admin)/sales-data/customers", implemented: false },
    { label: "Architects", route: "/(admin)/sales-data/referrals/architects", implemented: false },
    { label: "Interior Designers", route: "/(admin)/sales-data/referrals/interior-designers", implemented: false },
    { label: "Relationships", route: "/(admin)/sales-data/relationships", implemented: false },
  ] },
  { key: "products", label: "Products", members: [
    { label: "Products", route: "/(admin)/sales-data/products", implemented: false },
    { label: "Brands", route: "/(admin)/sales-data/brands", implemented: false },
    { label: "Suppliers", route: "/(admin)/sales-data/suppliers", implemented: false },
  ] },
  { key: "operations", label: "Operations", members: [
    { label: "Operations", route: "/(admin)/sales-data/operations", implemented: false },
  ] },
];

/** Where a member actually navigates. An unbuilt workspace goes to the
 *  placeholder carrying its own name, never to an unmatched route. */
export function destinationFor(member: Member): string {
  return member.implemented
    ? member.route
    : `${COMING_SOON_ROUTE}?workspace=${encodeURIComponent(member.label)}`;
}

export function WorkspaceSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  // `/sales-data` is a prefix of every other workspace route, so matching it
  // by `startsWith` would light up the Overview group on every screen in the
  // module. The launch dashboard is matched exactly instead.
  const isActiveMember = (member: Member) => {
    const path = member.route.replace("/(admin)", "");
    return path === "/sales-data" ? pathname === path : pathname.startsWith(path);
  };
  const activeGroup = WORKSPACE_GROUPS.find((g) => g.members.some(isActiveMember));

  const openMember = (member: Member) => router.push(destinationFor(member) as never);

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
                // Opens to the first member that actually exists, falling back
                // to the first entry when the whole group is still roadmap.
                openMember(group.members.find((m) => m.implemented) || group.members[0]);
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
              accessibilityLabel={member.implemented ? member.label : `${member.label} — coming soon`}
              onPress={() => openMember(member)}
              style={{
                minHeight: 44,
                justifyContent: "center",
                paddingHorizontal: spacing.md,
                flexDirection: "row",
                alignItems: "center",
                gap: 6,
              }}
            >
              <Text style={[type.body, member.implemented ? null : { color: colors.onSurfaceMuted }]}>
                {member.label}
              </Text>
              {member.implemented ? null : (
                <View style={{
                  paddingHorizontal: 6,
                  paddingVertical: 1,
                  borderRadius: radius.pill,
                  backgroundColor: colors.surfaceTertiary,
                }}>
                  <Text style={{ fontSize: 9, fontFamily: type.titleMd.fontFamily, fontWeight: "700", color: colors.onSurfaceMuted }}>
                    SOON
                  </Text>
                </View>
              )}
            </Pressable>
          ))}
        </ScrollView>
      ) : null}
    </View>
  );
}
