# Task 6 Report — Complete the Sanitary Chalan PDF

Date: 2026-08-05

Status: completed

## Implementation

- Expanded `build_chalan_pdf(chalan, po, customer, branding)` without changing the authenticated, floor-scoped PDF route, its customer lookup, or filename behavior.
- Added customer name/address/phone, PO number, reference, and dispatch date metadata with safe PO/customer/created-date fallbacks.
- Replaced the five-column tile-oriented table with wrapped Sanitary product rows for brand, product name, size, finish, quantity, unit, rate, and total.
- Enriched Chalan snapshots from the matching `po.items[]` entry by `po_item_id`, which keeps the existing embedded-Chalan persistence contract while making PO brand/finish/rate data printable.
- Added deterministic `Decimal` quantity/money formatting, calculated line totals, and a grand-total row. Unknown numeric values render as a placeholder rather than as a false zero.
- Added wrapped transport and remarks blocks, receiver/supplier signature areas, company contact details, and configured signatory metadata.
- Kept all optional fields crash-safe, including empty customer lookup results and absent rate, address, phone, transport, remarks, and signature names.

## TDD evidence

Initial focused run after adding the extraction contract tests:

```text
backend/.venv/bin/pytest backend/tests/unit/test_pdf_chalan.py -q
2 failed, 1 passed
```

The failures showed the old renderer lacked order/dispatch metadata, address, the complete product columns, totals, logistics blocks, and the updated signature labels.

Final focused and adjacent regression run:

```text
backend/.venv/bin/pytest backend/tests/unit/test_pdf_chalan.py backend/tests/unit/test_tile_orders_dispatch.py backend/tests/unit/test_pdf_tile_chalan.py -q
12 passed, 14 warnings in 0.56s
```

The warnings are existing Pydantic V2 deprecations from `backend/routes/tile_orders.py`; Task 6 did not modify that route.

Additional check:

```text
git diff --check -- backend/pdf_chalan.py backend/tests/unit/test_pdf_chalan.py
```

Passed with no whitespace errors.

## Tests added

- PDF magic bytes and text extraction with `pypdf`.
- Complete required field/headings presence after extraction.
- Long customer address and long product name preservation through wrapped `Paragraph` cells.
- Stable quantity, rate, line-total, and grand-total formatting.
- Missing optional address, phone, rate, transport, remarks, and signature-name generation with the existing PO customer-name/date/company fallbacks.
- Existing filename convention remains unchanged.

## Scoped files

- `backend/pdf_chalan.py`
- `backend/tests/unit/test_pdf_chalan.py`
- `.superpowers/sdd/2026-08-05-sanitary-bathroom-purchase-stabilization/task-6-report.md`

## Concerns

- The current persisted Sanitary `ChalanLineItem` stores only name, size, quantity, and unit. Brand, finish, and rate therefore come from the matching PO item at render time. This follows the existing renderer interface and avoids an out-of-scope model/route migration, but historical PO edits can affect those enriched PDF values.
- The current Sanitary lifecycle has no dedicated persisted transport field. The renderer supports existing/ad-hoc transport fields and vehicle/driver metadata and otherwise shows a safe placeholder; `dispatch_note` is used for remarks. Persisting richer transport metadata would require a separately scoped model/route change.
- `backend/pdf_chalan.py` already contained an unrelated unstaged Tile Chalan `Boxes` to `Unit` change before Task 6. That pre-existing hunk was preserved in the worktree and excluded from this commit.
