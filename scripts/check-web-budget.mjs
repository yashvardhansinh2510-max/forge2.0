import { readFile, stat } from "node:fs/promises";
import { gzipSync } from "node:zlib";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(SCRIPT_DIR, "..", "dist", "client");
const ROUTES = ["login.html", "dashboard.html"];
const MAX_INITIAL_JS_GZIP = 350 * 1024;

let failed = false;
for (const route of ROUTES) {
  const html = await readFile(path.join(ROOT, route), "utf8");
  const assets = [...new Set(
    [...html.matchAll(/(?:src|href)=["']\/?([^"']+\.js)["']/g)].map((match) => match[1]),
  )];
  let gzipBytes = 0;
  let rawBytes = 0;
  const assetStats = [];
  for (const asset of assets) {
    const bytes = await readFile(path.join(ROOT, asset));
    const raw = (await stat(path.join(ROOT, asset))).size;
    const gzip = gzipSync(bytes, { level: 9 }).length;
    rawBytes += raw;
    gzipBytes += gzip;
    assetStats.push({ asset, raw, gzip });
  }
  const result = {
    route,
    assets: assets.length,
    rawKb: Math.round(rawBytes / 1024),
    gzipKb: Math.round(gzipBytes / 1024),
    budgetKb: Math.round(MAX_INITIAL_JS_GZIP / 1024),
    largestAssets: assetStats
      .sort((left, right) => right.gzip - left.gzip)
      .slice(0, 5)
      .map(({ asset, gzip }) => ({ asset, gzipKb: Math.round(gzip / 1024) })),
  };
  console.log(JSON.stringify(result));
  if (gzipBytes > MAX_INITIAL_JS_GZIP) failed = true;
}

if (failed) {
  console.error("Initial JavaScript exceeds the 350 KB gzip mobile release budget.");
  process.exitCode = 1;
}
