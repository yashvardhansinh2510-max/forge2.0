import assert from "node:assert/strict";

import { quotationGridColumns } from "../src/components/quotation/helpers/responsive.ts";
import { productImageList } from "../src/components/quotation/helpers/media.ts";

assert.equal(quotationGridColumns(640), 1);
assert.equal(quotationGridColumns(768), 2);
assert.equal(quotationGridColumns(1040), 2);
assert.equal(quotationGridColumns(1920), 2);
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

console.log("quotation media/layout helpers: 7 assertions passed");
