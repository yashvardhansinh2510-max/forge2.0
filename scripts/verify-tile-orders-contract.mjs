import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const screen = readFileSync(resolve("app/(admin)/tiles/orders/index.tsx"), "utf8");
const client = readFileSync(resolve("src/api/tileOrders.ts"), "utf8");

const requiredScreenTokens = [
  '["customer", "Customer"]',
  '["brands", "Brands"]',
  '["dispatch-list", "Dispatch List"]',
  '["material-register", "Material Movement Register"]',
  "View Chalan",
  "Print Chalan",
  "View Dispatch",
  "dispatchRowKey",
];
const requiredClientTokens = [
  "releaseMaterial:",
  "moveToGodown:",
  "dispatchFromReleased:",
  "dispatchFromGodown:",
  "listDispatchList:",
  "listMovements:",
  "chalanPdfUrl:",
];

for (const token of requiredScreenTokens) {
  if (!screen.includes(token)) throw new Error(`Tile Orders screen contract missing: ${token}`);
}
for (const token of requiredClientTokens) {
  if (!client.includes(token)) throw new Error(`Tile Orders API contract missing: ${token}`);
}

console.log("Tile Orders workflow route contract verified.");