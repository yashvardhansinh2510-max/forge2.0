// Ground Floor → Tiles → Selection — editable replica of the official grey
// selection sheet. Optional ?id=… reopens a saved selection document.
import { QuotationBuilder } from "@/src/components/quotation";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function TilesSelectionScreen() {
  useRequireFloorAccess("ground-floor");
  return <QuotationBuilder mode="tiles_selection" />;
}
