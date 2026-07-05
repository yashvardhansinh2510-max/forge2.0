// BuildCon House · Customers list
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Avatar, Badge, Chip, EmptyState, SearchField, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

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
  const [items, setItems] = useState<Customer[] | null>(null);
  const [q, setQ] = useState("");
  const [tier, setTier] = useState<TierFilter>("all");

  useEffect(() => { api.get<Customer[]>("/customers").then(setItems).catch(() => setItems([])); }, []);

  const counts = useMemo(() => {
    const map: Record<string, number> = { all: items?.length || 0 };
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
    <AdminPage
      title="Customers"
      subtitle={items ? `${items.length} accounts · Trade, VIP & retail buyers` : "Loading customers…"}
    >
      <View style={{ gap: spacing.md }}>
        <SearchField
          value={q}
          onChangeText={setQ}
          onClear={() => setQ("")}
          placeholder="Search customers, cities, companies…"
          testID="customers-search"
        />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingRight: spacing.lg }}>
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

      {!items ? (
        <View style={{ gap: spacing.sm }}>
          {Array.from({ length: 5 }).map((_, i) => (
            <View key={i} style={[styles.card, { flexDirection: "row", gap: spacing.md, alignItems: "center" }]}>
              <Skeleton w={40} h={40} radius={20} />
              <View style={{ flex: 1, gap: 6 }}>
                <Skeleton w="60%" h={14} />
                <Skeleton w="40%" h={12} />
              </View>
            </View>
          ))}
        </View>
      ) : filtered.length === 0 ? (
        <EmptyState icon="users" title="No customers match" subtitle="Try clearing the search or filter to see more." />
      ) : (
        <View style={{ gap: spacing.sm }}>
          {filtered.map((c) => (
            <Pressable
              key={c.id}
              testID={`customer-${c.id}`}
              onPress={() => router.push(`/(admin)/customers/${c.id}` as any)}
              style={({ pressed }) => [styles.card, { opacity: pressed ? 0.9 : 1 }]}
            >
              <Avatar name={c.company || c.name} size={44} tone="brand" />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text numberOfLines={1} style={styles.customerName}>{c.company || c.name}</Text>
                <Text numberOfLines={1} style={type.caption}>
                  {c.email}{c.city ? ` · ${c.city}` : ""}
                </Text>
              </View>
              <View style={{ alignItems: "flex-end", gap: 6 }}>
                <Badge label={c.tier.toUpperCase()} tone={tierTone[c.tier]} size="sm" />
                <Feather name="chevron-right" size={16} color={colors.onSurfaceMuted} />
              </View>
            </Pressable>
          ))}
        </View>
      )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  customerName: {
    fontSize: 15,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "600",
    color: colors.onSurface,
    letterSpacing: -0.1,
    marginBottom: 2,
  },
});
