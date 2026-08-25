// Ground Floor → Tiles → Selection — editable replica of the official grey
// selection sheet. Optional ?id=… reopens a saved selection document.
import { LazyQuotationBuilder } from "@/src/components/quotation/LazyQuotationBuilder";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function TilesSelectionScreen() {
  useRequireFloorAccess("ground-floor");
  return <LazyQuotationBuilder mode="tiles_selection" />;
}
