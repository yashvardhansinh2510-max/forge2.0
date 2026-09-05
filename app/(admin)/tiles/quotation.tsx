// Ground Floor → Tiles → Quotation — editable replica of the official
// light-blue quotation sheet. Optional ?id=… reopens a saved quotation.
import { LazyQuotationBuilder } from "@/src/components/quotation/LazyQuotationBuilder";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function TilesQuotationScreen() {
  useRequireFloorAccess("ground-floor");
  return <LazyQuotationBuilder mode="tiles_quotation" />;
}
