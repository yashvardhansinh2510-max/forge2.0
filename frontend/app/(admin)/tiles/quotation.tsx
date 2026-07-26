// Ground Floor → Tiles → Quotation — editable replica of the official
// light-blue quotation sheet. Optional ?id=… reopens a saved quotation.
import { TilesDocBuilder } from "@/src/components/tiles/TilesDocBuilder";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function TilesQuotationScreen() {
  useRequireFloorAccess("ground-floor");
  return <TilesDocBuilder docType="tiles_quotation" />;
}
