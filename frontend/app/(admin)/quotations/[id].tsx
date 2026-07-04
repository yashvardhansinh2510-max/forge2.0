import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button, Card, StatusBadge } from "@/src/components/ui";
import { api, getToken } from "@/src/api/client";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";

type Line = { id: string; sku: string; name: string; qty: number; unit_price: number; discount_pct: number; tax_pct: number; room?: string };
type Quotation = {
  id: string; number: string; customer_name: string; status: string;
  items: Line[]; rooms: string[]; subtotal: number; discount_total: number;
  tax_total: number; grand_total: number; created_at: string; notes?: string;
  created_by_name: string;
};

const NEXT_STATUS: Record<string, string> = {
  draft: "sent",
  sent: "won",
  pending_approval: "approved",
};

export default function QuotationDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [q, setQ] = useState<Quotation | null>(null);

  const load = async () => {
    const doc = await api.get<Quotation>(`/quotations/${id}`);
    setQ(doc);
  };
  useEffect(() => { load(); }, [id]);

  const openPdf = async () => {
    const token = await getToken();
    if (!token) return;
    const url = `${api.base}/api/quotations/${id}/pdf?_t=${encodeURIComponent(token)}`;
    // browser can't send Authorization headers on window.open; server also accepts _t
    // (but our route requires header). We'll open a signed link built via fetch instead.
    // Simplest cross-platform: fetch blob and open via Linking (data:).
    try {
      const res = await fetch(`${api.base}/api/quotations/${id}/pdf`, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await res.blob();
      const reader = new FileReader();
      reader.onloadend = () => Linking.openURL(reader.result as string);
      reader.readAsDataURL(blob);
    } catch {
      Linking.openURL(url);
    }
  };

  const advance = async () => {
    if (!q) return;
    const next = NEXT_STATUS[q.status];
    if (!next) return;
    const updated = await api.patch<Quotation>(`/quotations/${id}`, { status: next, reason: `Marked ${next}` });
    setQ(updated);
  };

  if (!q) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.topbar}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Feather name="chevron-left" size={18} color={colors.onSurface} />
          <Text style={{ fontSize: 14, fontWeight: "500" }}>Quotations</Text>
        </Pressable>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button label="PDF" icon="download" variant="secondary" size="sm" onPress={openPdf} testID="download-pdf" />
          {NEXT_STATUS[q.status] ? (
            <Button label={`Mark ${NEXT_STATUS[q.status].replace("_", " ")}`} icon="check" size="sm" onPress={advance} testID="advance-status" />
          ) : null}
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.lg }}>
        <View>
          <Text style={[type.mono, { color: colors.onSurfaceMuted }]}>{q.number}</Text>
          <Text style={[type.displayLg, { marginTop: 4 }]}>{q.customer_name}</Text>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 8, alignItems: "center" }}>
            <StatusBadge status={q.status} />
            <Text style={type.caption}>Prepared by {q.created_by_name} · {new Date(q.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}</Text>
          </View>
        </View>

        <Card style={{ padding: 0 }}>
          <View style={styles.headerRow}>
            <Text style={[type.overline, { width: 40 }]}>#</Text>
            <Text style={[type.overline, { flex: 1 }]}>Item</Text>
            <Text style={[type.overline, { width: 60, textAlign: "right" }]}>QTY</Text>
            <Text style={[type.overline, { width: 90, textAlign: "right" }]}>RATE</Text>
            <Text style={[type.overline, { width: 60, textAlign: "right" }]}>DISC%</Text>
            <Text style={[type.overline, { width: 100, textAlign: "right" }]}>AMOUNT</Text>
          </View>
          {q.items.map((it, i) => (
            <View key={it.id} style={[styles.row, { borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border }]}>
              <Text style={[type.mono, { width: 40 }]}>{String(i + 1).padStart(2, "0")}</Text>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }} numberOfLines={2}>{it.name}</Text>
                <Text style={type.caption}>{it.sku}{it.room ? ` · ${it.room}` : ""}</Text>
              </View>
              <Text style={[type.mono, { width: 60, textAlign: "right" }]}>{it.qty}</Text>
              <Text style={[type.mono, { width: 90, textAlign: "right" }]}>{money(it.unit_price)}</Text>
              <Text style={[type.mono, { width: 60, textAlign: "right" }]}>{it.discount_pct}%</Text>
              <Text style={[type.mono, { width: 100, textAlign: "right", fontWeight: "700" }]}>
                {money(it.qty * it.unit_price * (1 - it.discount_pct / 100))}
              </Text>
            </View>
          ))}
        </Card>

        <Card>
          <View style={{ gap: 6, marginLeft: "auto", minWidth: 280 }}>
            {[
              ["Subtotal", q.subtotal, ""],
              ["Discount", q.discount_total, "-"],
              ["Tax", q.tax_total, ""],
            ].map(([l, v, sign]) => (
              <View key={String(l)} style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={type.bodyMuted}>{l as string}</Text>
                <Text style={type.mono}>{sign as string}{money(v as number)}</Text>
              </View>
            ))}
            <View style={{ flexDirection: "row", justifyContent: "space-between", borderTopWidth: 1, borderColor: colors.onSurface, paddingTop: 8, marginTop: 4 }}>
              <Text style={{ fontSize: 15, fontWeight: "700" }}>Grand total</Text>
              <Text style={{ fontSize: 22, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{money(q.grand_total)}</Text>
            </View>
          </View>
        </Card>

        {q.notes ? (
          <Card>
            <Text style={type.overline}>Notes</Text>
            <Text style={[type.body, { color: colors.onSurfaceSecondary, marginTop: 6 }]}>{q.notes}</Text>
          </Card>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  topbar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  headerRow: {
    flexDirection: "row", padding: spacing.md, backgroundColor: colors.surfaceTertiary,
    borderTopLeftRadius: radius.md, borderTopRightRadius: radius.md, alignItems: "center",
  },
  row: { flexDirection: "row", padding: spacing.md, alignItems: "center", gap: 8 },
});
