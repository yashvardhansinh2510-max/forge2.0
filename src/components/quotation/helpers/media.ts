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
