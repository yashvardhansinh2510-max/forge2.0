# BuildCon House — Product Design Reboot
## Part 1: The Audit (brutal, screen-by-screen) + Part 2: The Redesign Blueprint

Date: 6 July 2026 · Author: design reboot session
Live screenshots referenced: /tmp/audit_*.png

---

# PART 1 — AUDIT

## The one-sentence diagnosis

The current app is a competent database UI: every screen is "title + KPI tiles + search + filter chips
+ card list", which proves the backend works but answers no user question. It is organized around
**tables** (quotations, payments, purchases…), not around the **workday** of someone who lives in it
8–12 hours. It is exactly the "AI-generated admin dashboard" the brief forbids.

## Global / cross-cutting failures

1. **The KPI-tile disease.** Every screen opens with 4–7 stat tiles. Followups has a mission banner
   AND 7 tiles repeating the same numbers. Payments shows "₹11.15L outstanding" twice within 150px
   (hero + tile). Customers shows tier counts as tiles AND as filter-chip badges directly below.
   These tiles answer nothing; they are decoration wearing a data costume. → DELETE the pattern.
2. **Information architecture mirrors the database, not the job.** Purchases, Purchase-orders and
   Payments are three separate nav destinations for what is ONE real-world thing: a confirmed order
   moving through supplier → delivery → collection. The user must mentally join three screens.
3. **11 navigation items, flat.** Notifications, Team, Settings carry the same visual weight as
   Quotations. Two purchase modules coexist ("Purchases" material tracker + "purchase-orders" Kanban).
   Reports is an empty scaffold advertised as a first-class destination.
4. **No answer to "what should I do right now?"** Dashboard = 4 KPI cards + 2 lists. It's a
   read-only report, not a starting point. The genuinely excellent follow-ups priority engine
   (priority scoring, revenue-at-risk, reconciliation) is buried on page 7 of the nav.
5. **Accent abuse.** Brand blue #2563EB is used for: primary buttons, active nav, icon tiles,
   badges, links, rank chips, filter chips. When everything is blue, nothing is. Color has no meaning.
6. **Boxes inside boxes.** Card → panel → tile → chip nesting everywhere. Borders + shadows +
   background shifts all at once. Hairlines and typography could carry the same structure silently.
7. **Typography has no rhythm.** Page titles vary (greeting vs overline+title vs bare title).
   Money — the single most important data type in this business — is styled inconsistently
   (sometimes red, sometimes bold, sometimes caption-sized, non-tabular in lists).
8. **No global command surface.** ⌘K exists only inside the quotation builder. Creating a quotation
   from Customers, or finding a customer from Payments, requires nav round-trips.
9. **Motion is absent or decorative.** No state-communicating transitions; hover states inconsistent.
10. **Mobile is desktop-stacked.** The phone dashboard is the same KPI grid squeezed to 2×2. Bottom
    tabs ("Home, Quotes, +, Alerts, More") don't map to the real mobile jobs (chase follow-ups,
    check an order, record a payment on the go).

## Screen-by-screen

### Authentication
- Portal segmented control (Team/Customer) given prime position for a once-ever decision.
- A "DEMO CREDENTIALS" panel with 8 role chips permanently occupies a third of the form column. Noise.
- Hero quote name-drops "Linear, Stripe, and Apple" — telling, not being.
- Verdict: keep the split-panel bones, strip everything that isn't email→password→enter.

### Dashboard
- Four KPI cards with decorative icon tiles; two panel lists (activity, top products).
- Zero prioritization, zero actions. "Pending approval: 1" is a number when it should be a task.
- Verdict: DELETE the screen concept. Replace with "Today" (see blueprint).

### Quotations list
- Fine bones (search, status chips, rows) but: chips duplicate counts, per-row status pills are
  loud colored badges, icon+number+avatar+badge per row = 4 competing identities.
- Verdict: quiet pipeline lens + typographic rows.

### Quotation Builder (V4)
- Genuinely good workflow (3-pane, undo/redo, autosave, variants, alternates). The strongest screen.
- Problems: three stacked headers (app topbar + brand rail header + pane headers) burn ~140px;
  the dark left rail is a different design language than the rest of the app; red prices everywhere
  read as errors; keyboard hints crammed into the topbar.
