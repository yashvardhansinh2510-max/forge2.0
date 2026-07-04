import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AdminPage } from "@/src/components/AdminPage";
import { Badge, Card, EmptyState, Skeleton } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { colors, spacing, type } from "@/src/theme/tokens";

type Customer = { id: string; name: string; company?: string | null; email: string; city?: string | null; tier: "retail" | "trade" | "vip"; phone?: string | null };

const tierTone: Record<string, "success" | "info" | "neutral"> = { vip: "success", trade: "info", retail: "neutral" };

export default function Customers() {
  const [items, setItems] = useState<Customer[] | null>(null);
  useEffect(() => { api.get<Customer[]>("/customers").then(setItems); }, []);

  return (
    <AdminPage title="Customers" subtitle={`${items?.length ?? "—"} accounts · Trade partners, VIPs & retail buyers.`}>
      {!items ? (
        <Card style={{ padding: 0 }}>
          {Array.from({ length: 4 }).map((_, i) => <View key={i} style={styles.row}><Skeleton w="60%" /></View>)}
        </Card>
      ) : items.length === 0 ? (
        <EmptyState icon="users" title="No customers yet" />
      ) : (
        <Card style={{ padding: 0 }}>
          {items.map((c, i) => (
            <Pressable
              key={c.id}
              testID={`customer-${c.id}`}
              style={({ pressed }) => [styles.row, {
                borderTopWidth: i === 0 ? 0 : StyleSheet.hairlineWidth,
                borderColor: colors.border,
                backgroundColor: pressed ? colors.surfaceTertiary : "transparent",
              }]}
            >
              <View style={styles.initials}><Text style={{ color: colors.onBrand, fontWeight: "700" }}>{c.name[0]}</Text></View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 14, fontWeight: "600" }}>{c.company || c.name}</Text>
                <Text style={type.caption}>{c.email}{c.city ? ` · ${c.city}` : ""}</Text>
              </View>
              <Badge label={c.tier.toUpperCase()} tone={tierTone[c.tier]} />
            </Pressable>
          ))}
        </Card>
      )}
    </AdminPage>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md },
  initials: { width: 36, height: 36, borderRadius: 999, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" },
});
