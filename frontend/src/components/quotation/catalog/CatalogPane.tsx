// The left/mobile Catalog Pane — search box, tabs, virtualised list.
import { Feather } from "@expo/vector-icons";
import { ActivityIndicator, FlatList, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { EmptyState } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
import { color as ds } from "@/src/design/tokens";

import { useBuilder } from "../context/BuilderContext";
import { PickerCard } from "./PickerCard";
import type { Product } from "../helpers/types";
import { isNearScrollEnd } from "@/src/utils/scrollEnd";

export function CatalogPane({
  onOpenDetails,
  compactHeader = false,
}: {
  onOpenDetails?: (p: Product) => void;
  compactHeader?: boolean;
}) {
  const b = useBuilder();

  return (
    <View style={styles.panel}>
      <View style={[styles.head, compactHeader && { padding: spacing.sm }]}>
        {!compactHeader ? <Text style={type.titleMd}>Add products</Text> : null}
        <View style={styles.searchWrap}>
          <Feather name="search" size={16} color={colors.onSurfaceMuted} />
          <TextInput
            ref={b.searchRef}
            testID="builder-search"
            value={b.q}
            onChangeText={(v) => { b.setQ(v); b.setPickerTab("search"); }}
            placeholder={Platform.OS === "web" ? "Search catalog · ⌘K · Enter to add" : "Search catalog"}
            placeholderTextColor={colors.onSurfaceMuted}
            style={styles.searchInput}
            onSubmitEditing={() => b.pickerList[0] && b.addFromProduct(b.pickerList[0])}
            returnKeyType="search"
          />
          {b.q ? (
            <Pressable hitSlop={8} onPress={() => b.setQ("")} testID="builder-search-clear">
              <Feather name="x" size={16} color={colors.onSurfaceMuted} />
            </Pressable>
          ) : null}
        </View>
        <View style={styles.tabs}>
          {[
            { k: "search" as const, label: "All", icon: "search" as const },
            { k: "recent" as const, label: "Recent", icon: "clock" as const },
            { k: "frequent" as const, label: "Frequent", icon: "star" as const },
          ].map((t) => {
            const on = b.pickerTab === t.k;
            return (
              <Pressable
                key={t.k}
                testID={`picker-tab-${t.k}`}
                onPress={() => b.setPickerTab(t.k)}
                style={[styles.tab, on && styles.tabActive]}
              >
                <Feather name={t.icon} size={12} color={on ? colors.onBrand : colors.onSurfaceMuted} />
                <Text style={{ fontSize: 12, fontWeight: "600", color: on ? colors.onBrand : colors.onSurfaceSecondary }}>
                  {t.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <FlatList
        data={b.pickerList}
        keyExtractor={(p) => p.id}
        contentContainerStyle={{ padding: spacing.md, gap: 8, paddingBottom: 24 }}
        keyboardShouldPersistTaps="handled"
        renderItem={({ item }) => (
          <PickerCard
            product={item}
            onQuickAdd={(p, v) => b.addFromProduct(p, v)}
            onOpenDetails={onOpenDetails ?? ((p) => b.setAssistantFocus({ kind: "product", product_id: p.id, product: p }))}
          />
        )}
        removeClippedSubviews
        initialNumToRender={12}
        maxToRenderPerBatch={12}
        windowSize={7}
        onEndReached={() => { if (b.pickerTab === "search") b.loadMoreProducts(); }}
        onEndReachedThreshold={0.6}
        onScroll={(e) => { if (b.pickerTab === "search" && isNearScrollEnd(e.nativeEvent, 0.6)) b.loadMoreProducts(); }}
        scrollEventThrottle={50}
        ListFooterComponent={
          b.pickerTab === "search" && b.productLoadingMore ? (
            <View style={{ paddingVertical: 16, alignItems: "center" }}>
              <ActivityIndicator size="small" color={ds.brass} />
            </View>
          ) : null
        }
        ListEmptyComponent={
          <EmptyState
            icon={b.pickerTab === "search" ? "search" : b.pickerTab === "recent" ? "clock" : "star"}
            title={b.pickerTab === "search" ? "Type to search" : b.pickerTab === "recent" ? "No recent products" : "No favourites yet"}
            subtitle={b.pickerTab === "search" ? "Search across brands, SKUs and tags." : "Add products to a quotation to see them here."}
          />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { flex: 1, backgroundColor: colors.surface },
  head: {
    padding: spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    backgroundColor: colors.surface, gap: spacing.sm,
  },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 8,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    paddingHorizontal: 12, borderRadius: radius.md,
  },
  searchInput: { flex: 1, fontSize: 14, paddingVertical: 10, color: colors.onSurface },
  tabs: { flexDirection: "row", gap: 6, backgroundColor: colors.surfaceTertiary, padding: 3, borderRadius: radius.md },
  tab: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: 7, borderRadius: radius.sm },
  tabActive: { backgroundColor: colors.brand },
});
