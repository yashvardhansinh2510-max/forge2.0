// ─────────────────────────────────────────────────────────────────────────────
// BuildCon House · Shell.
// Desktop: quiet 240px sidebar. Tablet: 64px icon rail. Phone: bottom bar.
// One brass bar marks where you are. The command palette lives here (⌘K).
// ─────────────────────────────────────────────────────────────────────────────
import { Feather } from "@expo/vector-icons";
import { Slot, useRouter, useSegments } from "expo-router";
import React, { useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";

import {
  Avatar, FeatherName, Hairline, KeyCap, Menu, Sheet, Txt, usePalette,
} from "@/src/design/components";
import { PaletteProvider } from "@/src/design/CommandPalette";
import { useBp } from "@/src/design/responsive";
import { brand, color, font, layout, radius, space } from "@/src/design/tokens";
import { useAuth } from "@/src/state/auth";

type NavItem = { href: string; label: string; icon: FeatherName; match: string; roles?: string[] };

const PRIMARY: NavItem[] = [
  { href: "/(admin)/dashboard", label: "Today", icon: "sunrise", match: "dashboard" },
  { href: "/(admin)/quotations", label: "Quotations", icon: "file-text", match: "quotations" },
  { href: "/(admin)/catalog", label: "Catalogue", icon: "package", match: "catalog" },
  { href: "/(admin)/customers", label: "Customers", icon: "users", match: "customers" },
  { href: "/(admin)/purchases", label: "Purchases", icon: "shopping-cart", match: "purchases" },
  { href: "/(admin)/payments", label: "Payments", icon: "credit-card", match: "payments" },
  { href: "/(admin)/followups", label: "Follow-ups", icon: "phone-call", match: "followups" },
  { href: "/(admin)/reports", label: "Reports", icon: "bar-chart-2", match: "reports" },
];

const SECONDARY: NavItem[] = [
  { href: "/(admin)/notifications", label: "Notifications", icon: "bell", match: "notifications" },
  { href: "/(admin)/team", label: "Team", icon: "user-check", match: "team", roles: ["owner", "admin", "manager"] },
  { href: "/(admin)/settings", label: "Settings", icon: "settings", match: "settings" },
];

const roleLabel: Record<string, string> = {
  owner: "Owner", admin: "Admin", manager: "Manager", sales: "Sales",
  purchase: "Purchase", warehouse: "Warehouse", accounts: "Accounts", worker: "Worker",
};

function Wordmark({ compact }: { compact?: boolean }) {
  if (compact) {
    return (
      <View style={styles.monogram}>
        <Text style={{ fontFamily: font.serif, fontSize: 15, color: color.onAction }}>B</Text>
      </View>
    );
  }
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
      <View style={styles.monogram}>
        <Text style={{ fontFamily: font.serif, fontSize: 15, color: color.onAction }}>B</Text>
      </View>
      <Text style={{ fontFamily: font.serif, fontSize: 16.5, color: color.ink, letterSpacing: -0.2 }}>
        {brand.name}
      </Text>
    </View>
  );
}

// ── Sidebar item — the brass bar is the only accent in the chrome. ─────────
function SideItem({ item, active, onPress }: { item: NavItem; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      testID={`nav-${item.match}`}
      onPress={onPress}
      style={({ pressed, hovered }: any) => [
        styles.sideItem,
        { backgroundColor: active ? color.sunken : pressed || hovered ? color.hoverWash : "transparent" },
        Platform.OS === "web" ? ({ cursor: "pointer" } as any) : null,
      ]}
    >
      <View style={[styles.brassBar, { backgroundColor: active ? color.brass : "transparent" }]} />
      <Feather name={item.icon} size={16} color={active ? color.ink : color.inkSoft} />
      <Text
        style={{
          fontFamily: active ? font.semibold : font.medium,
          fontWeight: active ? "600" : "500",
          fontSize: 13.5, letterSpacing: -0.1,
          color: active ? color.ink : color.inkMid,
        }}
      >
        {item.label}
      </Text>
    </Pressable>
  );
}

