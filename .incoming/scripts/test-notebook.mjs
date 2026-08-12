import assert from "node:assert/strict";
import {
  NOTEBOOK_COLUMNS,
  NOTEBOOK_FILTERS,
  QUOTATION_COLUMNS,
  applyCellPatch,
  columnsForView,
  formatIndianDate,
  formatRupees,
  nextCell,
  searchNotebookRows,
} from "../src/components/notebook/notebookModel.ts";

assert.deepEqual(NOTEBOOK_COLUMNS.map((column) => column.key), [
  "customer_name", "customer_phone", "address", "kitchen_type", "referred_by",
  "architect_interior_designer", "status", "notes",
]);
assert.deepEqual(QUOTATION_COLUMNS.map((column) => column.key), ["quotation_price", "estimated_value", "quotation_date"]);
assert.deepEqual(NOTEBOOK_FILTERS, ["all", "pending", "won", "lost", "new", "quotation"]);

const row = {
  id: "1", customer_name: "A", customer_phone: "9999999999", address: "Home", kitchen_type: "GI",
  referred_by: "R", architect_interior_designer: "I", status: "new", notes: "N", is_converted: false, updated_at: "v1",
};
assert.equal(searchNotebookRows([row], "home").length, 1);
assert.equal(searchNotebookRows([row], "100000").length, 0);
assert.equal(columnsForView("followups").length, 8);
assert.equal(columnsForView("quotation").length, 11);
assert.deepEqual(columnsForView("followups", "third-floor").map((column) => column.key).includes("kitchen_type"), false);
assert.equal(columnsForView("quotation", "third-floor").length, 10);
assert.deepEqual(nextCell({ row: 0, column: 7 }, "Tab", 2, 8), { row: 1, column: 0 });
assert.deepEqual(nextCell({ row: 1, column: 0 }, "Shift+Tab", 2, 8), { row: 0, column: 7 });
assert.equal(nextCell({ row: 0, column: 0 }, "Escape", 2, 8), null);
assert.equal(applyCellPatch(row, "notes", "changed").notes, "changed");
assert.equal(row.notes, "N");
assert.equal(formatRupees(125000), "₹1,25,000");
assert.equal(formatIndianDate("2026-08-06"), "06/08/2026");

console.log("notebook model: 11 assertions passed");
