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
import { BuildConLogo } from "@/src/design/BrandLogo";
import { useAuth } from "@/src/state/auth";
import { useModuleAccess } from "@/src/hooks/use-permissions";
import { useFloorAccess } from "@/src/hooks/use-floor-access";

type NavItem = { href: string; label: string; icon: FeatherName; match: string; roles?: string[] };

const PRIMARY: NavItem[] = [
  { href: "/(admin)/dashboard", label: "Today", icon: "sunrise", match: "dashboard" },
  { href: "/(admin)/quotations", label: "Quotations", icon: "file-text", match: "quotations" },
  { href: "/(admin)/catalog", label: "Catalog", icon: "package", match: "catalog" },
  { href: "/(admin)/customers", label: "Customers", icon: "users", match: "customers" },
  { href: "/(admin)/purchases", label: "Purchases", icon: "shopping-cart", match: "purchases" },
  { href: "/(admin)/payments", label: "Payments", icon: "credit-card", match: "payments" },
  { href: "/(admin)/followups", label: "Follow-ups", icon: "phone-call", match: "followups" },
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
  return <BuildConLogo height={32} />;
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

function FloorSwitcher({ compact = false }: { compact?: boolean }) {
  const { access, floors, selectedFloorId, selectFloor } = useFloorAccess();
  const selected = floors.find((floor) => floor.id === selectedFloorId);
  if (!access || floors.length < 2) return null;
  const pick = async (id: string) => {
    if (id === selectedFloorId) return;
    await selectFloor(id);
    // Data on every mounted screen is scoped by the request header, so a
    // floor change requires a clean reload to refetch everything.
    if (Platform.OS === "web" && typeof window !== "undefined") window.location.reload();
  };
  const items = [
    ...(access.all_floors ? [{
      label: `All floors${selectedFloorId === "" ? " · Active" : ""}`,
      icon: (selectedFloorId === "" ? "check" : "layers") as FeatherName,
      onPress: () => { void pick(""); },
    }] : []),
    ...floors.map((floor) => ({
      label: `${floor.name}${floor.id === selectedFloorId ? " · Active" : ""}`,
      icon: (floor.id === selectedFloorId ? "check" : "layers") as FeatherName,
      onPress: () => { void pick(floor.id); },
    })),
  ];
  const currentLabel = selectedFloorId === "" ? "All floors" : selected?.name || "Select floor";
  return (
    <Menu align={compact ? "right" : "left"} items={items}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 10, height: 40, borderRadius: radius.md, backgroundColor: color.surface, borderWidth: layout.hairline, borderColor: color.line }}>
        <Feather name="layers" size={15} color={color.brass} />
        {!compact ? <Text numberOfLines={1} style={{ flex: 1, fontFamily: font.medium, fontSize: 12.5, color: color.ink }}>{currentLabel}</Text> : null}
        <Feather name="chevron-down" size={14} color={color.inkSoft} />
      </View>
    </Menu>
  );
}

// ── Ground Floor → Tiles module nav ────────────────────────────────────────
// The tiles document builders (Selection / Quotation) are Ground-floor pages:
// their catalog search AND the floor stamped onto saved documents both follow
// the active-floor request header, so opening them from another floor first
// switches the active floor to Ground floor (same reload semantics as the
// FloorSwitcher) before navigating.
const TILES_ITEMS: NavItem[] = [
  { href: "/(admin)/tiles/selection", label: "Tiles Selection", icon: "grid", match: "selection" },
  { href: "/(admin)/tiles/quotation", label: "Tiles Quotation", icon: "layout", match: "quotation" },
  { href: "/(admin)/tiles/orders", label: "Tile Orders", icon: "truck", match: "orders" },
];

