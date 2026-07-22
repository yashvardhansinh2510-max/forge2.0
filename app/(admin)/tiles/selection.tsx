// Ground Floor → Tiles → Selection — editable replica of the official grey
// selection sheet. Optional ?id=… reopens a saved selection document.
import { TilesDocBuilder } from "@/src/components/tiles/TilesDocBuilder";

export default function TilesSelectionScreen() {
  return <TilesDocBuilder docType="tiles_selection" />;
}