function SearchTrigger() {
  const palette = usePalette();
  return (
    <Pressable
      testID="open-palette"
      onPress={palette.open}
      style={({ hovered }: any) => [
        styles.searchTrigger,
        { borderColor: hovered ? color.lineStrong : color.line, backgroundColor: color.surface },
        Platform.OS === "web" ? ({ cursor: "pointer" } as any) : null,
      ]}
    >
      <Feather name="search" size={14} color={color.inkSoft} />
      <Text style={{ flex: 1, fontFamily: font.regular, fontSize: 13, color: color.inkSoft }}>Search</Text>
      {Platform.OS === "web" ? <KeyCap label="⌘K" /> : null}
    </Pressable>
  );
}

// ── Desktop sidebar ─────────────────────────────────────────────────────────
function Sidebar() {
  const router = useRouter();
  const segments = useSegments() as string[];
  const { staff, logout } = useAuth();
  const isActive = (m: string) => segments.includes(m);

  return (
    <SafeAreaView edges={["top", "left", "bottom"]} style={styles.sidebar}>
      <View style={{ paddingHorizontal: space.x4, paddingTop: space.x5, paddingBottom: space.x4 }}>
        <Wordmark />
      </View>
      <View style={{ paddingHorizontal: space.x3, paddingBottom: space.x3 }}>
        <SearchTrigger />
      </View>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingHorizontal: space.x3, gap: 1 }} showsVerticalScrollIndicator={false}>
        {PRIMARY.map((n) => (
          <SideItem key={n.href} item={n} active={isActive(n.match)} onPress={() => router.push(n.href as any)} />
        ))}
        <View style={{ height: space.x5 }} />
        {SECONDARY.filter((n) => !n.roles || (staff && n.roles.includes(staff.role))).map((n) => (
          <SideItem key={n.href} item={n} active={isActive(n.match)} onPress={() => router.push(n.href as any)} />
        ))}
      </ScrollView>

      <View style={{ padding: space.x3, gap: space.x3 }}>
        <Hairline />
        <Menu
          align="left"
          items={[{
            label: "Sign out", icon: "log-out", tone: "risk",
            onPress: async () => { await logout(); router.replace("/(auth)/login"); },
          }]}
        >
          <View style={styles.userRow}>
            <Avatar name={staff?.full_name} size={32} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text numberOfLines={1} style={{ fontFamily: font.medium, fontWeight: "500", fontSize: 13, color: color.ink }}>
                {staff?.full_name}
              </Text>
              <Text numberOfLines={1} style={{ fontFamily: font.regular, fontSize: 11.5, color: color.inkSoft }}>
                {roleLabel[staff?.role || ""] || staff?.role}
              </Text>
            </View>
            <Feather name="more-horizontal" size={15} color={color.inkFaint} />
          </View>
        </Menu>
      </View>
    </SafeAreaView>
  );
}

// ── Tablet icon rail ────────────────────────────────────────────────────────
function Rail() {
  const router = useRouter();
  const segments = useSegments() as string[];
  const { staff, logout } = useAuth();
  const palette = usePalette();
  const isActive = (m: string) => segments.includes(m);

  const RailBtn = ({ item }: { item: NavItem }) => {
    const on = isActive(item.match);
    return (
      <Pressable
        testID={`nav-${item.match}`}
        accessibilityLabel={item.label}
        onPress={() => router.push(item.href as any)}
        style={({ pressed, hovered }: any) => [
          styles.railItem,
          { backgroundColor: on ? color.sunken : pressed || hovered ? color.hoverWash : "transparent" },
        ]}
      >
        <View style={[styles.brassBarRail, { backgroundColor: on ? color.brass : "transparent" }]} />
        <Feather name={item.icon} size={18} color={on ? color.ink : color.inkSoft} />
      </Pressable>
    );
  };

  return (
    <SafeAreaView edges={["top", "left", "bottom"]} style={styles.rail}>
      <View style={{ alignItems: "center", paddingVertical: space.x4, gap: space.x4 }}>
        <Wordmark compact />
        <Pressable accessibilityLabel="Search" onPress={palette.open} style={styles.railItem}>
          <Feather name="search" size={18} color={color.inkSoft} />
        </Pressable>
      </View>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ alignItems: "center", gap: 2 }} showsVerticalScrollIndicator={false}>
        {PRIMARY.map((n) => <RailBtn key={n.href} item={n} />)}
        <View style={{ height: space.x4 }} />
        {SECONDARY.filter((n) => !n.roles || (staff && n.roles.includes(staff.role))).map((n) => (
          <RailBtn key={n.href} item={n} />
        ))}
      </ScrollView>
      <View style={{ alignItems: "center", paddingVertical: space.x4 }}>
        <Menu
          align="left"
          items={[{
            label: "Sign out", icon: "log-out", tone: "risk",
            onPress: async () => { await logout(); router.replace("/(auth)/login"); },
          }]}
        >
          <Avatar name={staff?.full_name} size={32} />
        </Menu>
      </View>
    </SafeAreaView>
  );
}

