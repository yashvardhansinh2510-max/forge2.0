import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Card, EmptyState, Skeleton, StatusBadge } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Quotation = {
  id: string; number: string; customer_name: string;
  status: string; grand_total: number; created_at: string; items: any[];
};

const STATUSES = ["all", "draft", "pending_approval", "sent", "won", "lost"];

export default function QuotationsList() {
  const router = useRouter();
  const [items, setItems] = useState<Quotation[] | null>(null);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    api.get<Quotation[]>("/quotations").then(setItems).catch(() => setItems([]));
  }, []);

  const filtered = (items || []).filter((it) => {
    if (statusFilter !== "all" && it.status !== statusFilter) return false;
    if (q && !`${it.number} ${it.customer_name}`.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  return (
    <AdminPage
      title="Quotations"
      subtitle={`${items?.length ?? "—"} total · Track pipeline, approvals, and revenue.`}
      right={
        <Pressable
          testID="new-quotation-btn"
          onPress={() => router.push("/(admin)/quotations/new" as any)}
          style={styles.cta}
        >
          <Feather name="plus" size={16} color={colors.onBrand} />
          <Text style={styles.ctaText}>New Quotation</Text>
        </Pressable>
      }
    >
      <View style={{ gap: spacing.md }}>
        <View style={styles.searchWrap}>
          <Feather name="search" size={16} color={colors.onSurfaceMuted} />
          <TextInput
            testID="quotations-search"
            value={q}
            onChangeText={setQ}
            placeholder="Search by number or customer…"
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
          />
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {STATUSES.map((s) => (
            <Pressable
              key={s}
              testID={`filter-${s}`}
              onPress={() => setStatusFilter(s)}
              style={[styles.chip, statusFilter === s && styles.chipActive]}
            >
              <Text style={{ color: statusFilter === s ? colors.onBrand : colors.onSurface, fontSize: 13, fontWeight: "500" }}>
                {s === "all" ? "All" : s.replace("_", " ")}
              </Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      {!items ? (
        <Card style={{ padding: 0 }}>
          {Array.from({ length: 5 }).map((_, i) => (
            <View key={i} style={styles.row}>
              <Skeleton w={80} />
              <Skeleton w={180} />
              <Skeleton w={100} />
            </View>
          ))}
        </Card>
      ) : filtered.length === 0 ? (
        <EmptyState icon="file-text" title="No quotations yet" subtitle="Press New Quotation to start building." />
      ) : (
        <Card style={{ padding: 0 }}>
          {filtered.map((q0, i) => (
            <Pressable
              key={q0.id}
              testID={`quotation-${q0.id}`}
              onPress={() => router.push(`/(admin)/quotations/${q0.id}` as any)}
              style={({ pressed }) => [styles.row, {
                backgroundColor: pressed ? colors.surfaceTertiary : "transparent",
                borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth, borderColor: colors.border,
              }]}
            >
              <Text style={[type.mono, { width: 110 }]}>{q0.number}</Text>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>{q0.customer_name}</Text>
                <Text style={type.caption}>{q0.items.length} items · {new Date(q0.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</Text>
              </View>
              <Text style={[type.mono, { fontSize: 14, fontWeight: "600" }]}>{money(q0.grand_total)}</Text>
              <StatusBadge status={q0.status} />
            </Pressable>
          ))}
        </Card>
      )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  cta: { flexDirection: "row", gap: 6, alignItems: "center", backgroundColor: colors.brand, paddingHorizontal: 14, paddingVertical: 9, borderRadius: radius.md },
  ctaText: { color: colors.onBrand, fontSize: 13, fontWeight: "600" },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 10,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    paddingHorizontal: 14, borderRadius: radius.md,
  },
  searchInput: { flex: 1, fontSize: 14, paddingVertical: 12, color: colors.onSurface },
  chip: { paddingHorizontal: 14, height: 34, borderRadius: 999, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  chipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md },
});
