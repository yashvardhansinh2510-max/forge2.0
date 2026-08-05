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

console.log("quotation media/layout helpers: 5 assertions passed");
