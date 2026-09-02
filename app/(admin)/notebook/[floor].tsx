import { useLocalSearchParams } from "expo-router";
import { NotebookScreen } from "@/src/components/notebook/NotebookScreen";

/** The two notebook floors share one floor-pinned register implementation. */
export default function FloorWalkIns() {
  const { floor } = useLocalSearchParams<{ floor?: string }>();
  const isFurniture = floor === "furniture";
  return <NotebookScreen floorId={isFurniture ? "third-floor" : "second-floor"} floorName={isFurniture ? "Furniture Floor" : "Kitchen Floor"} view="followups" />;
}
