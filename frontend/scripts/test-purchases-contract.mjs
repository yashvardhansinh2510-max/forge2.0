import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const screen = readFileSync(new URL("../app/(admin)/purchases.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../src/api/purchases.ts", import.meta.url), "utf8");

assert.match(api, /items\/page/);
assert.match(api, /limit \?\? 30/);
assert.match(api, /signal\?: AbortSignal/);
assert.match(screen, /requestController\.current\?\.abort\(\)/);
assert.match(screen, /seq !== requestSeq\.current/);
assert.match(screen, /<FlatList/);
assert.match(screen, /initialNumToRender=\{8\}/);
assert.match(screen, /purchases-filter-button/);
assert.match(screen, /minHeight: 44/);
assert.doesNotMatch(screen, /rows\.filter\(\(candidate\) => candidate\.customer_id/);
assert.doesNotMatch(screen, /<ScrollView[^>]*>\s*<FlatList/);

console.log("Purchases mobile/API contracts passed");
