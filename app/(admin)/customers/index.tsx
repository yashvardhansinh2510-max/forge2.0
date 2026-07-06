// Customers list — DS-aligned rebuild.
// Uses PageHeader, HeroBanner stat row, filter chips, SearchField, and a
// unified customer-card language shared with quotations/purchases/payments.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import {
  Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import {
  Avatar, Badge, Button, Chip, EmptyState, PageHeader,
  SearchField, Skeleton, StatTile,
} from "@/src/components/ui";
import { colors, icon as iconSize, radius, spacing, type } from "@/src/theme/tokens";

type Customer = {
  id: string;
  name: string;
  company?: string | null;
  email: string;
  city?: string | null;
  tier: "retail" | "trade" | "vip";
  phone?: string | null;
};

const tierTone: Record<string, "success" | "info" | "neutral"> = {
  vip: "success",
  trade: "info",
  retail: "neutral",
};

type TierFilter = "all" | "vip" | "trade" | "retail";

export default function Customers() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;

  const [items, setItems] = useState<Customer[] | null>(null);
  const [q, setQ] = useState("");
  const [tier, setTier] = useState<TierFilter>("all");

  useEffect(() => {
    api.get<Customer[]>("/customers").then(setItems).catch(() => setItems([]));
  }, []);

  const counts = useMemo(() => {
    const map: Record<string, number> = { all: items?.length || 0, vip: 0, trade: 0, retail: 0 };
    (items || []).forEach((c) => { map[c.tier] = (map[c.tier] || 0) + 1; });
    return map;
  }, [items]);

  const filtered = useMemo(() => (items || []).filter((c) => {
    if (tier !== "all" && c.tier !== tier) return false;
    if (!q) return true;
    const needle = q.toLowerCase();
    return `${c.name} ${c.company || ""} ${c.email} ${c.city || ""}`.toLowerCase().includes(needle);
  }), [items, q, tier]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <PageHeader
        title="Customers"
        subtitle={items ? `${items.length} accounts · Trade, VIP & retail buyers` : "Loading customers…"}
        overline="CRM"
        actions={
          <Button
            icon="plus"
            label="Add Customer"
            variant="primary"
            size="md"
            onPress={() => router.push("/(admin)/customers/new" as any)}
          />
        }
      />

      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg, paddingBottom: spacing.xxxl }}>
        {/* Stats */}
        <View style={[styles.statsRow, !isDesktop && styles.statsRowMobile]}>
          <StatTile
            label="Total Customers"
            value={items ? counts.all : "—"}
            icon="users"
            tone="brand"
            sub="All active accounts"
          />
          <StatTile
            label="VIP"
            value={items ? counts.vip : "—"}
            icon="star"
            tone="success"
            sub="Premium tier"
          />
          <StatTile
            label="Trade"
            value={items ? counts.trade : "—"}
            icon="briefcase"
            tone="brand"
            sub="Trade partners"
          />
          <StatTile
            label="Retail"
            value={items ? counts.retail : "—"}
            icon="user"
            tone="neutral"
            sub="Direct buyers"
          />
        </View>

        {/* Toolbar */}
        <View style={{ gap: spacing.md }}>
          <SearchField
            value={q}
            onChangeText={setQ}
            onClear={() => setQ("")}
            placeholder="Search customers, cities, companies…"
            testID="customers-search"
          />
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: spacing.sm, paddingRight: spacing.lg }}
          >
            {([
              { key: "all",    label: "All" },
              { key: "vip",    label: "VIP" },
              { key: "trade",  label: "Trade" },
              { key: "retail", label: "Retail" },
            ] as { key: TierFilter; label: string }[]).map((f) => (
              <Chip
                key={f.key}
                label={f.label}
                active={tier === f.key}
                onPress={() => setTier(f.key)}
                count={counts[f.key]}
                testID={`tier-${f.key}`}
              />
            ))}
          </ScrollView>
        </View>

        {/* List */}
        {!items ? (
          <View style={{ gap: spacing.sm }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <View key={i} style={[styles.card, { flexDirection: "row", gap: spacing.md, alignItems: "center" }]}>
                <Skeleton w={44} h={44} radius={22} />
                <View style={{ flex: 1, gap: 6 }}>
                  <Skeleton w="60%" h={14} />
                  <Skeleton w="40%" h={12} />
                </View>
                <Skeleton w={60} h={20} radius={radius.pill} />
              </View>
            ))}
          </View>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon="users"
            title="No customers match"
            subtitle="Try clearing the search or filter to see more."
            action={
              <Button
                label="Clear filters"
                variant="secondary"
                size="sm"
                icon="x"
                onPress={() => { setQ(""); setTier("all"); }}
              />
            }
          />
        ) : (
          <View style={{ gap: spacing.sm }}>
            {filtered.map((c) => (
              <Pressable
                key={c.id}
                testID={`customer-${c.id}`}
                onPress={() => router.push(`/(admin)/customers/${c.id}` as any)}
                style={({ pressed, hovered }: any) => [
                  styles.card,
                  {
                    backgroundColor: pressed ? colors.surfaceTertiary
                      : hovered ? colors.surfaceSubtle
                      : colors.surfaceSecondary,
                    borderColor: hovered ? colors.borderStrong : colors.border,
                  },
                ]}
              >
                <Avatar name={c.company || c.name} size={44} tone="brand" />
                <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
                  <Text numberOfLines={1} style={type.titleSm}>{c.company || c.name}</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" }}>
                    <Text style={type.caption} numberOfLines={1}>{c.email}</Text>
                    {c.city ? (
                      <>
                        <View style={styles.dot} />
                        <Text style={type.caption} numberOfLines={1}>{c.city}</Text>
                      </>
                    ) : null}
                  </View>
                </View>
                <View style={{ alignItems: "flex-end", gap: spacing.sm, flexShrink: 0 }}>
                  <Badge label={c.tier.toUpperCase()} tone={tierTone[c.tier]} size="sm" />
                  <Feather name="chevron-right" size={iconSize.md} color={colors.onSurfaceMuted} />
                </View>
              </Pressable>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  statsRow: { flexDirection: "row", gap: spacing.md },
  statsRowMobile: { flexWrap: "wrap" },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  dot: {
    width: 3, height: 3, borderRadius: 999,
    backgroundColor: colors.onSurfaceSubtle,
  },
});
