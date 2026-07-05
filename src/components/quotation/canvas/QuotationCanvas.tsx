// QuotationCanvas — the DnD flat list that mixes room headers + lines.
import { View } from "react-native";
import DraggableFlatList, { RenderItemParams } from "react-native-draggable-flatlist";

import { EmptyState } from "@/src/components/ui";
import { spacing } from "@/src/theme/tokens";

import { useBuilder } from "../context/BuilderContext";
import type { BuilderRow } from "../helpers/types";
import { LineRow } from "./LineRow";
import { RoomHeaderRow } from "./RoomHeaderRow";

export function QuotationCanvas() {
  const b = useBuilder();

  const renderItem = ({ item, drag, isActive }: RenderItemParams<BuilderRow>) => {
    if (item.kind === "room-header") {
      return (
        <RoomHeaderRow
          roomName={item.roomName}
          itemCount={item.itemCount}
          subtotal={item.subtotal}
          collapsed={item.collapsed}
          drag={drag}
          isActive={isActive}
        />
      );
    }
    return (
      <LineRow
        line={item.line}
        drag={drag}
        isActive={isActive}
        catDiscs={b.s.categoryDiscounts}
        projDisc={b.s.projectDiscount}
      />
    );
  };

  if (b.flatRows.length === 0 || (b.flatRows.length <= b.s.rooms.length && b.s.lines.length === 0)) {
    return (
      <View style={{ flex: 1, justifyContent: "center" }}>
        <EmptyState
          icon="file-plus"
          title="Add your first product"
          subtitle="Search on the left and tap to add. Everything totals live."
        />
      </View>
    );
  }

  return (
    <DraggableFlatList
      data={b.flatRows}
      keyExtractor={(row) => row.id}
      onDragEnd={b.onLinesDragEnd}
      renderItem={renderItem}
      contentContainerStyle={{ padding: spacing.md, gap: 6, paddingBottom: 32 }}
      activationDistance={10}
      keyboardShouldPersistTaps="handled"
      testID="receipt-list"
    />
  );
}
