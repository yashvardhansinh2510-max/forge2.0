// Customer Portal — Quotations List (read-only). Every quotation belonging
// to this customer: status, date, total, revision count, expiry. Tapping a
// row opens the read-only detail screen. No editing, no filters beyond the
// default newest-first order — kept intentionally simple per the minimal
// customer-portal roadmap.
//
// Route note: lives at (customer)/quotes/* rather than (customer)/quotations/*
// on purpose — expo-router strips group parentheses from the resolved public
// URL, and (admin)/quotations/* already occupies that exact path. Sharing it
// caused a real bug (browser refresh on a customer's own quotation page
// resolved to the STAFF quotation screen and crashed with "Not a staff
// token"). Keep this folder named "quotes" so the two never collide.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { Card, EmptyState, PageHeader, Skeleton, StatusBadge } from "@/src/components/ui";
import { colors, money, spacing, type } from "@/src/theme/tokens";

type Quote = {
  id: string; number: string; status: string; grand_total: number;
  created_at: string; items: any[]; valid_until?: string; revisions?: any[];
};

export default function CustomerQuotationsList() {
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = () => api.get<Quote[]>("/portal/quotations").then(setQuotes).catch(() => setQuotes([]));

  useEffect(() => { load(); }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <PageHeader title="Quotations" subtitle={quotes ? `${quotes.length} total` : undefined} back={() => router.back()} />
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ padding: spacing.xl, gap: spacing.md, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
        {!quotes ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} style={{ gap: 12 }}>
              <Skeleton w="40%" />
              <Skeleton w="80%" h={20} />
              <Skeleton w="30%" />
            </Card>
          ))
        ) : quotes.length === 0 ? (
          <EmptyState icon="file-text" title="No quotations yet" subtitle="Your sales representative will share estimates here." />
        ) : (
          quotes.map((q) => (
            <Card key={q.id} testID={`quote-row-${q.id}`} onPress={() => router.push(`/(customer)/quotes/${q.id}`)}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <View style={{ flex: 1, gap: 4 }}>
                  <Text style={[type.mono, { color: colors.onSurfaceMuted }]} numberOfLines={1}>{q.number}</Text>
                  <Text style={type.titleMd} numberOfLines={1}>{money(q.grand_total)}</Text>
                  <Text style={type.caption}>
                    {new Date(q.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                    {q.revisions && q.revisions.length > 0 ? ` · Rev ${q.revisions.length}` : ""}
                    {q.valid_until ? ` · Valid till ${new Date(q.valid_until).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}` : ""}
                  </Text>
                </View>
                <View style={{ alignItems: "flex-end", gap: 8 }}>
                  <StatusBadge status={q.status} />
                  <Feather name="chevron-right" size={18} color={colors.onSurfaceMuted} />
                </View>
              </View>
            </Card>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}
