// Shared visual contract for the interactive tiles surfaces. Keeping this
// separate from the printed-document renderer ensures phone and picker layouts
// cannot quietly drift back to square/portrait frames.
import { PRODUCT_IMAGE_ASPECT_RATIO } from "@/src/theme/tokens";

export const TILE_IMAGE_ASPECT_RATIO = PRODUCT_IMAGE_ASPECT_RATIO;

export function tilesPickerColumns(viewportWidth: number): 1 | 2 {
  return viewportWidth < 768 ? 1 : 2;
}