- Verdict: keep the workflow, reskin the chrome to the new language, merge headers.

### Catalogue
- "Families / Variants" toggle is supplier jargon exposed to a salesperson.
- Category chips row + brand text line + view toggles before any products.
- The real job — "find this product NOW while the customer is standing here" — starts with a
  medium-sized search input under two rows of chrome.
- Verdict: search-first finder. Brand shelf. Kill jargon toggles (auto-group, expand on demand).

### Customers
- Tier tiles duplicating filter chips; loud TRADE/VIP/RETAIL badges; rows fine otherwise.
- Detail page is a tab pile without a narrative: no "who is this, what do they owe, what's live".
- Verdict: relationship file — identity + balance + live work at top, one timeline under it.

### Purchases (material tracker) + Purchase Orders
- Two modules, two mental models (view filters vs Kanban), zero shared state language.
- Kanban with 8 columns on a 1280px screen = horizontal scrolling misery; most columns empty.
- Verdict: MERGE into "Orders" — one list, lens tabs by stage, one order = one timeline detail.

### Payments
- The half of "Orders" that got separated. Hero + 4 tiles repeat one number. Two-pane layout is
  right; the money math presentation (MRP/discounted/paid/outstanding as 4 boxed tiles) is noisy.
- Verdict: fold into Orders as the "To collect" lens + per-order ledger.

### Follow-ups
- The best product thinking in the app (priority engine, mission, context panel) wearing the worst
  UI: mission banner + 7 KPI tiles + search + saved views + priority chips + "more filters" + bulk
  bar + rank chips + score chips + priority color bars + checkbox per card — all before the first
  card's content. Cognitive DDoS.
- Verdict: this engine BECOMES "Today". One ranked queue, one card in focus, actions on the row.

### Reports / Team / Settings / Notifications
- Reports: scaffold. Team: bare list. Notifications: a page that shouldn't exist (merge into Today).
- Verdict: Reports gets a real, minimal answer to 3 owner questions; Team/Settings become quiet
  utility pages; Notifications page deleted from IA.

---

# PART 2 — REDESIGN BLUEPRINT

## Design philosophy → concrete rules

