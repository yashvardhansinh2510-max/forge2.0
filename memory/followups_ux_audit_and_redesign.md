# BuildCon House — Follow-ups UX Audit, Automation Investigation & Redesign Proposal
Date: 2026-02 · Author: E1 (grounded in live screenshots of https://persist-arch.preview.emergentagent.com/followups + source review of followups.tsx, followup_engine.py, followup_routes.py)

---
## PART 1 — UX AUDIT (grounded in live screenshots)

### Layout
1. **Chrome-before-work problem.** Order on screen: Header → Today's Mission hero (~110px) → 6-tile KPI strip (~110px) → Search+3 filter rows (~350px, always expanded even when unused) → first follow-up card. On a 1000px-tall screen, ~570px of pure navigation/filter chrome renders before card #1. For a page whose entire job is "show me who to call," that's too much preamble.
2. **Context panel is empty by default and still reserves 400px of desktop width** ("Select a follow-up / Choose a card on the left..."). On first load this is dead space competing with the list for the fold.
3. **Cards are tall** (~180–220px: avatar+name+badges → reason+factors → tags → Next-Best-Action box → due/contacted row → assignee row → action row). Only ~3 cards visible without scrolling on a 1000px screen. A workspace meant to handle 300+ customers needs a denser default row with expand-on-demand detail.
4. **Filter row default state looks pressed.** "All priorities" / "All types" pills render with the same blue-outline active style used for a *real* active filter — false affordance (looks like something is already filtered).
5. **Insights panel ("Today's conversion") is permanently glued below the context panel**, consuming vertical space even before anything is selected.

### Interaction
1. **Action overload behind one dropdown.** Visible: Call, WhatsApp, Complete. Hidden inside "···Actions": Email, 4 snooze presets, custom snooze, N×"Assign to person", Add note, Dismiss — 9+ items in one menu. Assign & Snooze are described in the product brief as top-tier "Smart Actions" yet need 2 clicks + list-scanning today.
2. **Keyboard shortcuts (c/w/e/space/s/Esc/"/") are implemented but invisible** — no legend, no `?`-key help, no on-hover hint. Power users (the actual Superhuman comparison) will never discover them.
3. **No bulk/multi-select.** Every action is single-card. At 300+ open cards this doesn't scale — there is no "select 10 stale quotes → bulk WhatsApp / bulk snooze."
4. **No virtualization.** `sections.map()` renders every card directly inside a plain `ScrollView` — fine for the current seed data (~12 rows) but will visibly lag once a real book of 300+ customers is loaded.
5. **Search placeholder lists 7 searchable fields** in one input with zero autocomplete — cognitively heavy, no scoped search.

### Information Architecture — can the page answer these in 5 seconds?
| Question | Verdict | Why |
|---|---|---|
| Who do I call first? | ⚠️ Partial | Mission's Top-3 list shows rank, but the main list below doesn't repeat rank numbers — you lose the "#1" framing once you scroll past the hero. |
| Which customer matters most? | ⚠️ Partial | Scores exist (51/49/44 in live data) but visually near-identical ("MEDIUM" for all three) — no strong color separation until a card is actually "critical" (red). |
| Which quotation is about to expire? | ❌ No | No dedicated KPI tile for "Expiring Quotations" despite the engine computing `quotation_expiring` explicitly — buried inside card text only. |
| Which payment is overdue? | ❌ No | The "Overdue" KPI tile blends quotation_expired + payment_overdue + customer_inactive into one number (9), while the Mission subtitle separately says "2 overdue payments" — inconsistent granularity between two adjacent widgets. |
| Which follow-up is blocking the most revenue? | ❌ No | ₹ value is embedded inside a sentence ("₹2.9L at stake"), never a standalone prominent chip/column you can visually scan down. |
| What should I do next? | ✅ Yes | The blue Next-Best-Action box is the strongest element already on the page — explainable, always visible, well-designed. |

**Verdict: 3 of 6 core questions fail a 5-second scan.** Root cause is consistent: urgency/revenue signals are text-embedded prose rather than dedicated scannable visual elements.

### Visual Design
- Typography & spacing tokens are consistent and legible — no complaints on the base design system (`ds.tsx` tokens).
- **Blue is overloaded**: primary CTA, active filter, "Auto" badge, Next-Best-Action box, focus ring, AND the "medium" priority score badge all use the same brand blue. This dilutes what blue is supposed to mean (action/brand) — a "medium" urgency card visually competes with primary buttons for attention.
- Cards are flat-bordered with no elevation change between resting/hover/selected beyond a border+background tint swap — feels closer to CRUD than Linear/Superhuman, which lean on crisp shadow + motion for state changes.
- No motion/delight anywhere: completing a follow-up, resolving a section, or hitting zero-inbox has no animation — a missed "Superhuman zero-inbox" moment.
- Priority color logic (critical=red, high=orange, medium=blue, low=grey) is sound *except* medium=blue for the reason above — recommend medium=neutral/amber-light instead, reserving blue purely for brand/actions.

### Immediate, non-invasive fixes (no rewrite required)
| # | Element | Why it happens | Why it's bad | Fix |
|---|---|---|---|
| 1 | Context panel empty on load | Nothing pre-selected | Wastes 400px + breaks the "Start with #1" promise | Auto-select the top-priority open card on page load |
| 2 | Filter rows always expanded | No collapse state | Pushes list ~200px down | Collapse Type/Tier/Owner behind one "Filters" toggle chip next to search; keep Priority chips inline |
| 3 | Assign/Snooze buried in one dropdown | All secondary actions merged into one menu | Two of the most-used "Smart Actions" need 2 clicks | Promote dedicated Snooze (with mini-menu) and Assign icon buttons next to Call/WhatsApp/Complete |
| 4 | "Overdue" tile conflates categories | Single counter for 3 different rule types | Fails the "which payment is overdue" question | Split into "Payments Overdue (₹X)" + generic "Overdue Tasks", reuse existing `sub` prop |
| 5 | Default filter pills look "active" | Selected-style used for default "all" state | False affordance | Use a distinct neutral style for the "all" (unfiltered) chip |

---
## PART 2 — AUTOMATION INVESTIGATION (as actually implemented today)

**Q1 — What creates a follow-up?**
Four deterministic rule families inside `followup_engine.py`, all executed by a single function `reconcile_followups()`:
- Quotation-based: `quotation_new`, `quotation_inactive`, `quotation_expiring`, `quotation_expired`, `payment_overdue`, `payment_partial`
- Purchase-order-based: `purchase_dispatched`, `purchase_delivered`
- Customer-based: `customer_inactive`
- Manual: staff-created via "New Follow-up" sheet (category general/quotation/payment/sales/support)

**Q2 — Quotation → Order: does the reminder auto-resolve?**
YES. Quotation-stage rules only match `status in ("draft","sent","pending_approval")`. The moment a quotation becomes an order, those `upsert()` calls stop firing for that quotation → its key disappears from the `desired` dict on the next reconciliation pass → the engine's diff step (`existing_by_key.pop` leftover) marks it `done`, `auto_resolved=True`, with a system resolution note. **This already works correctly** — the only caveat is timing (see gap #4 below).

**Q3 — Payment received → do reminders auto-close?**
YES, same mechanism. `outstanding = grand_total − paid`. Once `outstanding ≤ 0`, neither `payment_overdue` nor `payment_partial` re-enters `desired`, so the open card auto-resolves on the next reconcile pass.

**Q4 — Purchase delivered → dispatch follow-up?**
YES. `purchase_dispatched` requires `dispatched items AND delivered < total items`. Once every item reports `stage="delivered"`, this condition becomes false → the dispatch card auto-resolves, AND a *new* `purchase_delivered` "check satisfaction / ask for referral" card is generated for `DELIVERED_RECENCY_DAYS=5` days. After that window it simply stops regenerating (no explicit "feedback" or "archive" stage exists yet).

**Q5 — Full desired lifecycle vs. what's built:**
```
Quotation Created ─▶ (quotation_new, 0-2 days) ─▶ Waiting ─▶ quotation_inactive (3+ days) ─▶ [customer responds via call/WA — logged but NOT yet auto-scheduling next touch] ─▶ quotation_expiring (T-3d) / quotation_expired ─▶ Order Created (rules stop matching → auto-closed) ─▶ payment_overdue / payment_partial ─▶ Payment Received (auto-closed) ─▶ purchase_dispatched ─▶ Purchase Delivered (auto-closed, new purchase_delivered card, 5-day window) ─▶ [no explicit feedback/archive stage yet]
```
Everything left of the brackets is **built and working**. Gaps to close:
1. **Freshness lag** — reconciliation only runs at server boot and when the frontend calls `POST /followups/reconcile` (on page load/pull-to-refresh). It is *not* triggered by the mutating event itself (quotation approved, payment recorded, item marked delivered). Recommended fix: call `reconcile_followups()` (or a scoped single-entity variant) right after those specific write operations in `quotation_routes.py` / `payment_routes.py` / `purchase_routes.py`. This is **event-triggered, not time-triggered** — it does not reintroduce a cron job, it just removes the "nobody opened the workspace" lag.
2. **No outcome→next-action auto-scheduling.** Logging a call outcome (`interested`, `no_answer`, `call_back`, etc.) writes to the timeline but doesn't yet auto-snooze/re-schedule the next touch (e.g. `no_answer` → retry tomorrow; `interested` → check back in 2 days). Small deterministic lookup table, no LLM needed.
3. **No distinct "archived" state** — completed-by-action, auto-resolved-by-system, and merely stale are all just `status="done"`. Fine today; will matter once reporting/analytics on the follow-up funnel is built.
4. **No post-delivery feedback/review stage** beyond the 5-day "delivered" card.

---
## PART 3 — REDESIGN PROPOSAL
**Honest framing:** the *engine* (Part 2) and the *information* (Part 3 building blocks — mission, score, next-best-action, context panel, timeline) are already sound and correctly wired end-to-end with zero mocking. What needs redesigning is the **presentation and interaction layer**: hierarchy, progressive disclosure, bulk workflows, and native mobile patterns — not the data model or the engine.

### Primary Dashboard (Today's Mission, evolved)
Keep the hero, but replace the static 6-tile KPI grid with a **ranked "Radar" strip**: Revenue at Risk (₹, tap→filtered list) · Top 3 Priorities (already exists, keep) · Payments Overdue (₹ specific) · Quotations Expiring (count, specific) · Today's Calls/WhatsApps done vs target · Conversion rate this week. Same components (`StatTile`), just re-scoped labels + split counters so every one of the 6 IA questions has its own tile.

### Inbox (list → scannable rows)
- Add a **4px left-edge color bar per priority level** on each card (Superhuman-style instant scan), remove reliance on badge color alone.
- Collapse the card's rich body into a **2-line default** (name, ₹ value in own bold chip, next-best-action, score) with a chevron to expand reason/factors/tags/timeline-preview — cuts default row height ~40%.
- Promote Assign + Snooze to first-class icon buttons (see Immediate Fix #3).
- Add multi-select checkboxes + a **contextual bulk action bar** (bulk WhatsApp, bulk snooze, bulk assign) that appears once ≥1 row is checked.
- Add a `?`-triggered keyboard shortcut legend (reuse existing `Sheet` component).

### AI Priority Score — specification (already implemented, documented here for the team)
`score = value_pts(0–25) + silence_pts(0–20) + urgency_pts(0–35, rule-specific) + tier_pts(0–10)`, capped at 100.
- **Value (0–25):** `min(25, round(grand_total / ₹1,00,000 × 4))` — bigger deals rank higher.
- **Silence (0–20):** `min(20, days_since_last_contact × 2)` — colder leads rank higher ("you've forgotten them").
- **Urgency (0–35):** rule-specific fixed/graduated points, e.g. quotation expiring today = 35, expires in 3 days = 20, payment overdue = `20 + min(15, days_overdue×2)`, fresh quotation = 18, delivered follow-up = 12. This is the primary differentiator between rule types.
- **Tier (0–10):** VIP=10, Trade=5, Retail=0 — protects relationship-critical accounts.
- **Level bands:** critical ≥80, high ≥60, medium ≥35, low <35.
- 100% deterministic, fully explainable (`reason_factors` array is generated from the same inputs) — **no LLM involved, matches the hard product constraint.**
- Recommended enhancement (still deterministic): add a small **historical conversion-rate weight per rule_type** computed from closed-won stats already in Mongo (e.g. `quotation_expiring` empirically converts at a known % higher than `customer_inactive` → adjust urgency_pts table with data-derived constants, recomputed periodically as a batch statistic, not an LLM inference).

### Customer Context Panel
Already has: company, phone/email/city, tier, lifetime revenue, outstanding, pending quotations/orders, quotations list, purchases list, full activity timeline. **Missing per the brief:** Preferred Salesperson, Preferred Brand, Conversion %, Average Order Value, explicit Risk Level chip. All derivable from existing `customers`/`quotations`/`payments` collections — additive fields to the `/followups/{id}` detail endpoint, no new integration needed.

### Smart Actions
All listed actions already exist (Call, WhatsApp, Email, Assign, Complete, Snooze, Dismiss, Note, View Quotation/Customer/Timeline via context panel) — the fix here is purely **exposure** (fewer clicks to reach the top 5), not new functionality.

### Mobile Experience
Already has: bottom `Sheet` for context, `Swipeable` complete/snooze gestures, FAB quick-contact for #1 priority. Gaps: no swipe-to-assign, no sticky quick-filter bar while scrolling, Mission hero not collapsible into a persistent thin "X due today" pill once scrolled past. Recommend: sticky mini-header showing live count once hero scrolls off-screen; add a 3rd swipe direction (long-press) mapped to Assign, not just the first assignee.

---
## PART 4 — PRODUCT ROADMAP (whole app)
| Phase | Focus | Priority | Depends on | Effort | UX gain | Business gain |
|---|---|---|---|---|---|---|
| 1 | Design System hardening (color roles, elevation, motion tokens) | P0 | none | M | Removes blue-overload, adds delight | Consistency → trust |
| 2 | Navigation & IA pass (this session's original ask) | P0 | Phase 1 | M | Fewer clicks, clear hierarchy | Faster task completion |
| 3 | Quotation Builder polish | P1 | Phase 1 | M | Faster quote creation | More quotes/day |
| 4 | Customers 360 (adds fields noted above) | P1 | Phase 1 | S | Richer context panel | Better upsell targeting |
| 5 | Catalogue | P2 | — | S | — | — |
| 6 | Purchases / Dispatch tracking UI | P1 | Phase 2 | M | Visibility into logistics | Fewer "where's my order" calls |
| 7 | Payments | P1 | Phase 2 | S | Faster reconciliation | Cash-flow visibility |
| 8 | **Follow-ups V2** (this report's fixes) | **P0** | Phases 1–2 | M | 5-sec-scan achieved, bulk ops | Fewer missed follow-ups |
| 9 | Reports/Analytics | P1 | Phases 6–8 | M | Manager visibility | Coaching data |
| 10 | Automation lifecycle gaps (outcome→next-action, event-triggered reconcile) | **P0** | Phase 8 | S | Zero manual cleanup | Fewer dropped leads |
| 11 | Customer Portal | P2 | Phase 4 | L | Self-serve | Reduced support load |
| 12 | Mobile-native pass (gestures, sticky bars) | P1 | Phase 8 | M | Thumb-friendly at scale | Field-sales adoption |

---
## PART 5 — CRITICAL REVIEW
- The **engine is genuinely good** — deterministic, idempotent, explainable, already satisfies the hardest constraint (no LLM, no cron). Do not rebuild it.
- The **presentation layer is the weak link** — too much chrome before work, key actions buried, urgency signals text-embedded instead of visual, no bulk workflow for scale.
- The empty Context Panel on load and the always-expanded filter rows are the single biggest "feels unfinished" cues in the current screenshots — fix these two first for the fastest perceived-quality jump.
- **Automation lifecycle is 80% complete** — the remaining 20% (event-triggered reconcile, outcome-based auto-scheduling) is small, deterministic, and high leverage.

### Final Design Score: **6.5 / 10**
Strong bones (data model, engine, component library), weak presentation hierarchy and no bulk/scale workflows yet.

### Top 20 highest-impact fixes, ranked by ROI (effort vs. impact)
1. Auto-select #1 priority card on load (kills empty context panel) — tiny effort, big perceived-quality win
2. Collapse filter rows behind a toggle — tiny effort
3. Split "Overdue" KPI into Payments-Overdue(₹) vs Task-Overdue — tiny effort, fixes IA gap
4. Promote Assign + Snooze to dedicated buttons — small effort, big workflow win
5. Add left-edge priority color bar on cards — tiny effort, big scan-speed win
6. Event-trigger `reconcile_followups()` after payment/quotation/purchase mutations — small effort, closes automation freshness gap
7. Outcome→next-action auto-scheduling table — small effort, closes manual-cleanup gap
8. Multi-select + bulk action bar — medium effort, unlocks "300+ customers" scale claim
9. Keyboard shortcut legend (`?` key) — tiny effort
10. Switch card list to `@shopify/flash-list` for virtualization — small effort, future-proofs scale
11. Re-map "medium" priority color off brand-blue — tiny effort, fixes color-overload
12. Collapse card body to 2-line default + expand chevron — medium effort
13. Add Preferred Salesperson / Conversion% / AOV / Risk Level to context panel — small effort (data already exists)
14. Sticky Mission summary pill on mobile scroll — small effort
15. Swipe-to-assign gesture on mobile — small effort
16. Add motion on complete/resolve (checkmark + collapse animation) — small effort, delight win
17. Scoped search with field-specific chips instead of one giant placeholder — medium effort
18. Rank numbers repeated in main list (not just Mission hero) — tiny effort
19. Elevation/shadow states for hover/select vs. flat border-only — small effort, visual polish
20. Export/Saved Views (still explicitly stubbed per product decision — lowest priority, unchanged)
