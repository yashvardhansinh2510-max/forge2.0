// Shared visual contract for the interactive tiles surfaces. Keeping this
// separate from the printed-document renderer ensures phone and picker layouts
// cannot quietly drift back to square/portrait frames.
import { PRODUCT_IMAGE_ASPECT_RATIO } from "@/src/theme/tokens";
import { layout } from "@/src/design/tokens";

export const TILE_IMAGE_ASPECT_RATIO = PRODUCT_IMAGE_ASPECT_RATIO;

export function tilesPickerColumns(viewportWidth: number): 1 | 2 {
  return viewportWidth < layout.bp.tabletPortrait ? 1 : 2;
}

/** Consistent product identity on every operational Tile Orders surface. */
export function tileIdentityMeta(parts: (string | null | undefined)[], sku?: string | null): string {
  return [...parts.filter(Boolean), sku ? `SKU · ${sku}` : null].filter(Boolean).join(" · ") || "—";
}
