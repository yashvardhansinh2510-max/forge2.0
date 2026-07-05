// Logged-in shell: tablet sidebar + phone bottom nav with center FAB.
// Consumes the BuildCon House design system tokens exclusively.

import { Feather } from "@expo/vector-icons";
import { Slot, useRouter, useSegments } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Avatar, BrandMark } from "@/src/components/ui";
import { useAuth } from "@/src/state/auth";
import { brand, colors, elevation, radius, roleLabels, spacing, type } from "@/src/theme/tokens";

type NavItem = {
  href: string;
  label: string;
  icon: keyof typeof Feather.glyphMap;
  match: string;
  minRole?: string[];
};

// Sidebar (tablet) navigation — broader surface area
const NAV: NavItem[] = [
  { href: "/(admin)/dashboard", label: "Dashboard",  icon: "grid",          match: "dashboard" },
  { href: "/(admin)/quotations", label: "Quotations", icon: "file-text",     match: "quotations" },
  { href: "/(admin)/catalog",    label: "Catalogue",  icon: "package",       match: "catalog" },
  { href: "/(admin)/customers",  label: "Customers",  icon: "users",         match: "customers" },
  { href: "/(admin)/purchases",  label: "Purchases",  icon: "shopping-cart", match: "purchases" },
  { href: "/(admin)/payments",   label: "Payments",   icon: "credit-card",   match: "payments" },
  { href: "/(admin)/followups",  label: "Follow-ups", icon: "bell",          match: "followups" },
  { href: "/(admin)/reports",    label: "Reports",    icon: "bar-chart-2",   match: "reports" },
];

const SECONDARY_NAV: NavItem[] = [
  { href: "/(admin)/notifications", label: "Notifications", icon: "bell", match: "notifications" },
  { href: "/(admin)/team", label: "Team", icon: "user-check", match: "team", minRole: ["owner", "admin", "manager"] },
  { href: "/(admin)/settings", label: "Settings", icon: "settings", match: "settings" },
];

// Bottom nav (phone) — 5 slots with center FAB.
// Slot 1 & 2 on left, FAB in middle, slot 4 & 5 on right.
const PHONE_LEFT: NavItem[] = [
  { href: "/(admin)/dashboard", label: "Home", icon: "home", match: "dashboard" },
  { href: "/(admin)/quotations", label: "Quotes", icon: "file-text", match: "quotations" },
];
const PHONE_RIGHT: NavItem[] = [
  { href: "/(admin)/notifications", label: "Alerts", icon: "bell", match: "notifications" },
  { href: "/(admin)/settings", label: "More", icon: "more-horizontal", match: "settings" },
];

