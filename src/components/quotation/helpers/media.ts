// Shared image-resolution helper for the Quotation Builder.
// -----------------------------------------------------------------------------
// The catalog pipeline stores real photos in Supabase via the `product_media`
// collection; the backend surfaces them as `hero_image_url` + `gallery` (and
// mirrors them into the legacy `images` field for older callers). Every
// component that renders a product photo should go through this helper so
// there's exactly one fallback order, matching what the standalone Catalog
// page already does.
import type { Product } from "./types";

export function productImageList(
  p: Pick<Product, "images" | "hero_image_url" | "gallery"> | null | undefined,
): string[] {
  if (!p) return [];
  const out: string[] = [];
  if (p.hero_image_url) out.push(p.hero_image_url);
  if (p.gallery && p.gallery.length) {
    for (const g of p.gallery) {
      if (g?.url && !out.includes(g.url)) out.push(g.url);
    }
  }
  if (p.images) {
    for (const im of p.images) {
      if (im && !out.includes(im)) out.push(im);
    }
  }
  return out;
}
