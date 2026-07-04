// Custom sidebar navigation (tablet) + bottom tab (phone).
// Uses expo-router's <Slot> for content so every child screen renders inside.
import { Feather } from "@expo/vector-icons";
import { Slot, useRouter, useSegments } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "@/src/state/auth";
import { colors, radius, roleLabels, spacing, type } from "@/src/theme/tokens";

type NavItem = {
  href: string;
  label: string;
  icon: keyof typeof Feather.glyphMap;
  match: string;                // segment to match for "active" state
  minRole?: string[];
};

const NAV: NavItem[] = [
  { href: "/(admin)/dashboard", label: "Dashboard", icon: "grid", match: "dashboard" },
  { href: "/(admin)/quotations", label: "Quotations", icon: "file-text", match: "quotations" },
  { href: "/(admin)/catalog", label: "Catalog", icon: "package", match: "catalog" },
  { href: "/(admin)/customers", label: "Customers", icon: "users", match: "customers" },
  { href: "/(admin)/purchase-orders", label: "Purchase", icon: "shopping-cart", match: "purchase-orders" },
  { href: "/(admin)/payments", label: "Payments", icon: "credit-card", match: "payments" },
  { href: "/(admin)/followups", label: "Follow-ups", icon: "bell", match: "followups" },
  { href: "/(admin)/reports", label: "Reports", icon: "bar-chart-2", match: "reports" },
];

const BOTTOM_NAV: NavItem[] = [
  { href: "/(admin)/notifications", label: "Notifications", icon: "message-square", match: "notifications" },
  { href: "/(admin)/team", label: "Team", icon: "user-check", match: "team", minRole: ["owner", "admin", "manager"] },
  { href: "/(admin)/settings", label: "Settings", icon: "settings", match: "settings" },
];

export default function AdminLayout() {
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;
  const { staff, logout } = useAuth();
  const router = useRouter();
  const segments = useSegments();
  const active = segments[segments.length - 1] || segments[1] || "";

  const isActive = (m: string) => segments.includes(m);

  const initials = (staff?.full_name || "?")
    .split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

  const NavLink = ({ item, compact }: { item: NavItem; compact?: boolean }) => {
    const on = isActive(item.match);
    return (
      <Pressable
        testID={`nav-${item.match}`}
        onPress={() => router.push(item.href as any)}
        style={({ pressed }) => [{
          flexDirection: "row", alignItems: "center", gap: 12,
          paddingHorizontal: compact ? 0 : 12, paddingVertical: 10, borderRadius: radius.md,
          backgroundColor: on ? colors.brand : pressed ? colors.surfaceTertiary : "transparent",
          justifyContent: compact ? "center" : "flex-start",
        }]}
      >
        <Feather name={item.icon} size={17} color={on ? colors.onBrand : colors.onSurfaceSecondary} />
        {!compact ? (
          <Text style={{ color: on ? colors.onBrand : colors.onSurface, fontSize: 14, fontWeight: on ? "600" : "500" }}>
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
          <View style={styles.brandMark}><Text style={styles.brandMarkText}>F</Text></View>
          <View>
            <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface, letterSpacing: 1.2 }}>FORGE</Text>
            <Text style={type.caption}>Distributor OS</Text>
          </View>
        </View>
      </View>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingHorizontal: spacing.md, gap: 2 }} showsVerticalScrollIndicator={false}>
        <Text style={[type.overline, { marginLeft: 12, marginTop: 4, marginBottom: 6 }]}>Workspace</Text>
        {NAV.map((n) => <NavLink key={n.href} item={n} />)}
        <Text style={[type.overline, { marginLeft: 12, marginTop: spacing.lg, marginBottom: 6 }]}>General</Text>
        {BOTTOM_NAV.filter((n) => !n.minRole || (staff && n.minRole.includes(staff.role))).map((n) => <NavLink key={n.href} item={n} />)}
      </ScrollView>

      <View style={{ padding: spacing.md, gap: spacing.sm }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceTertiary, padding: spacing.sm, borderRadius: radius.md }}>
          <View style={styles.avatar}><Text style={styles.avatarText}>{initials}</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{staff?.full_name}</Text>
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

  const BottomTabs = (
    <View style={styles.bottomTabs}>
      {[NAV[0], NAV[1], NAV[2], NAV[3], BOTTOM_NAV[BOTTOM_NAV.length - 1]].map((n) => (
        <Pressable
          key={n.href}
          testID={`bottom-nav-${n.match}`}
          onPress={() => router.push(n.href as any)}
          style={{ flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: 8, gap: 3 }}
        >
          <Feather name={n.icon} size={20} color={isActive(n.match) ? colors.brand : colors.onSurfaceMuted} />
          <Text style={{ fontSize: 10, color: isActive(n.match) ? colors.brand : colors.onSurfaceMuted, fontWeight: "500" }}>
            {n.label}
          </Text>
        </Pressable>
      ))}
    </View>
  );

  if (isTablet) {
    return (
      <View style={{ flex: 1, flexDirection: "row", backgroundColor: colors.surface }}>
        <View style={{ width: 244, borderRightWidth: StyleSheet.hairlineWidth, borderColor: colors.border, backgroundColor: colors.surfaceSecondary }}>
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
      <SafeAreaView edges={["bottom"]} style={{ backgroundColor: colors.surfaceSecondary, borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border }}>
        {BottomTabs}
      </SafeAreaView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  sidebar: { flex: 1, backgroundColor: colors.surfaceSecondary },
  brandMark: {
    width: 30, height: 30, borderRadius: 8, backgroundColor: colors.brand,
    alignItems: "center", justifyContent: "center",
  },
  brandMarkText: { color: colors.onBrand, fontSize: 14, fontWeight: "700" },
  avatar: {
    width: 32, height: 32, borderRadius: 999, backgroundColor: colors.brand,
    alignItems: "center", justifyContent: "center",
  },
  avatarText: { color: colors.onBrand, fontSize: 12, fontWeight: "700" },
  bottomTabs: {
    flexDirection: "row", height: 56, backgroundColor: colors.surfaceSecondary,
  },
});
