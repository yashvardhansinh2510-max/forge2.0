// Ground Floor → Tiles → Quotation — editable replica of the official
// light-blue quotation sheet. Optional ?id=… reopens a saved quotation.
import { TilesDocBuilder } from "@/src/components/tiles/TilesDocBuilder";

export default function TilesQuotationScreen() {
  return <TilesDocBuilder docType="tiles_quotation" />;
}
