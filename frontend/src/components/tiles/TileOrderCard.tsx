// Ground Floor → Tiles → Orders — shared order-card + 4-dot stage-progress
// indicator used by both Customer-wise and Company-wise views (index.tsx)
// and referenced by the order detail page, since all three render the exact
// same underlying order shape the backend returns.
import { Feather } from "@expo/vector-icons";
import { Pressable, Text, View } from "react-native";

import { colors, icon, money, radius, shadow, spacing, type } from "@/src/theme/tokens";

export type OrderStage = "order" | "material_released" | "godown" | "dispatch" | "completed";

export type OrderCard = {
  po_id: string;
  po_number: string;
  customer_id?: string | null;
  customer_name: string;
  customer_phone?: string | null;
  supplier_id?: string | null;
  supplier_name?: string | null;
  status: string;
  stage: OrderStage;
  total_products: number;
  total_value: number;
  chalan_count: number;
  created_at: string;
};

const STAGE_LABELS: Record<OrderStage, string> = {
  order: "Order",
  material_released: "Material Released",
  godown: "Godown",
  dispatch: "Dispatch",
  completed: "Completed",
};

// Position 0-3 on the 4-dot bar. "completed" and "dispatch" both light up
// through the last dot — only the label below distinguishes them.
const STAGE_DOT_INDEX: Record<OrderStage, number> = {
  order: 0, material_released: 1, godown: 2, dispatch: 3, completed: 3,
};

export function stageLabel(stage: OrderStage): string {
  return STAGE_LABELS[stage] || STAGE_LABELS.order;
}

export function StageProgress({ stage }: { stage: OrderStage }) {
  const activeIndex = STAGE_DOT_INDEX[stage];
  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      {[0, 1, 2, 3].map((index) => (
        <View key={index} style={{ flexDirection: "row", alignItems: "center" }}>
          <View
            style={{
              width: 9, height: 9, borderRadius: 5,
              backgroundColor: index <= activeIndex ? colors.brand : colors.border,
            }}
          />
          {index < 3 ? (
            <View style={{ width: 16, height: 2, backgroundColor: index < activeIndex ? colors.brand : colors.border }} />
          ) : null}
        </View>
      ))}
    </View>
  );
}

export function TileOrderCard({ order, onPress }: { order: OrderCard; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        {
          backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
          borderWidth: 1, borderColor: colors.border,
          padding: spacing.lg, gap: spacing.sm, opacity: pressed ? 0.85 : 1,
        },
        shadow.soft,
      ]}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={2} style={type.titleSm}>{order.customer_name || "Unknown customer"}</Text>
          <Text numberOfLines={1} style={type.bodyMuted}>{order.customer_phone || "No phone on file"}</Text>
        </View>
        <Text style={type.captionStrong}>{order.po_number}</Text>
      </View>

      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Feather name="truck" size={icon.sm} color={colors.onSurfaceMuted} />
        <Text numberOfLines={1} style={[type.bodySm, { flex: 1, color: colors.onSurfaceMuted }]}>
          {order.supplier_name || "No supplier assigned"}
        </Text>
      </View>

      <View style={{ gap: spacing.xs }}>
        <StageProgress stage={order.stage} />
        <Text style={[type.captionStrong, { color: colors.brandHover }]}>{stageLabel(order.stage)}</Text>
      </View>

      <View style={{
        flexDirection: "row", justifyContent: "space-between",
        paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider,
      }}>
        <Text style={type.bodyMuted}>
          {order.total_products} product{order.total_products === 1 ? "" : "s"}
        </Text>
        <Text style={type.numeric}>{money(order.total_value)}</Text>
      </View>
    </Pressable>
  );
}
