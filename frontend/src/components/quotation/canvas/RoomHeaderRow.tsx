// Room header row — draggable, inline-renameable, with room actions.
import { Feather } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, font, money, radius, type } from "@/src/theme/tokens";
import { color as ds } from "@/src/design/tokens";

import { useBuilder } from "../context/BuilderContext";
import { grabCursor } from "../shared/grabCursor";

export function RoomHeaderRow({
  roomName, itemCount, subtotal, collapsed, drag, isActive,
}: {
  roomName: string;
  itemCount: number;
  subtotal: number;
  collapsed: boolean;
  drag: () => void;
  isActive: boolean;
}) {
  const b = useBuilder();
  const isActiveRoom = b.s.activeRoom === roomName;
  const isRenaming = b.inlineRenameRoom === roomName;

  const commit = () => {
    if (b.inlineRenameRoom) b.renameRoom(b.inlineRenameRoom, b.inlineRenameValue);
    b.setInlineRenameRoom(null);
  };

  return (
    <View style={[styles.wrap, isActiveRoom && styles.wrapActive, isActive && { opacity: 0.7 }]}>
      <Pressable
        onLongPress={drag}
        delayLongPress={160}
        hitSlop={6}
        style={[styles.dragHandle, grabCursor]}
        testID={`room-drag-${roomName}`}
      >
        <Feather name="menu" size={13} color={colors.onSurfaceMuted} />
      </Pressable>
      <Pressable onPress={() => b.toggleCollapse(roomName)} testID={`room-toggle-${roomName}`} hitSlop={6}>
        <Feather name={collapsed ? "chevron-right" : "chevron-down"} size={16} color={colors.onSurface} />
      </Pressable>
      {isRenaming ? (
        <TextInput
          testID={`room-inline-input-${roomName}`}
          value={b.inlineRenameValue}
          onChangeText={b.setInlineRenameValue}
          autoFocus
          onBlur={commit}
          onSubmitEditing={commit}
          onKeyPress={(e) => { if ((e.nativeEvent as any).key === "Escape") b.setInlineRenameRoom(null); }}
          returnKeyType="done"
          style={styles.inlineInput}
          selectTextOnFocus
        />
      ) : (
        <Pressable onPress={() => b.setActiveRoom(roomName)} style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.roomName} numberOfLines={1}>{roomName}</Text>
          <Text style={type.caption} numberOfLines={1}>{itemCount} items · {money(subtotal)}</Text>
        </Pressable>
      )}
      <Pressable
        testID={`room-rename-${roomName}`}
        hitSlop={8}
        onPress={() => {
          if (isRenaming) commit();
          else { b.setInlineRenameRoom(roomName); b.setInlineRenameValue(roomName); }
        }}
      >
        <Feather name={isRenaming ? "check" : "edit-2"} size={14} color={isRenaming ? ds.brass : colors.onSurfaceMuted} />
      </Pressable>
      <Pressable testID={`room-dup-${roomName}`} hitSlop={8} onPress={() => b.duplicateRoom(roomName)}>
        <Feather name="copy" size={14} color={colors.onSurfaceMuted} />
      </Pressable>
      <Pressable testID={`room-delete-${roomName}`} hitSlop={8} onPress={() => b.deleteRoom(roomName)}>
        <Feather name="trash-2" size={14} color={colors.error} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 10, paddingHorizontal: 10,
    borderRadius: radius.sm, backgroundColor: colors.surfaceSubtle,
    borderLeftWidth: 3, borderLeftColor: "transparent", marginTop: 6,
  },
  wrapActive: { borderLeftColor: ds.brass, backgroundColor: ds.brassTint },
  dragHandle: {
    width: 20, alignItems: "center", justifyContent: "center", alignSelf: "stretch",
    marginRight: -2, marginLeft: -4,
  },
  roomName: { fontSize: 13, fontFamily: font.semibold, fontWeight: "600", color: colors.onSurface, letterSpacing: -0.1 },
  inlineInput: {
    flex: 1, fontSize: 14, fontFamily: font.semibold, fontWeight: "600", color: colors.onSurface,
    paddingVertical: 4, paddingHorizontal: 6, borderRadius: 6,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: ds.brassLine,
  },
});
