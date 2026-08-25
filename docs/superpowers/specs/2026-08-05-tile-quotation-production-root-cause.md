# Tile Quotation Production Stabilization — Root-Cause Record

This record is written before the stabilization changes, as required by the
milestone objective. It describes the causes found in the existing code, not
just the visible symptoms.

## Findings

### Rate / Sq.Ft shows a box multiplier

`TilesDocBuilder.tsx` renders `rateSqft` together with a nested `/box` label
and an editable `boxSqft` field. The same presentation is duplicated in
`pdf_tiles.py`, where `box_sqft` is appended to the rate text. The UI is
therefore exposing an intermediate conversion rather than the requested
actual Rate / Sq.Ft value. The frontend also derives `rateBox` from
`rateSqft * boxSqft` in `updateRow` and `applyProduct`, which makes the
presentation layer a second pricing implementation.

### Offer Rate can be blank

Older tile quotation rows may have `offer_rate = null`. The server has a
normalization helper on create/update and the frontend has a restore fallback,
but PDF and read paths still rely on per-call fallback behavior. This split
allows blank display in a surface that does not pass through the same path.
Offer Rate must be normalized at the pricing boundary and rendered from the
normalized value everywhere.

### Pieces / Box is inconsistent

`quantity_unit` is persisted on quotation lines, but older renderers and tile
workflow surfaces default or format quantity independently. That is why a
single persisted choice can appear as `1`, `1 box`, or `1 pieces` depending on
the screen. The source of truth must remain the quotation line field, with one
display formatter used by quotation, tile order, dispatch, history, and PDF.

### Editing focus jumps to another cell

The paper is a nested horizontal `ScrollView` containing flex-based table rows,
controlled `TextInput`s, an absolutely positioned row-control rail, and an
overlapping product swap button. The inputs do not have stable field identity
or an explicit focus contract; the parent can therefore win responder/hit-test
resolution when the row rerenders during a controlled edit. The current
`onStartShouldSetResponder` patch only claims the initial responder and does
not make focus stable or keyboard navigation deterministic. Instrumentation
and a field-keyed focus path are needed rather than another hit-slop tweak.

### Save buttons remain despite autosave

`useTilesDoc` already schedules silent persistence after dirty state changes,
but `save()` remains exposed in both desktop and mobile action menus. The
buttons create a second, revision-producing persistence path and contradict
the autosave contract. Submit/Place Order/PDF actions should flush autosave as
needed, while ordinary editing must not expose Save.

### Layout and responsive behavior are split inconsistently

The desktop paper uses fixed-width flex columns inside a horizontal scroll,
while the phone editor has a separate card layout. Several table cells use
fixed typography and nested controls without shrink/wrap constraints, so long
values escape their cell even when the outer paper scrolls. The phone editor
does not share the paper's field labels and quantity semantics consistently.
The fix must keep the print-faithful desktop surface while making cell content
wrap naturally and using the mobile surface for 375/390/430 widths.

### PDF parity and calculation ownership

The backend already owns quotation totals through `services/pricing.py` and
`quotation_routes.py`, but the tile paper, mobile summary, and PDF independently
recompute line totals and subtotal from editable strings. This is a drift risk:
screen, stored quotation, and PDF can disagree after rounding or a backend
normalization. The frontend should submit raw editable inputs and render the
server response; the PDF should consume persisted normalized totals and fields.

## Verification plan

The implementation will add focused backend tests for normalization, quantity
unit persistence, and server-owned totals; typecheck the frontend; run the
backend unit suite; generate tile PDFs; and inspect the editor at 375, 390,
430, 768, 1024, 1280, and 1440 widths. The existing shared quotation models,
pricing engine, PDF generator, tile-order workflow, and activity system remain
the only business-logic owners.