function useTilesNav() {
  const router = useRouter();
  const { access, selectedFloorId, selectFloor } = useFloorAccess();
  const groundAccessible = Boolean(access && (access.all_floors || access.floor_ids.includes("ground-floor")));
  const items = groundAccessible ? TILES_ITEMS : [];
  const open = async (item: NavItem) => {
    if (selectedFloorId !== "ground-floor") {
      await selectFloor("ground-floor");
      if (Platform.OS === "web" && typeof window !== "undefined") {
        // Full reload so every mounted screen refetches under the new floor
        // scope — mirrors FloorSwitcher.pick().
        window.location.assign(item.href.replace("/(admin)", ""));
        return;
      }
    }
    router.push(item.href as any);
  };
  return { items, open };
}

// ── Desktop sidebar ─────────────────────────────────────────────────────────
function Sidebar() {
  const router = useRouter();
  const segments = useSegments() as string[];
  const { staff, logout } = useAuth();
  const hasAccess = useModuleAccess();
  const tilesNav = useTilesNav();
  const isActive = (m: string) => segments.includes(m);

  return (
    <SafeAreaView edges={["top", "left", "bottom"]} style={styles.sidebar}>
      <View style={{ paddingHorizontal: space.x4, paddingTop: space.x5, paddingBottom: space.x4 }}>
        <Wordmark />
      </View>
      <View style={{ paddingHorizontal: space.x3, paddingBottom: space.x3 }}><FloorSwitcher /></View>
      <View style={{ paddingHorizontal: space.x3, paddingBottom: space.x3 }}>
        <SearchTrigger />
      </View>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingHorizontal: space.x3, gap: 1 }} showsVerticalScrollIndicator={false}>
        {PRIMARY.filter((n) => hasAccess(n.match)).map((n) => (
          <SideItem key={n.href} item={n} active={isActive(n.match)} onPress={() => router.push(n.href as any)} />
        ))}
        {hasAccess("quotations") && tilesNav.items.map((n) => (
          <SideItem key={n.href} item={n} active={segments.includes("tiles") && isActive(n.match)} onPress={() => { void tilesNav.open(n); }} />
        ))}
        <View style={{ height: space.x5 }} />
        {SECONDARY.filter((n) => hasAccess(n.match)).map((n) => (
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
  const hasAccess = useModuleAccess();
  const palette = usePalette();
  const tilesNav = useTilesNav();
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
        <FloorSwitcher compact />
        <Pressable accessibilityLabel="Search" onPress={palette.open} style={styles.railItem}>
          <Feather name="search" size={18} color={color.inkSoft} />
        </Pressable>
      </View>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ alignItems: "center", gap: 2 }} showsVerticalScrollIndicator={false}>
        {PRIMARY.filter((n) => hasAccess(n.match)).map((n) => <RailBtn key={n.href} item={n} />)}
        {hasAccess("quotations") && tilesNav.items.map((n) => (
          <Pressable
            key={n.href}
            testID={`nav-${n.match}`}
            accessibilityLabel={n.label}
            onPress={() => { void tilesNav.open(n); }}
            style={({ pressed, hovered }: any) => [
              styles.railItem,
              { backgroundColor: segments.includes("tiles") && isActive(n.match) ? color.sunken : pressed || hovered ? color.hoverWash : "transparent" },
            ]}
          >
            <View style={[styles.brassBarRail, { backgroundColor: segments.includes("tiles") && isActive(n.match) ? color.brass : "transparent" }]} />
            <Feather name={n.icon} size={18} color={segments.includes("tiles") && isActive(n.match) ? color.ink : color.inkSoft} />
          </Pressable>
        ))}
        <View style={{ height: space.x4 }} />
        {SECONDARY.filter((n) => hasAccess(n.match)).map((n) => (
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
  { href: "/(admin)/dashboard", label: "Today", icon: "home", match: "dashboard" },
  { href: "/(admin)/quotations", label: "Quotes", icon: "file-text", match: "quotations" },
];
const PHONE_TABS_RIGHT: NavItem[] = [
  { href: "/(admin)/followups", label: "Tasks", icon: "check-square", match: "followups" },
];
const MORE_ITEMS: NavItem[] = [
  { href: "/(admin)/catalog", label: "Catalog", icon: "package", match: "catalog" },
  { href: "/(admin)/customers", label: "Customers", icon: "users", match: "customers" },
  { href: "/(admin)/purchases", label: "Purchases", icon: "shopping-cart", match: "purchases" },
  { href: "/(admin)/payments", label: "Payments", icon: "credit-card", match: "payments" },
  { href: "/(admin)/notifications", label: "Notifications", icon: "bell", match: "notifications" },
  { href: "/(admin)/team", label: "Team", icon: "user-check", match: "team", roles: ["owner", "admin", "manager"] },
  { href: "/(admin)/settings", label: "Settings", icon: "settings", match: "settings" },
];

function PhoneBar() {
  const router = useRouter();
  const segments = useSegments() as string[];
  const { staff, logout } = useAuth();
  const hasAccess = useModuleAccess();
  const palette = usePalette();
  const tilesNav = useTilesNav();
  const [moreOpen, setMoreOpen] = useState(false);
  const isActive = (m: string) => segments.includes(m);
  const visibleMore = MORE_ITEMS.filter((n) => hasAccess(n.match));
  const moreActive = visibleMore.some((m) => isActive(m.match));

  const Tab = ({ item }: { item: NavItem }) => {
    const on = isActive(item.match);
    return (
      <Pressable testID={`bottom-nav-${item.match}`} onPress={() => router.push(item.href as any)} style={styles.tab}>
        <View style={[styles.tabIconWrap, on && styles.tabIconWrapActive]}>
          <Feather name={item.icon} size={19} color={on ? color.brass : color.inkFaint} />
        </View>
        <Text style={[styles.tabLabel, on && styles.tabLabelActive]}>{item.label}</Text>
      </Pressable>
    );
  };

  return (
    <>
      <View style={styles.phoneBar}>
        {PHONE_TABS.filter((t) => hasAccess(t.match)).map((t) => <Tab key={t.href} item={t} />)}
        <View style={styles.fabSlot}>
          <Pressable
            testID="bottom-fab-new-quotation"
            accessibilityLabel="New quotation"
            onPress={() => router.push("/(admin)/quotations/new" as any)}
            style={({ pressed }) => [styles.fab, { transform: [{ scale: pressed ? 0.94 : 1 }] }]}
          >
            <Feather name="plus" size={22} color={color.onAction} />
          </Pressable>
        </View>
        {PHONE_TABS_RIGHT.filter((t) => hasAccess(t.match)).map((t) => <Tab key={t.href} item={t} />)}
        <Pressable testID="bottom-nav-more" onPress={() => setMoreOpen(true)} style={styles.tab}>
          <View style={[styles.tabIconWrap, moreActive && styles.tabIconWrapActive]}>
            <Feather name="menu" size={19} color={moreActive ? color.brass : color.inkFaint} />
          </View>
          <Text style={[styles.tabLabel, moreActive && styles.tabLabelActive]}>More</Text>
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
        <View style={{ paddingVertical: 6 }}><FloorSwitcher /></View>
        <Hairline style={{ marginVertical: 6 }} />
        {hasAccess("quotations") && tilesNav.items.map((n) => (
          <Pressable
            key={n.href}
            onPress={() => { setMoreOpen(false); void tilesNav.open(n); }}
            style={styles.moreRow}
          >
            <Feather name={n.icon} size={17} color={color.inkMid} />
            <Text style={styles.moreLabel}>{n.label}</Text>
          </Pressable>
        ))}
        {tilesNav.items.length ? <Hairline style={{ marginVertical: 6 }} /> : null}
        {visibleMore.map((n) => (
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
  tab: { flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: 6, gap: 3 },
  tabIconWrap: {
    width: 40, height: 26, borderRadius: radius.md, alignItems: "center", justifyContent: "center",
  },
  tabIconWrapActive: { backgroundColor: color.brassTint },
  tabLabel: { fontFamily: font.medium, fontWeight: "500", fontSize: 10.5, color: color.inkFaint, letterSpacing: 0.1 },
  tabLabelActive: { color: color.ink, fontWeight: "600" },
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
