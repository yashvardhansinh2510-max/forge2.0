import { useLocalSearchParams } from "expo-router";
import { Text, View } from "react-native";

import { FURNITURE_FLOOR_ID, KITCHEN_FLOOR_ID, NOTEBOOK_FLOOR_LABELS } from "@/src/constants/floors";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function NotebookRoute() {
  const { floor } = useLocalSearchParams<{ floor: string }>();
  const floorId = floor === "furniture" ? FURNITURE_FLOOR_ID : KITCHEN_FLOOR_ID;
  useRequireFloorAccess(floorId);
  return (
    <View style={{ flex: 1, padding: 24 }}>
      <Text>{NOTEBOOK_FLOOR_LABELS[floorId]}</Text>
    </View>
  );
}
