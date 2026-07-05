// BuildCon House · Quotations list
// Premium card list: number pill · customer + meta · total · status.
// Optimised for phone (no cramped inline rows), tablet gets a tabular feel.

import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import {
  Avatar, Chip, EmptyState, SearchField, Skeleton, StatusBadge,
} from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Quotation = {
  id: string; number: string; customer_name: string;
  status: string; grand_total: number; created_at: string; items: any[];
};

type Filter = "all" | "draft" | "pending_approval" | "sent" | "won" | "lost";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all",              label: "All" },
  { key: "draft",            label: "Draft" },
  { key: "pending_approval", label: "Pending" },
  { key: "sent",             label: "Sent" },
  { key: "won",              label: "Won" },
  { key: "lost",             label: "Lost" },
];

export default function QuotationsList() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;

  const [items, setItems] = useState<Quotation[] | null>(null);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<Filter>("all");

  useEffect(() => {
    api.get<Quotation[]>("/quotations").then(setItems).catch(() => setItems([]));
  }, []);

  const counts = useMemo(() => {
    const map: Record<string, number> = { all: items?.length || 0 };
    (items || []).forEach((it) => { map[it.status] = (map[it.status] || 0) + 1; });
    return map;
  }, [items]);

  const filtered = useMemo(() => (items || []).filter((it) => {
    if (statusFilter !== "all" && it.status !== statusFilter) return false;
    if (q && !`${it.number} ${it.customer_name}`.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  }), [items, q, statusFilter]);

  const totalValue = filtered.reduce((s, it) => s + (it.grand_total || 0), 0);

  return (
    <AdminPage
      title="Quotations"
      subtitle={items ? `${items.length} total · ${money(totalValue)} filtered pipeline` : "Loading pipeline…"}
      right={
        <Pressable
          testID="new-quotation-btn"
          onPress={() => router.push("/(admin)/quotations/new" as any)}
          style={({ pressed }) => [styles.cta, { opacity: pressed ? 0.88 : 1 }]}
        >
          <Feather name="plus" size={16} color={colors.onBrand} />
          <Text style={styles.ctaText}>New{isTablet ? " Quotation" : ""}</Text>
        </Pressable>
      }
    >
      <View style={{ gap: spacing.md }}>
        <SearchField
          testID="quotations-search"
          value={q}
          onChangeText={setQ}
          placeholder="Search by number or customer…"
          onClear={() => setQ("")}
        />
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 8, paddingRight: spacing.lg }}
        >
          {FILTERS.map((f) => (
            <Chip
              key={f.key}
              testID={`filter-${f.key}`}
              label={f.label}
              active={statusFilter === f.key}
              onPress={() => setStatusFilter(f.key)}
              count={counts[f.key]}
            />
          ))}
        </ScrollView>
      </View>

      {!items ? (
        <View style={{ gap: spacing.sm }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <View key={i} style={[styles.card, { gap: 10 }]}>
              <Skeleton w={110} h={12} />
              <Skeleton w={220} h={16} />
              <Skeleton w={160} h={12} />
            </View>
          ))}
        </View>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="file-text"
          title={q || statusFilter !== "all" ? "No quotations match" : "No quotations yet"}
          subtitle={q || statusFilter !== "all" ? "Try clearing filters or searching a different term." : "Press New Quotation to start building."}
        />
      ) : (
        <View style={{ gap: spacing.sm }}>
          {filtered.map((q0) => (
            <QuotationRow
              key={q0.id}
              q={q0}
              onPress={() => router.push(`/(admin)/quotations/${q0.id}` as any)}
            />
          ))}
        </View>
      )}
    </AdminPage>
  );
}

// ── Single row card ──
function QuotationRow({ q, onPress }: { q: Quotation; onPress: () => void }) {
  const created = new Date(q.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return (
    <Pressable
      testID={`quotation-${q.id}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, { transform: [{ scale: pressed ? 0.997 : 1 }], opacity: pressed ? 0.94 : 1 }]}
    >
      {/* Row 1: number + status */}
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm }}>
        <View style={styles.numberPill}>
          <Feather name="file-text" size={11} color={colors.brand} />
          <Text style={styles.numberText}>{q.number}</Text>
        </View>
        <StatusBadge status={q.status} />
      </View>

      {/* Row 2: customer + total */}
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", gap: spacing.md, marginTop: 12 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
          <Avatar name={q.customer_name} size={32} tone="surface" />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text numberOfLines={1} style={styles.customer}>{q.customer_name || "Unknown customer"}</Text>
            <Text numberOfLines={1} style={type.caption}>{q.items.length} items · {created}</Text>
          </View>
        </View>
        <Text style={styles.total}>{money(q.grand_total)}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  cta: {
    flexDirection: "row", gap: 6, alignItems: "center",
    backgroundColor: colors.brand,
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: radius.md,
  },
  ctaText: {
    color: colors.onBrand, fontSize: 13,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "600", letterSpacing: -0.1,
  },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
  },
  numberPill: {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.sm,
    backgroundColor: colors.brandTint,
  },
  numberText: {
    fontSize: 11,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "600",
    color: colors.brand,
    letterSpacing: 0.1,
    fontVariant: ["tabular-nums"],
  },
  customer: {
    fontSize: 15,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "600",
    color: colors.onSurface,
    letterSpacing: -0.1,
  },
  total: {
    fontSize: 16,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "700",
    color: colors.onSurface,
    fontVariant: ["tabular-nums"],
    letterSpacing: -0.2,
  },
});
