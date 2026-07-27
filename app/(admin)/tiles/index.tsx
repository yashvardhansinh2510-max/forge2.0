// Quotation Tiles — single tab listing every Ground Floor tiles Selection
// and Quotation, any stage, with two entry points to start a new one. See
// docs/superpowers/specs/2026-07-27-quotation-tiles-workflow-design.md.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { Button, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api/client";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, money, radius, spacing, type } from "@/src/theme/tokens";
import { tilesStageLabel } from "@/src/components/tiles/tilesStage";

type TilesDoc = {
  id: string; number: string; doc_type: "tiles_selection" | "tiles_quotation";
  status: string; customer_name: string; grand_total: number; updated_at: string;
};

export default function QuotationTilesList() {
  useRequireFloorAccess("ground-floor");
  const router = useRouter();
  const [docs, setDocs] = useState<TilesDoc[] | null>(null);

  const load = useCallback(async () => {
    const [selections, quotations] = await Promise.all([
      api.get<TilesDoc[]>("/quotations?doc_type=tiles_selection", { floorId: "ground-floor" }),
      api.get<TilesDoc[]>("/quotations?doc_type=tiles_quotation", { floorId: "ground-floor" }),
    ]);
    const merged = [...selections, ...quotations].sort(
      (a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""),
    );
    setDocs(merged);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openDoc = (doc: TilesDoc) => {
    const route = doc.doc_type === "tiles_selection" ? "selection" : "quotation";
    router.push(`/(admin)/tiles/${route}?id=${doc.id}` as any);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <View style={styles.header}>
        <View>
          <Text style={type.overline}>Ground Floor · Tiles</Text>
          <Text style={type.titleMd}>Quotation Tiles</Text>
        </View>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button
            label="Create new selection"
            variant="ghost"
            icon="grid"
            onPress={() => router.push("/(admin)/tiles/selection" as any)}
            testID="tiles-create-selection"
          />
          <Button
            label="Create new quotation"
            icon="layout"
            onPress={() => router.push("/(admin)/tiles/quotation" as any)}
            testID="tiles-create-quotation"
          />
        </View>
      </View>

      {docs === null ? null : docs.length === 0 ? (
        <EmptyState icon="layers" title="No selections or quotations yet" subtitle="Create one to get started." />
      ) : (
        <FlatList
          data={docs}
          keyExtractor={(d) => d.id}
          contentContainerStyle={{ padding: spacing.lg, gap: 8 }}
          renderItem={({ item }) => (
            <Pressable style={styles.row} onPress={() => openDoc(item)} testID={`tiles-doc-${item.id}`}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }} numberOfLines={1}>
                  {item.customer_name || "Unnamed customer"}
                </Text>
                <Text style={type.caption} numberOfLines={1}>{item.number} · {tilesStageLabel(item.doc_type, item.status)}</Text>
              </View>
              <Text style={[type.mono, { fontSize: 13, fontWeight: "600" }]}>{money(item.grand_total || 0)}</Text>
              <Feather name="chevron-right" size={16} color={colors.onSurfaceMuted} />
            </Pressable>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  row: {
    flexDirection: "row", alignItems: "center", gap: 10,
    padding: spacing.md, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
});