// ── Phone bottom bar + More sheet ───────────────────────────────────────────
const PHONE_TABS: NavItem[] = [
  { href: "/(admin)/dashboard", label: "Today", icon: "sunrise", match: "dashboard" },
  { href: "/(admin)/quotations", label: "Quotes", icon: "file-text", match: "quotations" },
];
const PHONE_TABS_RIGHT: NavItem[] = [
  { href: "/(admin)/followups", label: "Tasks", icon: "phone-call", match: "followups" },
];
const MORE_ITEMS: NavItem[] = [
  { href: "/(admin)/catalog", label: "Catalogue", icon: "package", match: "catalog" },
  { href: "/(admin)/customers", label: "Customers", icon: "users", match: "customers" },
  { href: "/(admin)/purchases", label: "Purchases", icon: "shopping-cart", match: "purchases" },
  { href: "/(admin)/payments", label: "Payments", icon: "credit-card", match: "payments" },
  { href: "/(admin)/reports", label: "Reports", icon: "bar-chart-2", match: "reports" },
  { href: "/(admin)/notifications", label: "Notifications", icon: "bell", match: "notifications" },
  { href: "/(admin)/team", label: "Team", icon: "user-check", match: "team", roles: ["owner", "admin", "manager"] },
  { href: "/(admin)/settings", label: "Settings", icon: "settings", match: "settings" },
];

function PhoneBar() {
  const router = useRouter();
  const segments = useSegments() as string[];
  const { staff, logout } = useAuth();
  const palette = usePalette();
  const [moreOpen, setMoreOpen] = useState(false);
  const isActive = (m: string) => segments.includes(m);
  const moreActive = MORE_ITEMS.some((m) => isActive(m.match));

  const Tab = ({ item }: { item: NavItem }) => {
    const on = isActive(item.match);
    return (
      <Pressable testID={`bottom-nav-${item.match}`} onPress={() => router.push(item.href as any)} style={styles.tab}>
        <Feather name={item.icon} size={21} color={on ? color.ink : color.inkFaint} />
        <Text style={[styles.tabLabel, { color: on ? color.ink : color.inkFaint }]}>{item.label}</Text>
      </Pressable>
    );
  };

  return (
    <>
      <View style={styles.phoneBar}>
        {PHONE_TABS.map((t) => <Tab key={t.href} item={t} />)}
        <View style={styles.fabSlot}>
          <Pressable
            testID="bottom-fab-new-quotation"
            accessibilityLabel="New quotation"
            onPress={() => router.push("/(admin)/quotations/new" as any)}
            style={({ pressed }) => [styles.fab, { transform: [{ scale: pressed ? 0.94 : 1 }] }]}
          >
            <Feather name="plus" size={24} color={color.onAction} />
          </Pressable>
        </View>
        {PHONE_TABS_RIGHT.map((t) => <Tab key={t.href} item={t} />)}
        <Pressable testID="bottom-nav-more" onPress={() => setMoreOpen(true)} style={styles.tab}>
          <Feather name="grid" size={21} color={moreActive ? color.ink : color.inkFaint} />
          <Text style={[styles.tabLabel, { color: moreActive ? color.ink : color.inkFaint }]}>More</Text>
        </Pressable>
      </View>

      <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
        <Pressable
          onPress={() => { setMoreOpen(false); setTimeout(palette.open, 250); }}
          style={styles.moreRow}
        >
          <Feather name="search" size={17} color={color.inkMid} />
          <Text style={styles.moreLabel}>Search everything</Text>
        </Pressable>
        <Hairline style={{ marginVertical: 6 }} />
        {MORE_ITEMS.filter((n) => !n.roles || (staff && n.roles.includes(staff.role))).map((n) => (
          <Pressable
            key={n.href}
            onPress={() => { setMoreOpen(false); router.push(n.href as any); }}
            style={styles.moreRow}
          >
            <Feather name={n.icon} size={17} color={color.inkMid} />
            <Text style={styles.moreLabel}>{n.label}</Text>
          </Pressable>
        ))}
        <Hairline style={{ marginVertical: 6 }} />
        <View style={[styles.moreRow, { justifyContent: "space-between" }]}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
            <Avatar name={staff?.full_name} size={30} />
            <View>
              <Text style={{ fontFamily: font.medium, fontSize: 13.5, color: color.ink }}>{staff?.full_name}</Text>
              <Text style={{ fontFamily: font.regular, fontSize: 11.5, color: color.inkSoft }}>
                {roleLabel[staff?.role || ""] || staff?.role}
              </Text>
            </View>
          </View>
          <Pressable
            onPress={async () => { setMoreOpen(false); await logout(); router.replace("/(auth)/login"); }}
            hitSlop={layout.hitSlop}
          >
            <Text style={{ fontFamily: font.medium, fontSize: 13, color: color.risk }}>Sign out</Text>
          </Pressable>
        </View>
      </Sheet>
    </>
  );
}

