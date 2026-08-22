import { useLocalSearchParams } from "expo-router";

import WalkInsScreen from "../../walkins";

/** Converted leads retain the familiar Walk-ins workspace with one Price field. */
export default function QuotationFollowUpScreen() {
  const { floor } = useLocalSearchParams<{ floor?: string }>();
  const isFurniture = floor === "furniture";
  return (
    <WalkInsScreen
      fixedFloorId={isFurniture ? "third-floor" : "second-floor"}
      title={isFurniture ? "Furniture Quotation Follow-up" : "Kitchen Quotation Follow-up"}
      quotationFollowup
    />
  );
}
