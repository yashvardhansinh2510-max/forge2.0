import { useLocalSearchParams } from "expo-router";
import { NotebookScreen } from "@/src/components/notebook/NotebookScreen";

/** Converted notebook rows retain the same ID and appear in this second view. */
export default function QuotationFollowUpScreen() {
  const { floor } = useLocalSearchParams<{ floor?: string }>();
  const isFurniture = floor === "furniture";
  return <NotebookScreen floorId={isFurniture ? "third-floor" : "second-floor"} floorName={isFurniture ? "Furniture Floor" : "Kitchen Floor"} view="quotation" />;
}
