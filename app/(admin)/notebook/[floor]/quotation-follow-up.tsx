import { Redirect, useLocalSearchParams } from "expo-router";
import { NotebookScreen } from "@/src/components/notebook/NotebookScreen";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { FURNITURE_FLOOR_ID, KITCHEN_FLOOR_ID } from "@/src/constants/floors";

/** Converted notebook rows retain the same ID and appear in this second view. */
export default function QuotationFollowUpScreen() {
  const { floor } = useLocalSearchParams<{ floor?: string }>();
  const isFurniture = floor === "furniture";
  const floorId = isFurniture ? FURNITURE_FLOOR_ID : KITCHEN_FLOOR_ID;
  useRequireFloorAccess(floorId);
  if (floor !== "kitchen" && floor !== "furniture") return <Redirect href="/(admin)/dashboard" />;
  return <NotebookScreen floorId={floorId} floorName={isFurniture ? "Furniture Floor" : "Kitchen Floor"} view="quotation" />;
}
