// Shared image-resolution helper for the Quotation Builder.
// -----------------------------------------------------------------------------
// The catalog pipeline stores real photos in Supabase via the `product_media`
// collection; the backend surfaces them as `hero_image_url` + `gallery` (and
// mirrors them into the legacy `images` field for older callers). Every
// component that renders a product photo should go through this helper so
// there's exactly one fallback order, matching what the standalone Catalog
// page already does.
import type { Product, ProductVariant } from "./types";

export function productImageList(
  p: Pick<Product, "images" | "hero_image_url" | "gallery" | "family_key"> | null | undefined,
): string[] {
  if (!p) return [];
  type Candidate = {
    url: string;
    quality: number;
    pixels: number;
    familyMatch: number;
    primary: number;
    order: number;
  };
  const qualityRank: Record<string, number> = {
    excellent: 4,
    good: 3,
    acceptable: 2,
    poor: 1,
  };
  const candidates: Candidate[] = [];
  const seen = new Set<string>();
  const add = (url: string | null | undefined, meta: { quality?: string; width?: number | null; height?: number | null; family_key?: string | null; is_primary?: boolean } = {}, primary = false) => {
    if (!url || seen.has(url)) return;
    seen.add(url);
    candidates.push({
      url,
      quality: qualityRank[String(meta.quality || "").toLowerCase()] || 0,
      pixels: Math.max(0, Number(meta.width || 0)) * Math.max(0, Number(meta.height || 0)),
      familyMatch: p.family_key && meta.family_key ? (p.family_key === meta.family_key ? 1 : -1) : 0,
      primary: primary || meta.is_primary === true ? 1 : 0,
      order: candidates.length,
    });
  };

  // Gallery metadata is authoritative for source quality, but family identity
  // wins first. A primary image is still preferred when identity and quality
  // are tied; a better-looking sibling image must never replace the exact
  // product photo merely because it has more pixels.
  const gallery = p.gallery || [];
  const heroMeta = gallery.find((g) => g?.url === p.hero_image_url);
  add(p.hero_image_url, heroMeta, true);
  for (const g of gallery) add(g?.url, g);
  for (const im of p.images || []) add(im);

  return candidates
    .sort((a, b) => b.familyMatch - a.familyMatch || b.quality - a.quality || b.pixels - a.pixels || b.primary - a.primary || a.order - b.order)
    .map((candidate) => candidate.url);
}

// Resolves which images to show for the currently-selected finish/variant.
// Some supplier source files ship a finish with no photo of its own (e.g. a
// row the supplier simply never photographed) — when that happens we must
// never leave the gallery empty, since every finish switch should show
// *something*. Falls back, in order: the selected variant's own photo → any
// other sibling finish's photo (first match in swatch order) → the base
// product's own images. `isFallback` tells the caller when the displayed
// photo is a stand-in for a different finish, so the UI can say so rather
// than silently implying it's the exact selected finish's own photograph.
export function resolveVariantImages(
  product: Pick<Product, "images" | "hero_image_url" | "gallery" | "variants" | "sku">,
  selectedVariant?: Pick<ProductVariant, "sku" | "image"> | null,
): { images: string[]; isFallback: boolean } {
  const base = productImageList(product);
  const ownImage = selectedVariant ? selectedVariant.image : (base[0] ?? null);
  if (ownImage) {
    const images = base.includes(ownImage)
      ? [ownImage, ...base.filter((u) => u !== ownImage)]
      : [ownImage, ...base];
    return { images, isFallback: false };
  }
  const currentSku = selectedVariant?.sku ?? product.sku;
  const sibling = (product.variants || []).find((v) => v.sku !== currentSku && v.image);
  if (sibling?.image) {
    const images = base.includes(sibling.image)
      ? [sibling.image, ...base.filter((u) => u !== sibling.image)]
      : [sibling.image, ...base];
    return { images, isFallback: true };
  }
  return { images: base, isFallback: false };
}
