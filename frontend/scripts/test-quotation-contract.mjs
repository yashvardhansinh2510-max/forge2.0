import assert from "node:assert/strict";

import { computeQuotationTotals } from "../src/components/quotation/helpers/totals.ts";
import { enqueueQuotationPersist } from "../src/components/quotation/helpers/autosave.ts";

const totals = computeQuotationTotals([
  { qty: 2, unitPrice: 2170 },
  { qty: 1, unitPrice: 2000, discountAmount: 100 },
], 100);

assert.deepEqual(totals, {
  subtotal: 6340,
  discount: 100,
  transportation: 100,
  grandTotal: 6340,
});

assert.deepEqual(computeQuotationTotals([], 125.678), {
  subtotal: 0,
  discount: 0,
  transportation: 125.68,
  grandTotal: 125.68,
});

const queue = { current: Promise.resolve(null) };
const order = [];
const slow = () => new Promise((resolve) => setTimeout(() => { order.push("first"); resolve("first"); }, 10));
const fast = () => Promise.resolve().then(() => { order.push("second"); return "second"; });
await Promise.all([enqueueQuotationPersist(queue, slow), enqueueQuotationPersist(queue, fast)]);
assert.deepEqual(order, ["first", "second"]);

console.log("shared quotation totals/autosave contract: 3 assertions passed");
