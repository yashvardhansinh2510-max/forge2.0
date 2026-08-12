// Shared visual contract for the interactive tiles surfaces. Keeping this
// separate from the printed-document renderer ensures phone and picker layouts
// cannot quietly drift back to square/portrait frames.
export const TILE_IMAGE_ASPECT_RATIO = 16 / 10;

export function tilesPickerColumns(viewportWidth: number): 1 | 2 {
  return viewportWidth < 768 ? 1 : 2;
}