- **Calm**: one accent color, used only where the user should act. Neutrals carry everything else.
- **Focus**: every screen states its one primary action; everything else recedes until hover/press.
- **Speed**: ⌘K everywhere, one-tap row actions, inline editing, no confirmation theater.
- **Confidence**: money in large, light, tabular numerals; statuses as words with a small tinted
  dot, never shouting pills; sentences instead of tile grids ("₹11.4L outstanding across 4 orders —
  2 need a reminder today").

Hard rules (enforced in the component system):
- Max ONE filled button per screen.
- No stat may appear twice on a screen.
- No borders where a hairline or whitespace suffices; no shadow + border together.
- No icon-in-tinted-square decoration.
- Numbers: tabular figures, always. Money: ₹ symbol smaller and lighter than digits.
- Motion only on state change: 150–220ms, ease-out, fade+4px slide. Nothing loops, nothing bounces.

## New information architecture (11 items → 6 + utility)

1. **Today** — the workday home. Fuses Dashboard + Follow-ups + Notifications.
   Greeting date-line → one state sentence → ranked "Up next" queue (existing priority engine)
   with inline Call/WhatsApp/Done/Snooze → quiet right column: the business pulse (3 typographic
   stats) + team activity whisper feed.
2. **Quotations** — pipeline lens (Draft/Sent/Approval/Won/Lost) + typographic rows + the Builder.
3. **Orders** — MERGES Purchase-orders + Purchases tracker + Payments. Lenses: To order → With
   supplier → To deliver → To collect → Done. Detail = one vertical timeline (confirm → PO → receive
   → deliver) + payment ledger + stage-appropriate single primary action.
4. **Customers** — list + relationship file (identity, balance, live work, one timeline).
5. **Catalogue** — search-first finder + brand shelf + product page with variant/finish selection.
6. **Reports** — three owner questions, answered plainly (Money / Pipeline / Team).
Utility (sidebar footer / phone "More"): Team, Settings. Command palette (⌘K / search button) global.

## Visual language — "Showroom"

Inspired by why Apple/Linear/Stripe feel premium (restraint, typographic confidence, material
subtlety), tuned to this industry (porcelain, chrome, brushed brass):

- Canvas `#FAF9F7` (warm gallery white) · Surface `#FFFFFF` · Ink `#191A1C` ·
  Secondary `#6E7178` · Hairline `#ECEAE6`.
- Primary action: ink-black filled button (Apple/Notion confidence). Accent (focus, selection,
  active states, links): a single controlled hue — proposal A: brushed brass `#9A7B4F`;
  proposal B: deep cobalt kept from current identity but used 10× less.
- Status hues: money-positive green, attention amber, risk red — only as dot+word, never pill walls.
- Type: Inter (UI) + Inter Tight (display numerals/titles), tabular-nums for all figures.
  Optional single serif moment (Fraunces) for the wordmark/greeting only.
- Depth: 2 shadow levels total (raised, overlay). Everything else is hairlines + background shift.

## Execution phases

- **Phase 1 (first slice)**: tokens v3 + fonts + new navigation shell (desktop & phone) +
  global command palette + **Today** + Auth redesign. Notifications route folds into Today.
- **Phase 2**: Quotations list + Builder reskin (workflow preserved).
- **Phase 3**: Orders fusion (purchase-orders + purchases + payments → one module).
- **Phase 4**: Customers + Customer file + Catalogue finder.
- **Phase 5**: Reports + Team/Settings + ruthless coherence pass + full test sweep.

Backend: untouched (it's proven). The redesign composes existing endpoints; small additive
endpoints only if a screen genuinely needs one (e.g., Today briefing could reuse /followups/mission).

## Per-module deliverables

Each phase will ship with: problems addressed, IA, user journey, screen hierarchy, interaction
model, motion spec, components used, mobile adaptation, edge cases — appended to this document.

---

# PHASE 1 — SHIPPED (6 July 2026)

## What exists now
- src/design/tokens.ts — Showroom tokens (canvas #F7F5F1, ink #1D1B16 action, brass #8C7351 guidance-only,
  Fraunces display serif, 4pt spacing, 2 shadows, motion 90/140/200/260)
- src/design/components.tsx — Txt, Money, Button, IconButton, Field/Input, Row, StatusWord, Avatar,
  Surface, Section, EmptyState, Skeleton, KeyCap, Tabs, Sheet, Dialog, Menu, FadeIn, Hairline
- src/design/Screen.tsx — page scaffold (gutters 20/28/40, maxWidth 1120)
- src/design/CommandPalette.tsx — global ⌘K (actions + nav + customers/quotations/products search)
- src/design/responsive.ts — useBp(): phone <768 / tablet 768–1023 / desktop ≥1024
- New shell (_layout), Today (dashboard), Auth (login), Toast — all on the new system
- Legacy src/theme/tokens.ts VALUES remapped to warm palette → unmigrated screens blend automatically

## Rules for later phases (LOCKED)
1. Modules consume ONLY @/src/design/* — zero local styling.
2. One filled (ink) button per screen. Brass never on buttons.
3. No stat appears twice on a screen. No KPI tile grids — typographic stats.
4. Statuses = StatusWord (dot+word). Money = <Money/> (small ₹, tabular digits).
5. Fraunces appears ONLY in greetings/auth display moments.
6. Motion only on state change; use FadeIn once per screen, Sheet/Menu/Dialog for overlays.

## Migration order (user-approved)
1. Quotation Builder (flagship) → 2. Customers+CRM → 3. Catalogue → 4. Purchases → 5. Payments
→ 6. Follow-ups → 7. Reports → 8. Settings

## Catalog restoration (parallel workstream — BLOCKED on user)
Needs: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY, then the 4 supplier files (VITRA xlsx, GROHE pdf,
GEBERIT pdf, HANSGROHE). Then: re-run pipeline, verify counts (Vitra 250 / Grohe 854-864 / Geberit 496 /
Hansgrohe 1272), implement Supabase catalog snapshot auto-backup/restore on startup.