export default function AdminLayout() {
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;
  const { staff, logout } = useAuth();
  const router = useRouter();
  const segments = useSegments();

  const isActive = (m: string) => segments.includes(m);

  const SidebarNavLink = ({ item, compact }: { item: NavItem; compact?: boolean }) => {
    const on = isActive(item.match);
    return (
      <Pressable
        testID={`nav-${item.match}`}
        onPress={() => router.push(item.href as any)}
        style={({ pressed }) => [{
          flexDirection: "row",
          alignItems: "center",
          gap: 12,
          paddingHorizontal: compact ? 0 : 12,
          paddingVertical: 10,
          borderRadius: radius.md,
          backgroundColor: on ? colors.brandTint : pressed ? colors.surfaceTertiary : "transparent",
          justifyContent: compact ? "center" : "flex-start",
        }]}
      >
        <Feather name={item.icon} size={17} color={on ? colors.brand : colors.onSurfaceSecondary} />
        {!compact ? (
          <Text style={{
            color: on ? colors.brand : colors.onSurface,
            fontSize: 14,
            fontFamily: type.titleMd.fontFamily,
            fontWeight: on ? "600" : "500",
            letterSpacing: -0.1,
          }}>
            {item.label}
          </Text>
        ) : null}
      </Pressable>
    );
  };

  const Sidebar = (
    <SafeAreaView edges={["top", "left", "bottom"]} style={styles.sidebar}>
      <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing.lg }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          <BrandMark size={34} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={{
              fontSize: 15,
              fontFamily: type.titleMd.fontFamily,
              fontWeight: "700",
              color: colors.onSurface,
              letterSpacing: -0.2,
            }} numberOfLines={1}>{brand.name}</Text>
            <Text style={type.caption} numberOfLines={1}>{brand.tagline}</Text>
          </View>
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: spacing.md, gap: 2 }}
        showsVerticalScrollIndicator={false}
      >
        <Text style={[type.overline, { marginLeft: 12, marginTop: 4, marginBottom: 6 }]}>Workspace</Text>
        {NAV.map((n) => <SidebarNavLink key={n.href} item={n} />)}
        <Text style={[type.overline, { marginLeft: 12, marginTop: spacing.lg, marginBottom: 6 }]}>General</Text>
        {SECONDARY_NAV.filter((n) => !n.minRole || (staff && n.minRole.includes(staff.role))).map((n) => (
          <SidebarNavLink key={n.href} item={n} />
        ))}
      </ScrollView>

      <View style={{ padding: spacing.md, gap: spacing.sm }}>
        <View style={{
          flexDirection: "row", alignItems: "center", gap: spacing.sm,
          backgroundColor: colors.surfaceTertiary,
          padding: spacing.sm, borderRadius: radius.md,
        }}>
          <Avatar name={staff?.full_name} size={34} tone="brand" />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={{
              fontSize: 13,
              fontFamily: type.titleMd.fontFamily,
              fontWeight: "600",
              color: colors.onSurface,
            }} numberOfLines={1}>{staff?.full_name}</Text>
            <Text style={type.caption} numberOfLines={1}>{roleLabels[staff?.role || ""] || staff?.role}</Text>
          </View>
          <Pressable
            testID="logout-button"
            onPress={async () => { await logout(); router.replace("/(auth)/login"); }}
            hitSlop={8}
          >
            <Feather name="log-out" size={16} color={colors.onSurfaceMuted} />
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );

  const BottomTab = ({ item }: { item: NavItem }) => {
    const on = isActive(item.match);
    return (
      <Pressable
        testID={`bottom-nav-${item.match}`}
        onPress={() => router.push(item.href as any)}
        style={styles.tabItem}
      >
        <Feather name={item.icon} size={22} color={on ? colors.brand : colors.onSurfaceMuted} />
        <Text style={{
          fontSize: 10,
          fontFamily: type.captionStrong.fontFamily,
          color: on ? colors.brand : colors.onSurfaceMuted,
          fontWeight: on ? "600" : "500",
          marginTop: 2,
        }}>
          {item.label}
        </Text>
      </Pressable>
    );
  };

  const BottomNav = (
    <View style={styles.bottomNavWrap}>
      <View style={styles.bottomNav}>
        {PHONE_LEFT.map((n) => <BottomTab key={n.href} item={n} />)}

        {/* Center FAB — New Quotation */}
        <View style={styles.fabSlot}>
          <Pressable
            testID="bottom-fab-new-quotation"
            onPress={() => router.push("/(admin)/quotations/new" as any)}
            style={({ pressed }) => [styles.fab, { transform: [{ scale: pressed ? 0.94 : 1 }] }]}
          >
            <Feather name="plus" size={26} color={colors.onBrand} />
          </Pressable>
        </View>

        {PHONE_RIGHT.map((n) => <BottomTab key={n.href} item={n} />)}
      </View>
    </View>
  );

  if (isTablet) {
    return (
      <View style={{ flex: 1, flexDirection: "row", backgroundColor: colors.surface }}>
        <View style={{
          width: 260,
          borderRightWidth: StyleSheet.hairlineWidth,
          borderColor: colors.border,
          backgroundColor: colors.surfaceSecondary,
        }}>
          {Sidebar}
        </View>
        <View style={{ flex: 1 }}>
          <Slot />
        </View>
      </View>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={{ flex: 1 }}>
        <Slot />
      </View>
      <SafeAreaView edges={["bottom"]} style={styles.bottomSafe}>
        {BottomNav}
      </SafeAreaView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  sidebar: {
    flex: 1,
    backgroundColor: colors.surfaceSecondary,
  },
  bottomSafe: {
    backgroundColor: colors.surfaceSecondary,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  bottomNavWrap: {
    backgroundColor: colors.surfaceSecondary,
  },
  bottomNav: {
    height: 64,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.sm,
  },
  tabItem: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 6,
  },
  fabSlot: {
    width: 72,
    alignItems: "center",
    justifyContent: "center",
  },
  fab: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
    marginTop: -18,
    ...elevation.medium,
    borderWidth: 4,
    borderColor: colors.surfaceSecondary,
  },
});
