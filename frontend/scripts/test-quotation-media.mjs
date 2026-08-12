import assert from "node:assert/strict";

import { quotationGridColumns } from "../src/components/quotation/helpers/responsive.ts";
import { productImageList } from "../src/components/quotation/helpers/media.ts";
import { TILE_IMAGE_ASPECT_RATIO, tilesPickerColumns } from "../src/components/tiles/tilePresentation.ts";

assert.equal(TILE_IMAGE_ASPECT_RATIO, 16 / 10);
assert.equal(tilesPickerColumns(375), 1);
assert.equal(tilesPickerColumns(430), 1);
assert.equal(tilesPickerColumns(767), 1);
assert.equal(tilesPickerColumns(768), 2);
assert.equal(tilesPickerColumns(1280), 2);

// Phone, tablet and wide-picker widths must all preserve the shop-style
// two-column grid; 280px is the supported lower bound for a picker viewport.
assert.equal(quotationGridColumns(280), 2);
assert.equal(quotationGridColumns(320), 2);
assert.equal(quotationGridColumns(375), 2);
assert.equal(quotationGridColumns(390), 2);
assert.equal(quotationGridColumns(430), 2);
assert.equal(quotationGridColumns(640), 2);
assert.equal(quotationGridColumns(768), 2);
assert.equal(quotationGridColumns(800), 2);
assert.equal(quotationGridColumns(810), 2);
assert.equal(quotationGridColumns(1040), 2);
assert.equal(quotationGridColumns(1920), 2);
assert.equal(quotationGridColumns(279), 1);
assert.deepEqual(productImageList({
  hero_image_url: "hero",
  gallery: [{ url: "gallery" }, { url: "hero" }],
  images: ["legacy", "gallery"],
}), ["hero", "gallery", "legacy"]);
assert.deepEqual(productImageList({
  hero_image_url: "thumbnail",
  family_key: "omega",
  gallery: [
    { url: "thumbnail", family_key: "omega", quality: "poor", width: 103, height: 162, is_primary: true },
    { url: "wrong-family", family_key: "sigma", quality: "acceptable", width: 365, height: 547 },
  ],
  images: [],
}), ["thumbnail", "wrong-family"]);
assert.deepEqual(productImageList({
  hero_image_url: "thumbnail",
  family_key: "omega",
  gallery: [
    { url: "thumbnail", family_key: "omega", quality: "poor", width: 103, height: 162, is_primary: true },
    { url: "original", family_key: "omega", quality: "acceptable", width: 365, height: 547 },
  ],
  images: [],
}), ["original", "thumbnail"]);

console.log("quotation media/layout helpers: 21 assertions passed");
