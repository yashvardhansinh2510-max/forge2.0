# Milestone 1 — Ground Floor Tiles Verification

Date: 2026-08-06
Status: **Signed off**

## Evidence completed

| Check | Result | Evidence |
|---|---|---|
| TypeScript | PASS | `frontend/node_modules/.bin/tsc --noEmit --pretty false` |
| Python compilation | PASS | `backend/.venv/bin/python -m compileall` |
| Frontend quotation contract | PASS | 3 assertions |
| Frontend quotation media helpers | PASS | 7 assertions |
| Notebook model regression | PASS | 11 assertions |
| Backend tile pricing | PASS | Offer fallback, explicit Rate/Box, box totals, piece conversion |
| Selection → Quotation handoff | PASS | Fresh `FQ-2026-0130`: Selection save/edit/approve → Quotation promotion → Mongo reload preserved ₹400 subtotal, ₹130 transport, ₹530 grand total, Rate/Box ₹200, offer rate ₹95, and 4 pcs/box; PDF generated successfully |
| Current backend persistence | PASS | QA quotations `FQ-2026-0125`/`FQ-2026-0126`: subtotal ₹400 + transport ₹125 = grand total ₹525 |
| Piece pricing persistence | PASS | 8 pieces × ₹50 = ₹400; Rate/Box ₹200 and 4 pcs/box persisted |
| Tiles PDF | PASS | 2-page PDF; extracted `₹525.00`, `₹200.00`, and `₹95.00` |
| Supabase media | PASS | Public product image returned HTTP 200, `image/jpeg`, 31,482 bytes |
| Sanitary quotation regression | PASS | Existing standard quotation PDF generated; 2 pages and total ₹72,250 present |
| Browser desktop | PASS | Live screenshot: total remained inside bordered cell; quotation paper readable |
| Browser tablet | PASS with horizontal paper scroll | Live screenshot confirmed right-side columns and total cell intact after horizontal scroll |
| Browser mobile | PASS after label fix | Live screenshot confirmed card editor; `Pcs / Box` is now correctly labeled |
| Browser console errors | PASS | Fresh live reload: no error-level browser logs |
| Place Order preview reconciliation | PASS | `FQ-2026-0126` preview returned material subtotal ₹400 and total value ₹525 including transport; confirm returned payment amount ₹525 |
| Full tiles lifecycle | PASS | `FQ-2026-0126`: Place Order → PO `FPO-2026-0357` → Ready → Move to Godown → Dispatch `DSP-2026-0029`/Chalan → Godown Received → Delivered; PO and customer order both reached Delivered with 8/8 pieces |
| Payment reconciliation | PASS | `FQ-2026-0126`: grand ₹525, completed paid ₹525, outstanding ₹0, status Paid |
| Sales Data | PASS | Ground Floor overview for the won QA order returned revenue ₹525 and quotation count 1 |
| Customer order history/timeline | PASS | `TORD-2026-0019` returned Delivered, 100% completion, and dispatch/godown/delivery events on `ground-floor` |
| Payment floor inheritance | PASS after fix | Fresh `FQ-2026-0127` payment persisted `floor_id=ground-floor` while the operator remained on the First Floor ambient context |
| Mongo reload persistence | PASS | Live UI reopened `FQ-2026-0126` from Mongo with customer, rates, offer rate, piece quantity, subtotal, transport, and ₹525 total intact |
| Supabase public media | PASS | Existing product image returned HTTP 200, `image/jpeg`, 31,482 bytes; current server preflight bucket check returned HTTP 200 |
| Supabase signed media | PASS | Driver-generated signed URL returned HTTP 200, `image/jpeg`, 31,482 bytes |
| Image-bearing Tiles PDF | PASS | Existing `FQ-2026-0121` PDF was 2 pages/A4, contained embedded image objects, and extracted its expected total |
| Backend unit suite | PASS | `tests/unit`: 908 passed |
| Backend integration suite | PASS | `tests/integration`: 44 passed, 125 intentionally skipped |
| Current API performance audit | PASS | Ten authenticated requests per endpoint, all HTTP 200: dashboard stats p95 0.455s; quotations recent p95 0.161s; payments stats p95 0.308s; Tiles Sales Data p95 0.139s |

## Scope note

Broader multi-user/load testing beyond this bounded authenticated endpoint audit is deferred outside the single-operator Milestone 1 verification scope.

## Blocking runtime evidence

The backend preflight recovered during this verification window. Supabase bucket checks returned HTTP 200 and MongoDB-backed lifecycle writes completed successfully. The initial outage and the first godown delivery run exposed two defects; both are now fixed in source: preview transport omission and godown-origin delivery status calculation. A shared payment-floor defect was also fixed and verified with fresh `FQ-2026-0127` data.

Ground Floor notifications were also verified through `X-Floor-Id: ground-floor`: order-confirmed notifications for `FQ-2026-0126`, payment-received notification for ₹525, and the corresponding Ground Floor lifecycle records were present. The full unit/integration suites and bounded authenticated performance audit are green. Broader multi-user load testing is not part of this single-operator Milestone 1 verification pass.

No merge or push was performed. Milestone 1 Ground Floor Tiles is signed off based on the evidence above; do not proceed to Milestone 2 in this task.
