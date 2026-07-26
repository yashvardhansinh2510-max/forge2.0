// Ground Floor → Tiles → Selection — editable replica of the official grey
// selection sheet. Optional ?id=… reopens a saved selection document.
import { TilesDocBuilder } from "@/src/components/tiles/TilesDocBuilder";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function TilesSelectionScreen() {
  useRequireFloorAccess("ground-floor");
  return <TilesDocBuilder docType="tiles_selection" />;
}