// ── Layout root ─────────────────────────────────────────────────────────────
export default function AdminLayout() {
  const { isPhone, isTablet } = useBp();
  const insets = useSafeAreaInsets();

  if (isPhone) {
    return (
      <PaletteProvider>
        <View style={{ flex: 1, backgroundColor: color.canvas, paddingTop: insets.top }}>
          <View style={{ flex: 1 }}>
            <Slot />
          </View>
          <View style={{ backgroundColor: color.canvas, borderTopWidth: layout.hairline, borderTopColor: color.line, paddingBottom: insets.bottom }}>
            <PhoneBar />
          </View>
        </View>
      </PaletteProvider>
    );
  }

  return (
    <PaletteProvider>
      <View style={{ flex: 1, flexDirection: "row", backgroundColor: color.canvas }}>
        <View style={{
          width: isTablet ? layout.rail : layout.sidebar,
          borderRightWidth: layout.hairline, borderRightColor: color.line,
        }}>
          {isTablet ? <Rail /> : <Sidebar />}
        </View>
        <View style={{ flex: 1 }}>
          <Slot />
        </View>
      </View>
    </PaletteProvider>
  );
}

const styles = StyleSheet.create({
  sidebar: { flex: 1, backgroundColor: color.canvas },
  rail: { flex: 1, backgroundColor: color.canvas },
  monogram: {
    width: 26, height: 26, borderRadius: 7, backgroundColor: color.ink,
    alignItems: "center", justifyContent: "center",
  },
  searchTrigger: {
    flexDirection: "row", alignItems: "center", gap: 8,
    height: 34, borderRadius: radius.md, borderWidth: 1, paddingHorizontal: 10,
  },
  sideItem: {
    flexDirection: "row", alignItems: "center", gap: 10,
    height: 36, borderRadius: radius.sm, paddingLeft: 10, paddingRight: 10,
    overflow: "hidden",
  },
  brassBar: {
    position: "absolute", left: 0, top: 8, bottom: 8, width: 2.5, borderRadius: 2,
  },
  brassBarRail: {
    position: "absolute", left: 0, top: 10, bottom: 10, width: 2.5, borderRadius: 2,
  },
  railItem: {
    width: 42, height: 42, borderRadius: radius.sm,
    alignItems: "center", justifyContent: "center", overflow: "hidden",
  },
  userRow: {
    flexDirection: "row", alignItems: "center", gap: 10,
    paddingHorizontal: 8, paddingVertical: 6, borderRadius: radius.md,
  },
  phoneBar: {
    height: layout.bottomBar, flexDirection: "row", alignItems: "center",
    paddingHorizontal: space.x2,
  },
  tab: { flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: 6, gap: 2 },
  tabLabel: { fontFamily: font.medium, fontWeight: "500", fontSize: 10 },
  fabSlot: { width: 68, alignItems: "center", justifyContent: "center" },
  fab: {
    width: 52, height: 52, borderRadius: 26, backgroundColor: color.brass,
    alignItems: "center", justifyContent: "center", marginTop: -22,
    borderWidth: 4, borderColor: color.canvas,
  },
  moreRow: {
    flexDirection: "row", alignItems: "center", gap: 12,
    height: 48, paddingHorizontal: 4,
  },
  moreLabel: { fontFamily: font.medium, fontWeight: "500", fontSize: 14.5, color: color.ink },
});
