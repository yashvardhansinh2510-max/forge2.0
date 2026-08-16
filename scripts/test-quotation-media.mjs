import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { quotationGridColumns } from "../src/components/quotation/helpers/responsive.ts";
import { productImageList } from "../src/components/quotation/helpers/media.ts";

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

// Keep this zero-config Node contract free of app-runtime imports. Importing
// tilePresentation used its @/ alias, which Node's strip-types runner cannot
// resolve and caused the quotation-media release gate to fail before running
// a single assertion.
const productImageSource = readFileSync(new URL("../src/components/ProductImage.tsx", import.meta.url), "utf8");
assert.match(productImageSource, /storage\/v1\/render\/image\/public/);
assert.match(productImageSource, /contentFit = "contain"/);
assert.doesNotMatch(productImageSource, /rotate: "90deg"/);

const builderSource = readFileSync(new URL("../src/components/quotation/context/BuilderContext.tsx", import.meta.url), "utf8");
const catalogServiceSource = readFileSync(new URL("../src/services/catalogService.ts", import.meta.url), "utf8");
assert.ok(builderSource.includes('api.get<Customer[]>("/customers", request)'), "missing essential customer bootstrap request");
assert.match(builderSource, /catalogReferences\.categories<Category\[\]>\(null, request\)/);
assert.match(builderSource, /catalogReferences\.brands<Brand\[\]>\(request\)/);
for (const endpoint of ["/products/recent", "/products/frequent", "/quotations/recent?limit=10", "/referrers"]) {
  assert.ok(builderSource.includes(endpoint), `missing lazy quotation request: ${endpoint}`);
}
assert.match(builderSource, /q\.trim\(\) \? 300 : 0/);
assert.match(builderSource, /loadMoreController\.current\?\.abort\(\)/);
assert.match(catalogServiceSource, /signal\?: AbortSignal/);
assert.match(builderSource, /retryReferenceData/);
assert.match(builderSource, /controller\.abort\(\)/);

console.log("quotation media/layout helpers: 30 assertions passed");
