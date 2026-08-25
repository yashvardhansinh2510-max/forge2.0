# Coverage matrix

Status meanings: **pass** is tool-evidenced only; **fail** is code-confirmed; **blocked** needs auth/data; **not verified** needs a browser/device/manual test.

| Route group / critical flow | 320–414 phone | 568 landscape | 768–820 tablet | 1024–1440 desktop | States | Status / highest finding |
| --- | --- | --- | --- | --- | --- | --- |
| Public: `/`, `/privacy`, `/terms` | not verified | not verified | not verified | not verified | public | not verified |
| Auth: login, forced password | blocked | blocked | blocked | blocked | validation/loading/error | blocked |
| Admin shell and phone More | fail (static) | not verified | fail (hybrid risk) | fail (hybrid risk) | navigation/sheet | UX-002, UX-006, UX-011 |
| Dashboard / follow-up queue | blocked | blocked | blocked | blocked | loading/error/action | UX-010 static; otherwise blocked |
| Catalog list/detail/import | fail (static) | not verified | fail (static) | fail (static) | loading, pagination, filters | UX-001, UX-009, UX-012 |
| Customers / walk-ins / follow-ups / team | blocked | blocked | blocked | blocked | list, detail, form, dialogs | UX-002, UX-004, UX-007 static |
| Quotations list/new/detail/place-order | fail (static) | not verified | not verified | not verified | builder, product modal, save/error | UX-005, UX-006 |
| Purchases / purchase orders / payments | fail (static) | not verified | not verified | fail (date focus static) | table, movement, payment | UX-008, UX-013 |
| Tile selection / quotation / orders / dispatch | fail (static) | not verified | fail (static) | fail (static) | filter, dispatch, document edit | UX-003, UX-011 |
| Sales data / reports / notifications / settings | blocked | blocked | blocked | blocked | filters, empty/error | UX-004, UX-007 static |
| Customer portal / quotes | blocked | blocked | blocked | blocked | list/detail | blocked |

### Route inventory

Reachable route modules were inventoried: 3 public, 2 auth, 3 customer, and 55+ admin modules. Admin includes dashboard; catalog; customers; walk-ins; quotations; purchase orders; purchases; payments; follow-ups; notebook; notifications; reports; sales data; settings; team; and Tiles selection, quotation, and orders. Authentication/data prevented meaningful route-by-route visual interaction checks; their static shared-shell/component exposure is recorded above.

### Required follow-up checks

At 320×800, 375×812, 390×844, 414×896, 568×320, 768×1024, 820×1180, 1024×768, 1280×800, and 1440×900, exercise a staff flow through Catalog, quotation builder, Tile Orders/dispatch, payment, and phone More. Repeat representative routes at 200% zoom, keyboard-only, and with screen reader. Record resulting pass/fail evidence rather than assuming a static result proves reflow or focus behavior.
