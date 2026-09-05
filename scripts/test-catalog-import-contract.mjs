import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const screen = readFileSync(new URL("../app/(admin)/catalog/import.tsx", import.meta.url), "utf8");

// Large import review must not fan out an arbitrary number of row writes.
assert.match(screen, /const ROW_PATCH_CONCURRENCY = 4/);
assert.match(screen, /async function runBounded/);
assert.match(screen, /runBounded\(candidates/);

// Review is page-bounded and the FlatList retains a small render window.
assert.match(screen, /const REVIEW_PAGE_SIZE = 50/);
assert.match(screen, /const pageRows = current\.rows\.slice/);
assert.match(screen, /data=\{pageRows\}/);
assert.match(screen, /initialNumToRender=\{12\}/);
assert.match(screen, /maxToRenderPerBatch=\{12\}/);

// The async approval contract is idempotent at the UI boundary and exposes
// progress plus an actionable retry for a failed individual row.
assert.match(screen, /status !== "processing"/);
assert.match(screen, /setInterval\(refresh, 2000\)/);
assert.match(screen, /disabled=\{accepted === 0 \|\| changesInFlight \|\| processing\}/);
assert.match(screen, /\/rows\/\$\{row\.row_id\}\/retry/);
assert.match(screen, /retry-import-\$\{item\.row_id\}/);
assert.match(screen, /accessibilityLiveRegion="polite"/);

console.log("Catalog import review contracts passed");
