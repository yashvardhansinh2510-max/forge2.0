# Executive Operating System — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the correctness foundation and shared analytics layer that every Executive Operating System workspace depends on — without shipping a single workspace.

**Architecture:** Two pre-existing defects make every revenue number wrong (revenue dated by a mutable `updated_at`; line revenue ignoring the discount cascade). Fix those at the source, backfill via migrations, then add `backend/services/analytics/` — one canonical filter builder, one comparison engine, one version-keyed cache, one metric registry — plus the frontend chart foundation and the grouped workspace shell.

**Tech Stack:** FastAPI · MongoDB (motor) · Pydantic · pytest · Expo / React Native Web · expo-router · react-native-svg

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-01-executive-operating-system-design.md` is frozen. Do not add a KPI, aggregation, or route that is not in it.
- **Revenue dates by `ordered_at`.** After Task 4, `updated_at` is never used for business reporting.
- **One pricing engine.** All discount resolution goes through `services/pricing.py`. Never recompute a discount anywhere else.
- **No fabricated values.** Missing comparison data returns a `history_state`, never `+100%` or `0%`.
- **Migrations are forward-only and idempotent**, filename `NNNN_snake_case.py`, must define `async def up(db)`, and every `create_index` call tolerates `OperationFailure.code == 85` (see `migrations/0010_add_customers_email_unique_index.py` for the exact pattern).
- **Backend tests:** `cd backend && ./.venv/bin/python -m pytest tests/unit -v`. Suite was 197 passing before this plan; it must never go down.
- **Frontend has no test framework** (no jest, no testing-library — confirmed). Frontend verification is `npx tsc --noEmit` plus a live browser check.
- **The shared backend on `:8010` does not auto-reload** and may be in use by another session. Ask before restarting it.
- Python is `backend/.venv/bin/python` (3.14). Never use a system python.

---

## File Structure

**Backend — created**

| File | Responsibility |
|---|---|
| `backend/migrations/0011_backfill_quotation_net_amounts.py` | Backfill `items.net_amount` |
| `backend/migrations/0012_backfill_quotation_ordered_at.py` | Backfill `ordered_at` |
| `backend/migrations/0013_add_analytics_indexes.py` | Every index in spec §3.3 |
| `backend/services/analytics/__init__.py` | Package marker |
| `backend/services/analytics/filters.py` | `AnalyticsFilter` + the only match builder |
| `backend/services/analytics/periods.py` | Period resolution, previous window, `history_state` |
| `backend/services/analytics/cache.py` | Version-keyed Redis-or-memory cache |
| `backend/services/analytics/metrics.py` | Canonical KPI registry |
| `backend/routes/analytics_settings_routes.py` | Owner targets read/write |

**Backend — modified**

| File | Change |
|---|---|
| `backend/services/pricing.py` | Extract one shared cascade core; add `net_amounts`, `stamp_net_amounts` |
| `backend/models.py` | `QuotationLineItem.net_amount`, `Quotation.ordered_at`, `AnalyticsTargets` |
| `backend/routes/quotation_routes.py` | Stamp `net_amount` on both write paths; stamp `ordered_at` on both status paths |
| `backend/server.py` | Register the settings router |

**Frontend — created**

| File | Responsibility |
|---|---|
| `frontend/src/components/charts/ChartFrame.tsx` | Sizing, states, tokens — shared by every chart |
| `frontend/src/components/charts/Sparkline.tsx` | First chart, proves the frame |
| `frontend/src/components/analytics/WorkspaceSwitcher.tsx` | Grouped navigation (spec §16.2) |
| `frontend/app/(admin)/sales-data/_layout.tsx` | Shell wrapping every workspace |

---

## Task 1: One pricing engine

The discount cascade's room-amount allocation loop is currently **implemented twice** — in `recalc_quotation_totals` and again in `per_line_net_amounts`. That duplication is the root cause of brand revenue not reconciling to `grand_total`. Unify it, then expose per-line nets.

**Files:**
- Modify: `backend/services/pricing.py`
- Modify: `backend/models.py` (`QuotationLineItem`)
- Test: `backend/tests/unit/test_pricing_net_amounts.py`

**Interfaces:**
- Consumes: existing `effective_discount_pct`, `QuotationLineItem`, `RoomDiscountCfg`
- Produces:
  - `_resolve_line_rows(items, project_discount_pct, category_discounts, room_discounts) -> list[dict]` — rows of `{line_id, gross, disc, source, room}`
  - `net_amounts(items, project_discount_pct=0.0, category_discounts=None, room_discounts=None) -> dict[str, float]`
  - `stamp_net_amounts(item_dicts, project_discount_pct=0.0, category_discounts=None, room_discounts=None) -> list[dict]`
  - `QuotationLineItem.net_amount: Optional[float]`
  - `recalc_quotation_totals` and `per_line_net_amounts` keep their exact current signatures and return values

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_pricing_net_amounts.py`:

```python
"""Per-line net_amount must reconcile to grand_total under every discount
source, including the room "amount" (flat rupee) allocation that was
previously implemented twice and could drift."""
from __future__ import annotations

from models import QuotationLineItem, RoomDiscountCfg
from services.pricing import net_amounts, recalc_quotation_totals, stamp_net_amounts


def _line(line_id: str, qty: float, price: float, **kw) -> QuotationLineItem:
    return QuotationLineItem(id=line_id, product_id=f"p-{line_id}", sku=f"S-{line_id}", name=line_id, qty=qty, unit_price=price, **kw)


def _reconciles(items, **cfg) -> None:
    nets = net_amounts(items, **cfg)
    totals = recalc_quotation_totals(items, **cfg)
    assert abs(sum(nets.values()) - totals["grand_total"]) <= 0.01 * len(items)


def test_no_discount_net_equals_gross():
    items = [_line("a", 2, 100.0)]
    assert net_amounts(items) == {"a": 200.0}
    _reconciles(items)


def test_product_level_discount():
    items = [_line("a", 2, 100.0, discount_pct=10)]
    assert net_amounts(items) == {"a": 180.0}
    _reconciles(items, project_discount_pct=50)  # product override wins


def test_project_discount_applies_when_no_override():
    items = [_line("a", 1, 100.0), _line("b", 1, 300.0)]
    assert net_amounts(items, project_discount_pct=10) == {"a": 90.0, "b": 270.0}
    _reconciles(items, project_discount_pct=10)


def test_category_discount_beats_project():
    items = [_line("a", 1, 100.0, category_id="c1")]
    cfg = {"project_discount_pct": 50, "category_discounts": {"c1": 10}}
    assert net_amounts(items, **cfg) == {"a": 90.0}
    _reconciles(items, **cfg)


def test_room_percent_discount_beats_category():
    items = [_line("a", 1, 100.0, room="Kitchen", category_id="c1")]
    cfg = {
        "category_discounts": {"c1": 50},
        "room_discounts": {"Kitchen": RoomDiscountCfg(type="percent", value=10)},
    }
    assert net_amounts(items, **cfg) == {"a": 90.0}
    _reconciles(items, **cfg)


def test_room_flat_amount_allocates_pro_rata_and_reconciles():
    # ₹300 flat off a room whose lines gross ₹100 and ₹300 → 25%/75% split.
    items = [_line("a", 1, 100.0, room="Bath"), _line("b", 1, 300.0, room="Bath")]
    cfg = {"room_discounts": {"Bath": RoomDiscountCfg(type="amount", value=300)}}
    assert net_amounts(items, **cfg) == {"a": 25.0, "b": 75.0}
    _reconciles(items, **cfg)


def test_room_flat_amount_never_exceeds_room_gross():
    items = [_line("a", 1, 100.0, room="Bath")]
    cfg = {"room_discounts": {"Bath": RoomDiscountCfg(type="amount", value=5000)}}
    assert net_amounts(items, **cfg) == {"a": 0.0}


def test_mixed_sources_all_reconcile():
    items = [
        _line("a", 2, 100.0, discount_pct=10),
        _line("b", 1, 300.0, room="Bath"),
        _line("c", 3, 50.0, room="Bath"),
        _line("d", 1, 900.0, category_id="c1"),
        _line("e", 4, 25.0),
    ]
    cfg = {
        "project_discount_pct": 5,
        "category_discounts": {"c1": 12},
        "room_discounts": {"Bath": RoomDiscountCfg(type="amount", value=200)},
    }
    _reconciles(items, **cfg)


def test_stamp_net_amounts_writes_onto_item_dicts():
    raw = [
        {"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0},
        {"id": "b", "product_id": "p2", "sku": "S2", "name": "B", "qty": 1, "unit_price": 300.0},
    ]
    out = stamp_net_amounts(raw, project_discount_pct=10)
    assert [r["net_amount"] for r in out] == [90.0, 270.0]
    assert out is raw  # mutates in place, returns the same list


def test_stamp_net_amounts_overwrites_a_stale_value():
    raw = [{"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0, "net_amount": 999.0}]
    assert stamp_net_amounts(raw)[0]["net_amount"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_pricing_net_amounts.py -v`
Expected: FAIL — `ImportError: cannot import name 'net_amounts' from 'services.pricing'`

- [ ] **Step 3: Add `net_amount` to the line item model**

In `backend/models.py`, in `class QuotationLineItem`, directly after the `mrp` field:

```python
    # Post-discount total for this line, resolved through services/pricing.py's
    # cascade and denormalized at write time. Analytics sums THIS field, so
    # product/brand/category revenue reconciles to grand_total by construction
    # instead of re-deriving discounts per report and drifting.
    net_amount: Optional[float] = Field(default=None, ge=0)
```

- [ ] **Step 4: Unify the cascade in `services/pricing.py`**

Replace the bodies of `recalc_quotation_totals` and `per_line_net_amounts` with calls to one shared core. The full replacement for everything from `def recalc_quotation_totals(` to end of file:

```python
def _resolve_line_rows(
    items: list[QuotationLineItem],
    project_discount_pct: float,
    category_discounts: dict[str, float],
    room_discounts: dict[str, RoomDiscountCfg],
) -> list[dict]:
    """The one implementation of the discount cascade and the room "amount"
    pro-rata allocation.

    This loop used to exist twice — once in recalc_quotation_totals and once
    in per_line_net_amounts — which is exactly how per-line revenue drifted
    from grand_total. Both now build on this.
    """
    rows = []
    for it in items:
        gross = it.qty * it.unit_price
        pct, source = effective_discount_pct(it, room_discounts, category_discounts, project_discount_pct)
        rows.append({"line_id": it.id, "gross": gross, "source": source, "room": it.room, "disc": gross * pct / 100})

    by_room: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["source"] == "room_amount":
            by_room[row["room"] or ""].append(row)
    for room, room_rows in by_room.items():
        cfg = room_discounts.get(room)
        if not cfg or cfg.type != "amount" or cfg.value <= 0:
            continue
        room_gross = sum(r["gross"] for r in room_rows)
        flat = min(cfg.value, room_gross)
        if room_gross <= 0 or flat <= 0:
            continue
        for row in room_rows:
            row["disc"] = flat * (row["gross"] / room_gross)
    return rows


def recalc_quotation_totals(
    items: list[QuotationLineItem],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
    room_discounts: dict[str, RoomDiscountCfg] | None = None,
) -> dict:
    rows = _resolve_line_rows(items, project_discount_pct, category_discounts or {}, room_discounts or {})
    subtotal = sum(row["gross"] for row in rows)
    discount_total = sum(row["disc"] for row in rows)
    return {
        "subtotal": round(subtotal, 2),
        "discount_total": round(discount_total, 2),
        "grand_total": round(subtotal - discount_total, 2),
    }


def net_amounts(
    items: list[QuotationLineItem],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
    room_discounts: dict[str, RoomDiscountCfg] | None = None,
) -> dict[str, float]:
    """Return {line_id: post-discount line total}.

    Sums to grand_total to within per-line rounding (each line is rounded to
    paise independently, so a quotation with N lines can differ from
    grand_total by at most N x ₹0.01 — assert with that tolerance, not equality.
    """
    rows = _resolve_line_rows(items, project_discount_pct, category_discounts or {}, room_discounts or {})
    return {row["line_id"]: round(row["gross"] - row["disc"], 2) for row in rows}


def per_line_net_amounts(doc: dict[str, Any]) -> dict[str, float]:
    """Doc-shaped wrapper over net_amounts().

    Used by the OrderPlaced automation so a Purchase Order's unit_cost keeps
    whatever discount was actually applied, and by the place-order preview so
    the review screen shows the same number the PO is created at.
    """
    return net_amounts(
        [QuotationLineItem(**raw) for raw in doc.get("items", [])],
        doc.get("project_discount_pct", 0) or 0,
        doc.get("category_discounts", {}) or {},
        {k: RoomDiscountCfg(**v) for k, v in (doc.get("room_discounts") or {}).items()},
    )


def stamp_net_amounts(
    item_dicts: list[dict[str, Any]],
    project_discount_pct: float = 0.0,
    category_discounts: dict[str, float] | None = None,
    room_discounts: dict[str, RoomDiscountCfg] | None = None,
) -> list[dict[str, Any]]:
    """Write each line's post-discount total onto its dict as net_amount.

    Mutates in place and returns the same list, so it can be dropped into a
    persistence path without re-binding. Always overwrites: a discount change
    re-prices every line even when no line itself was edited.
    """
    resolved = net_amounts(
        [QuotationLineItem(**raw) for raw in item_dicts],
        project_discount_pct,
        category_discounts,
        room_discounts,
    )
    for raw in item_dicts:
        raw["net_amount"] = resolved.get(raw.get("id"), 0.0)
    return item_dicts
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_pricing_net_amounts.py -v`
Expected: PASS — 10 passed

- [ ] **Step 6: Run the full suite — the refactor must not move any existing number**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit -v`
Expected: PASS — 197 previously-passing tests still pass, plus the 10 new ones (207 total). If any pricing or sales-data test now fails, the refactor changed behaviour and must be corrected — the totals are the contract.

- [ ] **Step 7: Commit**

```bash
git add backend/services/pricing.py backend/models.py backend/tests/unit/test_pricing_net_amounts.py
git commit -m "Unify the quotation discount cascade into one implementation

The room flat-amount allocation loop existed twice, in
recalc_quotation_totals and per_line_net_amounts, which is how per-line
revenue could drift from grand_total. Both now build on one shared
_resolve_line_rows core, and net_amounts/stamp_net_amounts expose the
per-line result that analytics will sum.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Stamp `net_amount` on both quotation write paths

**Files:**
- Modify: `backend/routes/quotation_routes.py` (create ~line 206, update ~line 344-360)
- Test: `backend/tests/unit/test_quotation_net_amount_stamping.py`

**Interfaces:**
- Consumes: `net_amounts`, `stamp_net_amounts` from Task 1
- Produces: `_stamped_items_for_update(update, doc) -> list[dict]` in `quotation_routes` — pure, testable without a database

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_quotation_net_amount_stamping.py`:

```python
"""A discount-only edit re-prices every line, so items must be re-stamped
even when the request body carried no items at all."""
from __future__ import annotations

from routes.quotation_routes import _stamped_items_for_update


def _raw(line_id: str, qty: float, price: float, **kw) -> dict:
    return {"id": line_id, "product_id": f"p-{line_id}", "sku": f"S-{line_id}", "name": line_id, "qty": qty, "unit_price": price, **kw}


def test_items_supplied_in_the_update_are_stamped():
    doc = {"items": [], "project_discount_pct": 0, "category_discounts": {}, "room_discounts": {}}
    update = {"items": [_raw("a", 1, 100.0)], "project_discount_pct": 10}
    assert [i["net_amount"] for i in _stamped_items_for_update(update, doc)] == [90.0]


def test_discount_only_edit_restamps_the_existing_items():
    doc = {
        "items": [_raw("a", 1, 100.0, net_amount=100.0), _raw("b", 1, 200.0, net_amount=200.0)],
        "project_discount_pct": 0,
        "category_discounts": {},
        "room_discounts": {},
    }
    update = {"project_discount_pct": 25}  # no items in the body at all
    assert [i["net_amount"] for i in _stamped_items_for_update(update, doc)] == [75.0, 150.0]


def test_falls_back_to_stored_discount_config_for_keys_not_being_updated():
    doc = {
        "items": [_raw("a", 1, 100.0)],
        "project_discount_pct": 10,
        "category_discounts": {},
        "room_discounts": {},
    }
    update = {"items": [_raw("a", 1, 100.0)]}  # discounts unchanged
    assert _stamped_items_for_update(update, doc)[0]["net_amount"] == 90.0


def test_empty_quotation_returns_empty_list():
    doc = {"items": [], "project_discount_pct": 0, "category_discounts": {}, "room_discounts": {}}
    assert _stamped_items_for_update({"project_discount_pct": 5}, doc) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_quotation_net_amount_stamping.py -v`
Expected: FAIL — `ImportError: cannot import name '_stamped_items_for_update'`

- [ ] **Step 3: Add the helper to `quotation_routes.py`**

Extend the existing pricing import at line 33-34:

```python
from services.pricing import net_amounts, per_line_net_amounts, stamp_net_amounts
from services.pricing import recalc_quotation_totals as _recalc
```

Then add this module-level helper immediately above `async def update_quotation(` (~line 262):

```python
def _stamped_items_for_update(update: dict, doc: dict) -> list[dict]:
    """Re-stamp net_amount on the items that are about to be persisted.

    Reads each pricing input from the update when present and the stored doc
    otherwise. A discount-only edit carries no items in the body but still
    re-prices every line, so the stored items are re-stamped too — skipping
    that is how a stale net_amount would silently under- or over-report
    product and brand revenue.
    """
    items = update.get("items", doc.get("items", []) or [])
    return stamp_net_amounts(
        [dict(raw) for raw in items],
        update.get("project_discount_pct", doc.get("project_discount_pct", 0) or 0),
        update.get("category_discounts", doc.get("category_discounts", {}) or {}),
        {
            k: RoomDiscountCfg(**v)
            for k, v in (update.get("room_discounts", doc.get("room_discounts", {}) or {})).items()
        },
    )
```

- [ ] **Step 4: Wire the create path**

In `create_quotation`, replace the single line at ~206:

```python
    totals = _recalc(items, body.project_discount_pct or 0, body.category_discounts or {}, body.room_discounts or {})
```

with:

```python
    totals = _recalc(items, body.project_discount_pct or 0, body.category_discounts or {}, body.room_discounts or {})
    # Denormalize each line's post-discount total so analytics can sum one
    # field instead of re-deriving the discount cascade per report.
    _line_nets = net_amounts(items, body.project_discount_pct or 0, body.category_discounts or {}, body.room_discounts or {})
    for _it in items:
        _it.net_amount = _line_nets.get(_it.id, 0.0)
```

- [ ] **Step 5: Wire the update path**

In `update_quotation`, replace this line (~360):

```python
        update.update(totals)
```

with:

```python
        update.update(totals)
        update["items"] = _stamped_items_for_update(update, doc)
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit -v`
Expected: PASS — 211 total (207 from Task 1 + 4 new)

- [ ] **Step 7: Commit**

```bash
git add backend/routes/quotation_routes.py backend/tests/unit/test_quotation_net_amount_stamping.py
git commit -m "Stamp items.net_amount on both quotation write paths

Create and update now denormalize each line's post-discount total. The
update path re-stamps stored items even when the body carried none,
because a discount-only edit re-prices every line.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Migration — backfill `items.net_amount`

**Files:**
- Create: `backend/migrations/0011_backfill_quotation_net_amounts.py`
- Test: `backend/tests/unit/test_migration_0011_net_amounts.py`

**Interfaces:**
- Consumes: `per_line_net_amounts` (Task 1)
- Produces: `compute_net_amount_items(doc) -> list[dict]` — the pure transform, importable and testable without a database

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_migration_0011_net_amounts.py`. The module name starts with a digit, so it must be imported via `importlib`, not a plain `import` statement:

```python
"""The backfill must reproduce exactly what the write path now stamps."""
from __future__ import annotations

import importlib

migration = importlib.import_module("migrations.0011_backfill_quotation_net_amounts")


def test_computes_nets_for_every_line():
    doc = {
        "items": [
            {"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0},
            {"id": "b", "product_id": "p2", "sku": "S2", "name": "B", "qty": 2, "unit_price": 50.0},
        ],
        "project_discount_pct": 10,
    }
    assert [i["net_amount"] for i in migration.compute_net_amount_items(doc)] == [90.0, 90.0]


def test_preserves_all_other_line_fields():
    doc = {"items": [{"id": "a", "product_id": "p1", "sku": "S1", "name": "A", "qty": 1, "unit_price": 100.0, "room": "Bath", "mrp": 120.0}]}
    out = migration.compute_net_amount_items(doc)[0]
    assert out["room"] == "Bath" and out["mrp"] == 120.0 and out["net_amount"] == 100.0


def test_quotation_with_no_items_yields_empty_list():
    assert migration.compute_net_amount_items({"items": []}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_migration_0011_net_amounts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrations.0011_backfill_quotation_net_amounts'`

- [ ] **Step 3: Write the migration**

Create `backend/migrations/0011_backfill_quotation_net_amounts.py`:

```python
"""Denormalize each quotation line's post-discount total onto
items[].net_amount.

Before this, per-line revenue was recomputed per report as qty x unit_price
— ignoring the product/room/category/project discount cascade — so brand and
product revenue never summed to grand_total. Analytics now sums net_amount,
which is stamped at write time (routes/quotation_routes.py); this migration
backfills every document written before that landed.

Idempotent: recomputing from the same source fields always yields the same
value, so re-running is a no-op. Nothing is deleted.
"""
from __future__ import annotations

from services.pricing import per_line_net_amounts


def compute_net_amount_items(doc: dict) -> list[dict]:
    """Return the doc's items with net_amount stamped, leaving every other
    field untouched. Pure — no database access — so it is unit-testable."""
    nets = per_line_net_amounts(doc)
    return [{**raw, "net_amount": nets.get(raw.get("id"), 0.0)} for raw in doc.get("items", []) or []]


async def up(db) -> None:
    cursor = db.quotations.find({"items.0": {"$exists": True}}, {"_id": 0})
    async for doc in cursor:
        await db.quotations.update_one(
            {"id": doc["id"]},
            {"$set": {"items": compute_net_amount_items(doc)}},
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_migration_0011_net_amounts.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Dry-run against the live database, read-only**

Run:

```bash
cd backend && ./.venv/bin/python -c "
import asyncio, sys, importlib
sys.path.insert(0, '.')
from db import db
m = importlib.import_module('migrations.0011_backfill_quotation_net_amounts')
async def main():
    drift = 0
    async for doc in db.quotations.find({'items.0': {'$exists': True}}, {'_id': 0}):
        total = sum(i['net_amount'] for i in m.compute_net_amount_items(doc))
        gt = doc.get('grand_total') or 0
        if abs(total - gt) > 0.01 * len(doc.get('items') or []):
            drift += 1
            print('DRIFT', doc.get('number'), round(total, 2), gt)
    print('quotations with reconciliation drift:', drift)
asyncio.run(main())
"
```

Expected: `quotations with reconciliation drift: 0`. Any drift means the cascade disagrees with the stored `grand_total` on real data — stop and investigate before writing anything.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/0011_backfill_quotation_net_amounts.py backend/tests/unit/test_migration_0011_net_amounts.py
git commit -m "Add migration backfilling items.net_amount

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: `ordered_at` — write-once order confirmation timestamp

Two code paths set `status = "ordered"`: `PATCH /{id}` (line ~316) and `POST /{id}/place-order/confirm` (line ~897). Both must stamp, and neither may ever overwrite an existing value.

**Files:**
- Modify: `backend/models.py` (`Quotation`)
- Modify: `backend/routes/quotation_routes.py` (~316, ~897)
- Test: `backend/tests/unit/test_quotation_ordered_at.py`

**Interfaces:**
- Produces: `_ordered_at_patch(doc, new_status) -> dict` in `quotation_routes` — returns `{"ordered_at": <iso>}` or `{}`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_quotation_ordered_at.py`:

```python
"""Revenue is dated by ordered_at, so the stamp must be write-once. If a
later edit could move it, editing an old order would move its revenue into
the current reporting period."""
from __future__ import annotations

from routes.quotation_routes import _ordered_at_patch


def test_stamps_on_transition_to_ordered():
    patch = _ordered_at_patch({"status": "approved"}, "ordered")
    assert "ordered_at" in patch and patch["ordered_at"]


def test_never_overwrites_an_existing_stamp():
    doc = {"status": "ordered", "ordered_at": "2026-07-01T00:00:00+00:00"}
    assert _ordered_at_patch(doc, "ordered") == {}


def test_no_stamp_for_any_other_status():
    for status in ("draft", "sent", "approved", "rejected", "lost"):
        assert _ordered_at_patch({"status": "draft"}, status) == {}


def test_stamp_is_iso_utc():
    stamped = _ordered_at_patch({}, "ordered")["ordered_at"]
    assert "T" in stamped and ("+00:00" in stamped or stamped.endswith("Z"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_quotation_ordered_at.py -v`
Expected: FAIL — `ImportError: cannot import name '_ordered_at_patch'`

- [ ] **Step 3: Add the model field**

In `backend/models.py`, in `class Quotation`, immediately after the `status` field:

```python
    # Stamped once, when status first becomes "ordered", and never rewritten.
    # EVERY revenue calculation dates by this field. updated_at cannot be used:
    # it is re-stamped on every edit, so editing an old order would move its
    # revenue into the current period.
    ordered_at: Optional[str] = None
```

- [ ] **Step 4: Add the helper**

In `backend/routes/quotation_routes.py`, add above `async def update_quotation(`:

```python
def _ordered_at_patch(doc: dict, new_status: str) -> dict:
    """Return the ordered_at fragment for a status transition, or {}.

    Write-once by design — an order confirmed in June must keep dating to
    June no matter how many times it is edited afterwards.
    """
    if new_status == "ordered" and not doc.get("ordered_at"):
        return {"ordered_at": now_iso()}
    return {}
```

- [ ] **Step 5: Wire the PATCH path**

Replace lines ~316-319:

```python
    if body.status is not None:
        update["status"] = body.status
        if body.status == "approved":
            update["approved_by"] = user.id
```

with:

```python
    if body.status is not None:
        update["status"] = body.status
        if body.status == "approved":
            update["approved_by"] = user.id
        update.update(_ordered_at_patch(doc, body.status))
```

- [ ] **Step 6: Wire the place-order path**

Replace the `$set` at ~897:

```python
                        {"$set": {"status": "ordered", "updated_at": now_iso()}},
```

with:

```python
                        {"$set": {"status": "ordered", "updated_at": now_iso(), **_ordered_at_patch(doc, "ordered")}},
```

- [ ] **Step 7: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit -v`
Expected: PASS — 218 total (214 + 4 new)

- [ ] **Step 8: Commit**

```bash
git add backend/models.py backend/routes/quotation_routes.py backend/tests/unit/test_quotation_ordered_at.py
git commit -m "Add write-once ordered_at to quotations

Revenue was dated by updated_at, which is re-stamped on every edit, so
editing an old order silently moved its revenue between reporting
periods. Both paths that set status=ordered now stamp ordered_at, and
neither can overwrite an existing value.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Migration — backfill `ordered_at`

**Files:**
- Create: `backend/migrations/0012_backfill_quotation_ordered_at.py`

- [ ] **Step 1: Write the migration**

Create `backend/migrations/0012_backfill_quotation_ordered_at.py`:

```python
"""Backfill ordered_at for quotations confirmed before the field existed.

updated_at is the best available approximation and is explicitly imperfect:
for any order edited after confirmation it is the last edit time, not the
confirmation time. It is recorded here so a future session reading a July
2026 revenue chart knows those 35 rows are approximate and every row after
this migration is exact.

Only fills where the field is missing, so it never overwrites a real stamp
and is safe to re-run.
"""
from __future__ import annotations


async def up(db) -> None:
    cursor = db.quotations.find(
        {"status": "ordered", "ordered_at": {"$in": [None, ""]}},
        {"_id": 0, "id": 1, "updated_at": 1, "created_at": 1},
    )
    async for doc in cursor:
        stamp = doc.get("updated_at") or doc.get("created_at")
        if not stamp:
            continue
        await db.quotations.update_one({"id": doc["id"]}, {"$set": {"ordered_at": stamp}})
```

- [ ] **Step 2: Verify the target set before running anything**

Run:

```bash
cd backend && ./.venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, '.')
from db import db
async def main():
    print('ordered total:', await db.quotations.count_documents({'status': 'ordered'}))
    print('missing ordered_at:', await db.quotations.count_documents({'status': 'ordered', 'ordered_at': {'\$in': [None, '']}}))
asyncio.run(main())
"
```

Expected: `ordered total: 35` and `missing ordered_at: 35`.

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/0012_backfill_quotation_ordered_at.py
git commit -m "Add migration backfilling ordered_at from updated_at

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Migration — analytics indexes

Every index from spec §3.3. No index on `quotations` currently supports any analytics access pattern.

**Files:**
- Create: `backend/migrations/0013_add_analytics_indexes.py`

- [ ] **Step 1: Write the migration**

Create `backend/migrations/0013_add_analytics_indexes.py`:

```python
"""Indexes for the Executive Operating System's access patterns (spec §3.3).

Nothing on quotations supported analytics before this: every dashboard query
was a collection scan. Harmless at 78 documents, fatal at 100k.

Every create_index tolerates OperationFailure code 85 — a same-keys index
under a different name. That exact conflict hard-crashed the runner twice on
2026-07-17 (migrations 0002 and 0003), so it is the house pattern.
"""
from __future__ import annotations

from pymongo.errors import OperationFailure

_INDEX_CONFLICT_CODE = 85


async def _create_index_tolerant(collection, keys, **kwargs) -> None:
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as e:
        if e.code != _INDEX_CONFLICT_CODE:
            raise


async def up(db) -> None:
    await _create_index_tolerant(db.quotations, [("status", 1), ("floor_id", 1), ("ordered_at", -1)], name="quotations_analytics_revenue")
    await _create_index_tolerant(db.quotations, [("floor_id", 1), ("created_at", -1)], name="quotations_analytics_created")
    await _create_index_tolerant(db.quotations, [("referrer_id", 1), ("status", 1)], name="quotations_analytics_referrer")
    await _create_index_tolerant(db.quotations, [("customer_id", 1), ("status", 1)], name="quotations_analytics_customer")
    await _create_index_tolerant(db.quotations, [("items.product_id", 1)], name="quotations_analytics_product")

    await _create_index_tolerant(db.payments, [("quotation_id", 1), ("status", 1)], name="payments_analytics_quotation")
    await _create_index_tolerant(db.payments, [("floor_id", 1), ("paid_at", -1)], name="payments_analytics_paid")

    await _create_index_tolerant(db.walkins, [("floor_id", 1), ("created_at", -1)], name="walkins_analytics_created")
    await _create_index_tolerant(db.walkins, [("customer_id", 1)], name="walkins_analytics_customer")

    await _create_index_tolerant(db.followups, [("floor_id", 1), ("status", 1), ("due_at", 1)], name="followups_analytics_due")

    await _create_index_tolerant(db.customer_orders, [("floor_id", 1), ("overall_status", 1), ("created_at", -1)], name="customer_orders_analytics")
    await _create_index_tolerant(db.dispatches, [("floor_id", 1), ("dispatch_date", -1)], name="dispatches_analytics_date")
    await _create_index_tolerant(db.dispatches, [("customer_order_id", 1)], name="dispatches_analytics_order")

    await _create_index_tolerant(db.activity_events, [("customer_id", 1), ("created_at", -1)], name="activity_analytics_customer")
    await _create_index_tolerant(db.activity_events, [("quotation_id", 1), ("created_at", -1)], name="activity_analytics_quotation")
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `cd backend && ./.venv/bin/python -c "import importlib; importlib.import_module('migrations.0013_add_analytics_indexes'); print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/0013_add_analytics_indexes.py
git commit -m "Add analytics indexes migration

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Run migrations 0011-0013 against the live database

This is the only task that writes to production data. It needs the user's explicit go-ahead before Step 2.

**Files:** none — this task runs the existing `backend/scripts/run_migrations.py`.

- [ ] **Step 1: List pending migrations (read-only)**

Run: `cd backend && ./.venv/bin/python scripts/run_migrations.py --dry-run`
Expected: `0011_backfill_quotation_net_amounts`, `0012_backfill_quotation_ordered_at`, and `0013_add_analytics_indexes` listed as pending. If anything else is listed, stop and report it — another session may have added a migration.

- [ ] **Step 2: Ask the user before applying**

Report the dry-run output and ask for explicit confirmation to write to the live `buildcon_house` database. Do not proceed without it.

- [ ] **Step 3: Apply**

Run: `cd backend && ./.venv/bin/python scripts/run_migrations.py`
Expected: three migrations applied, no errors.

- [ ] **Step 4: Verify the result against real data**

Run:

```bash
cd backend && ./.venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, '.')
from db import db
async def main():
    print('ordered missing ordered_at:', await db.quotations.count_documents({'status': 'ordered', 'ordered_at': {'\$in': [None, '']}}))
    bad = 0
    async for d in db.quotations.find({'items.0': {'\$exists': True}}, {'_id': 0, 'items': 1}):
        if any(i.get('net_amount') is None for i in d['items']):
            bad += 1
    print('quotations with an unstamped line:', bad)
    print('quotation indexes:', sorted((await db.quotations.index_information()).keys()))
asyncio.run(main())
"
```

Expected: both counts `0`, and the five `quotations_analytics_*` indexes present.

- [ ] **Step 5: Commit** — nothing to commit; record the verification output in the task report.

---

## Task 8: Owner targets

The Health Score needs something to measure against. Storage lands now; the Goals & Targets workspace (Phase 8) reuses this exact document.

**Files:**
- Modify: `backend/models.py`
- Create: `backend/routes/analytics_settings_routes.py`
- Modify: `backend/server.py`
- Test: `backend/tests/unit/test_analytics_targets.py`

**Interfaces:**
- Produces: `AnalyticsTargets` model; `GET /api/analytics/targets`; `PUT /api/analytics/targets`; `available_target_signals(targets) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_targets.py`:

```python
"""Unset targets must be reported as unavailable, never defaulted to a
number — the Health Score renormalizes over available signals rather than
scoring against an invented benchmark."""
from __future__ import annotations

from models import AnalyticsTargets
from routes.analytics_settings_routes import available_target_signals


def test_defaults_leave_owner_declared_targets_unset():
    t = AnalyticsTargets()
    assert t.monthly_revenue_target is None
    assert t.target_conversion_pct is None
    assert t.target_collection_pct == 90
    assert t.payment_terms_days == 30


def test_no_owner_targets_means_neither_signal_is_available():
    assert available_target_signals(AnalyticsTargets()) == []


def test_revenue_target_enables_only_revenue_attainment():
    assert available_target_signals(AnalyticsTargets(monthly_revenue_target=500000)) == ["revenue_attainment"]


def test_both_targets_enable_both_signals():
    t = AnalyticsTargets(monthly_revenue_target=500000, target_conversion_pct=30)
    assert available_target_signals(t) == ["revenue_attainment", "conversion_health"]


def test_zero_is_not_a_target():
    # A zero revenue target would make attainment infinite; treat it as unset.
    assert available_target_signals(AnalyticsTargets(monthly_revenue_target=0)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_targets.py -v`
Expected: FAIL — `ImportError: cannot import name 'AnalyticsTargets' from 'models'`

- [ ] **Step 3: Add the model**

Append to `backend/models.py`:

```python
class AnalyticsTargets(BaseModel):
    """Owner-declared targets the Business Health Score measures against.

    monthly_revenue_target and target_conversion_pct deliberately default to
    None: without a declared target there is no honest way to score revenue
    or conversion, so those components are excluded and the score reports how
    many signals it used. Never default them to an invented benchmark.
    """
    monthly_revenue_target: Optional[float] = Field(default=None, ge=0)
    target_conversion_pct: Optional[float] = Field(default=None, ge=0, le=100)
    target_collection_pct: float = Field(default=90, ge=0, le=100)
    payment_terms_days: int = Field(default=30, ge=0)
```

- [ ] **Step 4: Write the route module**

Create `backend/routes/analytics_settings_routes.py`:

```python
"""Owner-declared analytics targets.

Stored as a single key-addressed document in the existing `settings`
collection (key "analytics_targets"), which the Phase 8 Goals & Targets
workspace will read and write unchanged — targets are stored once.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import require_roles
from db import db
from models import AnalyticsTargets, UserPublic
from utils import now_iso

router = APIRouter(prefix="/analytics", tags=["analytics"])

SETTINGS_KEY = "analytics_targets"


def available_target_signals(targets: AnalyticsTargets) -> list[str]:
    """Which Health Score components have a target to measure against.

    A zero target is treated as unset — dividing by it would make attainment
    infinite rather than meaningful.
    """
    signals = []
    if targets.monthly_revenue_target:
        signals.append("revenue_attainment")
    if targets.target_conversion_pct:
        signals.append("conversion_health")
    return signals


async def load_targets() -> AnalyticsTargets:
    doc = await db.settings.find_one({"key": SETTINGS_KEY}, {"_id": 0})
    return AnalyticsTargets(**{k: v for k, v in (doc or {}).items() if k in AnalyticsTargets.model_fields})


@router.get("/targets")
async def get_targets(user: UserPublic = Depends(require_roles("owner", "admin", "manager"))):
    targets = await load_targets()
    return {"targets": targets.model_dump(), "available_signals": available_target_signals(targets)}


@router.put("/targets")
async def put_targets(body: AnalyticsTargets, user: UserPublic = Depends(require_roles("owner", "admin"))):
    await db.settings.update_one(
        {"key": SETTINGS_KEY},
        {"$set": {**body.model_dump(), "key": SETTINGS_KEY, "updated_at": now_iso(), "updated_by": user.id, "updated_by_name": user.full_name}},
        upsert=True,
    )
    return {"targets": body.model_dump(), "available_signals": available_target_signals(body)}
```

Note the role split: `manager` may read targets, only `owner`/`admin` may set them.

- [ ] **Step 5: Register the router**

In `backend/server.py`, find the block of `app.include_router(...)` calls and add alongside them:

```python
from routes.analytics_settings_routes import router as analytics_settings_router
app.include_router(analytics_settings_router, prefix="/api")
```

Match the exact import and `include_router` style already used for neighbouring routers in that file — if they are imported at the top rather than inline, follow that.

- [ ] **Step 6: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit -v`
Expected: PASS — 223 total

- [ ] **Step 7: Verify the app still boots**

Run: `cd backend && ./.venv/bin/python -c "import server; print('ok')"`
Expected: `ok` (catches a bad import or a duplicate route prefix)

- [ ] **Step 8: Commit**

```bash
git add backend/models.py backend/routes/analytics_settings_routes.py backend/server.py backend/tests/unit/test_analytics_targets.py
git commit -m "Add owner-declared analytics targets

Revenue and conversion targets default to unset so the Health Score can
exclude those components rather than score against an invented benchmark.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: `analytics/filters.py` — the only match builder

**Files:**
- Create: `backend/services/analytics/__init__.py`
- Create: `backend/services/analytics/filters.py`
- Test: `backend/tests/unit/test_analytics_filters.py`

**Interfaces:**
- Consumes: `periods.resolve` is NOT yet available — this task takes an already-resolved `(start, end)` tuple, so it has no dependency on Task 10
- Produces:
  - `AnalyticsFilter` frozen dataclass
  - `date_field_for(status) -> str`
  - `build_match(f, accessible_floors, window, product_ids=None) -> dict`
  - `FloorAccessError` exception

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_filters.py`:

```python
"""One match builder. Floor access is enforced here, and revenue-status
queries date by ordered_at rather than updated_at."""
from __future__ import annotations

import pytest

from services.analytics.filters import AnalyticsFilter, FloorAccessError, build_match, date_field_for

WINDOW = ("2026-07-01T00:00:00+00:00", "2026-07-31T23:59:59+00:00")


def test_ordered_status_dates_by_ordered_at():
    assert date_field_for("ordered") == "ordered_at"


def test_other_statuses_date_by_created_at():
    for status in ("draft", "sent", "approved", "any"):
        assert date_field_for(status) == "created_at"


def test_status_and_window_are_always_applied():
    m = build_match(AnalyticsFilter(), accessible_floors=None, window=WINDOW)
    assert m["status"] == "ordered"
    assert m["ordered_at"] == {"$gte": WINDOW[0], "$lte": WINDOW[1]}


def test_all_floors_for_an_unrestricted_user_adds_no_floor_clause():
    m = build_match(AnalyticsFilter(floor_id="all"), accessible_floors=None, window=WINDOW)
    assert "floor_id" not in m


def test_all_floors_for_a_restricted_user_is_limited_to_their_floors():
    m = build_match(AnalyticsFilter(floor_id="all"), accessible_floors=["ground-floor"], window=WINDOW)
    assert m["floor_id"] == {"$in": ["ground-floor"]}


def test_explicit_floor_is_applied():
    m = build_match(AnalyticsFilter(floor_id="ground-floor"), accessible_floors=None, window=WINDOW)
    assert m["floor_id"] == {"$in": ["ground-floor"]}


def test_floor_outside_the_callers_access_is_refused():
    with pytest.raises(FloorAccessError):
        build_match(AnalyticsFilter(floor_id="first-floor"), accessible_floors=["ground-floor"], window=WINDOW)


def test_entity_filters_map_to_their_stored_fields():
    f = AnalyticsFilter(salesperson_id="u1", customer_id="c1", referrer_id="r1", referrer_type="architect")
    m = build_match(f, accessible_floors=None, window=WINDOW)
    assert m["created_by"] == "u1"
    assert m["customer_id"] == "c1"
    assert m["referrer_id"] == "r1"
    assert m["referrer_type"] == "architect"


def test_brand_filter_uses_the_supplied_product_ids():
    m = build_match(AnalyticsFilter(brand_id="b1"), accessible_floors=None, window=WINDOW, product_ids=["p1", "p2"])
    assert m["items.product_id"] == {"$in": ["p1", "p2"]}


def test_brand_filter_with_no_matching_products_matches_nothing():
    # An empty $in must not silently widen to "all products".
    m = build_match(AnalyticsFilter(brand_id="b1"), accessible_floors=None, window=WINDOW, product_ids=[])
    assert m["items.product_id"] == {"$in": []}


def test_open_window_omits_the_date_clause():
    m = build_match(AnalyticsFilter(), accessible_floors=None, window=(None, None))
    assert "ordered_at" not in m


def test_status_any_drops_the_status_clause():
    m = build_match(AnalyticsFilter(status="any"), accessible_floors=None, window=WINDOW)
    assert "status" not in m
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics'`

- [ ] **Step 3: Create the package and the module**

Create `backend/services/analytics/__init__.py`:

```python
"""Shared analytics layer for the Executive Operating System.

One canonical filter builder, one comparison engine, one cache, one metric
registry. Every workspace consumes these; no workspace reimplements a KPI.
See docs/superpowers/specs/2026-08-01-executive-operating-system-design.md.
"""
```

Create `backend/services/analytics/filters.py`:

```python
"""The only place an analytics Mongo match document is built."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


class FloorAccessError(Exception):
    """Caller asked for a floor they cannot see. Routes turn this into a 403."""


@dataclass(frozen=True)
class AnalyticsFilter:
    floor_id: Optional[str] = None          # None or "all" → every accessible floor
    preset: str = "this_month"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    brand_id: Optional[str] = None
    category_id: Optional[str] = None
    supplier_id: Optional[str] = None
    salesperson_id: Optional[str] = None
    referrer_type: Optional[str] = None
    referrer_id: Optional[str] = None
    customer_id: Optional[str] = None
    status: str = "ordered"                 # "any" drops the status clause


def date_field_for(status: str) -> str:
    """Revenue dates by ordered_at — the write-once confirmation stamp.

    updated_at is never used: it is re-stamped on every edit, so an edited
    old order would move between reporting periods. Non-revenue queries
    (open quotations, pipeline) date by created_at instead.
    """
    return "ordered_at" if status == "ordered" else "created_at"


def build_match(
    f: AnalyticsFilter,
    accessible_floors: Optional[Sequence[str]],
    window: tuple[Optional[str], Optional[str]],
    product_ids: Optional[Sequence[str]] = None,
) -> dict:
    """Build the match stage every analytics pipeline starts from.

    accessible_floors is None for owner/manager (all floors). window is an
    already-resolved (start, end) pair from periods.resolve. product_ids is
    supplied by the caller when filtering by brand, so this stays free of
    database access and unit-testable.
    """
    match: dict = {}

    if f.status != "any":
        match["status"] = f.status

    if f.floor_id and f.floor_id != "all":
        if accessible_floors is not None and f.floor_id not in accessible_floors:
            raise FloorAccessError(f.floor_id)
        match["floor_id"] = {"$in": [f.floor_id]}
    elif accessible_floors is not None:
        match["floor_id"] = {"$in": list(accessible_floors)}

    start, end = window
    if start or end:
        bounds = {k: v for k, v in (("$gte", start), ("$lte", end)) if v}
        match[date_field_for(f.status)] = bounds

    if f.salesperson_id:
        match["created_by"] = f.salesperson_id
    if f.customer_id:
        match["customer_id"] = f.customer_id
    if f.referrer_id:
        match["referrer_id"] = f.referrer_id
    if f.referrer_type:
        match["referrer_type"] = f.referrer_type
    if f.brand_id is not None and product_ids is not None:
        # Deliberately keeps an empty list: a brand with no products must
        # match nothing, not everything.
        match["items.product_id"] = {"$in": list(product_ids)}

    return match
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_filters.py -v`
Expected: PASS — 12 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/__init__.py backend/services/analytics/filters.py backend/tests/unit/test_analytics_filters.py
git commit -m "Add the canonical analytics filter builder

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: `analytics/periods.py` — comparison engine with honest degradation

**Files:**
- Create: `backend/services/analytics/periods.py`
- Test: `backend/tests/unit/test_analytics_periods.py`

**Interfaces:**
- Produces:
  - `Period` frozen dataclass — `start`, `end`, `label`
  - `resolve(preset, date_from=None, date_to=None, now=None) -> Period`
  - `previous(period, mode="period") -> Optional[Period]` where mode ∈ `period` | `month` | `quarter` | `year`
  - `compare(current, previous_value, prior_window_exists) -> dict` — `{delta_pct, direction, history_state}`
  - `HISTORY_OK`, `HISTORY_NO_PRIOR`, `HISTORY_INSUFFICIENT` constants

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_periods.py`:

```python
"""Never +100%, never 0%, never a fabricated delta. When there is nothing to
compare against, say so."""
from __future__ import annotations

from datetime import datetime, timezone

from services.analytics.periods import (
    HISTORY_INSUFFICIENT,
    HISTORY_NO_PRIOR,
    HISTORY_OK,
    compare,
    previous,
    resolve,
)

NOW = datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)


def test_today_starts_at_midnight_utc():
    p = resolve("today", now=NOW)
    assert p.start.startswith("2026-08-01T00:00:00")
    assert p.label == "Today"


def test_yesterday_is_a_full_closed_day():
    p = resolve("yesterday", now=NOW)
    assert p.start.startswith("2026-07-31T00:00:00")
    assert p.end.startswith("2026-08-01T00:00:00")


def test_this_week_starts_monday():
    # 2026-08-01 is a Saturday; the week starts Monday 2026-07-27.
    assert resolve("this_week", now=NOW).start.startswith("2026-07-27")


def test_last_n_days_preset():
    assert resolve("last_7_days", now=NOW).start.startswith("2026-07-26")


def test_this_month_starts_on_the_first():
    assert resolve("this_month", now=NOW).start.startswith("2026-08-01")


def test_last_month_is_the_whole_previous_month():
    p = resolve("last_month", now=NOW)
    assert p.start.startswith("2026-07-01")
    assert p.end.startswith("2026-08-01")


def test_custom_passes_the_supplied_bounds_through():
    p = resolve("custom", date_from="2026-01-01", date_to="2026-03-31", now=NOW)
    assert (p.start, p.end) == ("2026-01-01", "2026-03-31")


def test_all_is_an_open_window():
    p = resolve("all", now=NOW)
    assert p.start is None and p.end is None


def test_previous_period_is_the_immediately_preceding_equal_span():
    p = resolve("last_month", now=NOW)          # July
    prev = previous(p)
    assert prev.start.startswith("2026-06-01")
    assert prev.end.startswith("2026-07-01")


def test_previous_year_shifts_by_twelve_months():
    prev = previous(resolve("last_month", now=NOW), mode="year")
    assert prev.start.startswith("2025-07-01")


def test_previous_of_an_open_window_is_none():
    assert previous(resolve("all", now=NOW)) is None


def test_compare_reports_a_real_delta():
    result = compare(120.0, 100.0, prior_window_exists=True)
    assert result["delta_pct"] == 20.0
    assert result["direction"] == "up"
    assert result["history_state"] == HISTORY_OK


def test_compare_reports_a_decline():
    assert compare(75.0, 100.0, prior_window_exists=True)["direction"] == "down"


def test_empty_prior_window_is_not_a_hundred_percent_growth():
    result = compare(500.0, 0.0, prior_window_exists=True)
    assert result["delta_pct"] is None
    assert result["history_state"] == HISTORY_NO_PRIOR


def test_no_prior_window_at_all_is_insufficient_history():
    result = compare(500.0, 0.0, prior_window_exists=False)
    assert result["delta_pct"] is None
    assert result["history_state"] == HISTORY_INSUFFICIENT


def test_flat_is_a_real_zero_not_a_missing_comparison():
    result = compare(100.0, 100.0, prior_window_exists=True)
    assert result["delta_pct"] == 0.0
    assert result["direction"] == "flat"
    assert result["history_state"] == HISTORY_OK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_periods.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.periods'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/periods.py`:

```python
"""Period resolution and the comparison engine.

The comparison logic is complete now and starts producing real numbers the
moment history accumulates — no future code change. Until then it reports
WHY a comparison is unavailable instead of inventing one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

HISTORY_OK = "ok"
HISTORY_NO_PRIOR = "no_prior_period"
HISTORY_INSUFFICIENT = "insufficient_history"


@dataclass(frozen=True)
class Period:
    start: Optional[str]
    end: Optional[str]
    label: str


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return dt.replace(year=year, month=month)


def resolve(preset: str, date_from: Optional[str] = None, date_to: Optional[str] = None, now: Optional[datetime] = None) -> Period:
    """Turn a preset into a concrete window. `all` and an unknown preset both
    yield an open window rather than raising — a report with no date filter is
    a legitimate request."""
    if preset == "custom":
        return Period(date_from, date_to, "Custom range")

    now = now or datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if preset == "today":
        return Period(_iso(today), _iso(now), "Today")
    if preset == "yesterday":
        return Period(_iso(today - timedelta(days=1)), _iso(today), "Yesterday")
    if preset == "this_week":
        return Period(_iso(today - timedelta(days=today.weekday())), _iso(now), "This week")
    if preset.startswith("last_") and preset.endswith("_days"):
        days = int(preset.split("_")[1])
        return Period(_iso(today - timedelta(days=days - 1)), _iso(now), f"Last {days} days")
    if preset == "this_month":
        return Period(_iso(_month_start(today)), _iso(now), "This month")
    if preset == "last_month":
        end = _month_start(today)
        return Period(_iso(_add_months(end, -1)), _iso(end), "Last month")
    if preset == "quarter":
        start = today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return Period(_iso(start), _iso(now), "This quarter")
    if preset == "year":
        return Period(_iso(today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)), _iso(now), "This year")
    return Period(None, None, "All time")


def previous(period: Period, mode: str = "period") -> Optional[Period]:
    """The window this one is compared against.

    "period" is the immediately preceding equal span; "month"/"quarter"/"year"
    shift by that calendar amount for MoM/QoQ/YoY. An open window has no
    previous — returns None, which compare() turns into insufficient_history.
    """
    if not period.start or not period.end:
        return None
    start = datetime.fromisoformat(period.start)
    end = datetime.fromisoformat(period.end)

    if mode == "period":
        span = end - start
        return Period(_iso(start - span), _iso(start), f"Previous {period.label.lower()}")
    shift = {"month": -1, "quarter": -3, "year": -12}.get(mode)
    if shift is None:
        return None
    return Period(_iso(_add_months(start, shift)), _iso(_add_months(end, shift)), f"{period.label} a {mode} ago")


def compare(current: float, previous_value: float, prior_window_exists: bool) -> dict:
    """Compare two periods, or explain why we cannot.

    prior_window_exists=False means there is no comparable window at all (an
    open-ended period, or a comparison reaching before the business has data).
    A prior window that exists but is empty is a different, equally honest
    answer: no_prior_period. Neither is ever rendered as +100%.
    """
    if not prior_window_exists:
        return {"delta_pct": None, "direction": None, "history_state": HISTORY_INSUFFICIENT}
    if not previous_value:
        return {"delta_pct": None, "direction": None, "history_state": HISTORY_NO_PRIOR}
    delta = round((current - previous_value) / previous_value * 100, 1)
    direction = "flat" if delta == 0 else ("up" if delta > 0 else "down")
    return {"delta_pct": delta, "direction": direction, "history_state": HISTORY_OK}
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_periods.py -v`
Expected: PASS — 16 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/periods.py backend/tests/unit/test_analytics_periods.py
git commit -m "Add the analytics comparison engine

Full MoM/QoQ/YoY logic now, with an explicit history_state instead of a
fabricated delta when the prior window is empty or absent.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: `analytics/cache.py` — version-keyed invalidation

**Files:**
- Create: `backend/services/analytics/cache.py`
- Test: `backend/tests/unit/test_analytics_cache.py`

**Interfaces:**
- Produces:
  - `async bump(collection: str) -> None`
  - `async cache_key(metric_id, collections, filter_signature, floors) -> str`
  - `async cached(metric_id, collections, filter_signature, floors, loader, ttl=60)`
  - `reset_memory_state()` — test helper

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_cache.py`:

```python
"""Invalidation is automatic: a write bumps a collection version, the key
changes, and every dependent entry becomes unreachable. Nothing is ever
cleared by hand."""
from __future__ import annotations

import pytest

from services.analytics import cache


@pytest.fixture(autouse=True)
def _clean():
    cache.reset_memory_state()
    yield
    cache.reset_memory_state()


@pytest.mark.asyncio
async def test_key_is_stable_for_identical_inputs():
    a = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor"])
    b = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor"])
    assert a == b


@pytest.mark.asyncio
async def test_key_changes_when_a_dependency_is_bumped():
    before = await cache.cache_key("revenue", ["quotations"], "sig", None)
    await cache.bump("quotations")
    assert await cache.cache_key("revenue", ["quotations"], "sig", None) != before


@pytest.mark.asyncio
async def test_bumping_an_unrelated_collection_leaves_the_key_alone():
    before = await cache.cache_key("revenue", ["quotations"], "sig", None)
    await cache.bump("payments")
    assert await cache.cache_key("revenue", ["quotations"], "sig", None) == before


@pytest.mark.asyncio
async def test_floor_scope_is_part_of_the_key():
    # Omitting this would serve one user's floor-scoped rows to another.
    ground = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor"])
    first = await cache.cache_key("revenue", ["quotations"], "sig", ["first-floor"])
    assert ground != first


@pytest.mark.asyncio
async def test_unrestricted_access_keys_differently_from_a_single_floor():
    unrestricted = await cache.cache_key("revenue", ["quotations"], "sig", None)
    scoped = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor"])
    assert unrestricted != scoped


@pytest.mark.asyncio
async def test_floor_order_does_not_change_the_key():
    a = await cache.cache_key("revenue", ["quotations"], "sig", ["ground-floor", "first-floor"])
    b = await cache.cache_key("revenue", ["quotations"], "sig", ["first-floor", "ground-floor"])
    assert a == b


@pytest.mark.asyncio
async def test_loader_runs_once_then_the_value_is_served_from_cache():
    calls = []

    async def loader():
        calls.append(1)
        return {"revenue": 100}

    first = await cache.cached("revenue", ["quotations"], "sig", None, loader)
    second = await cache.cached("revenue", ["quotations"], "sig", None, loader)
    assert first == second == {"revenue": 100}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_write_makes_the_loader_run_again():
    calls = []

    async def loader():
        calls.append(1)
        return {"revenue": len(calls)}

    await cache.cached("revenue", ["quotations"], "sig", None, loader)
    await cache.bump("quotations")
    result = await cache.cached("revenue", ["quotations"], "sig", None, loader)
    assert result == {"revenue": 2}
    assert len(calls) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.cache'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/cache.py`:

```python
"""Version-keyed analytics cache.

Invalidation is structural rather than procedural: each source collection has
a version counter, every cached metric declares which collections it reads,
and the version numbers are part of the cache key. A write bumps the counter,
the key changes, and every dependent entry becomes unreachable at once —
there is no delete to forget and no stale entry to clear by hand.

Uses Redis when REDIS_URL is set so all workers agree (the app ships
--workers 2 and process-local caches are already a known incoherence
source); falls back to process memory otherwise, exactly like
services/rate_limit.py.
"""
from __future__ import annotations

import json
import time
from typing import Awaitable, Callable, Optional, Sequence

_DEFAULT_TTL = 60

_memory_versions: dict[str, int] = {}
_memory_entries: dict[str, tuple[float, object]] = {}


def reset_memory_state() -> None:
    """Test helper — clears the in-process fallback."""
    _memory_versions.clear()
    _memory_entries.clear()


def _redis():
    """Reuse the rate limiter's optional client so there is one Redis setup."""
    try:
        from services.rate_limit import _redis_client
        return _redis_client()
    except Exception:
        return None


async def _version(collection: str) -> int:
    client = _redis()
    if client is not None:
        raw = await client.get(f"analytics:ver:{collection}")
        return int(raw) if raw else 0
    return _memory_versions.get(collection, 0)


async def bump(collection: str) -> None:
    """Called from a write path. Invalidates every metric reading this
    collection, without touching any cache entry."""
    client = _redis()
    if client is not None:
        await client.incr(f"analytics:ver:{collection}")
        return
    _memory_versions[collection] = _memory_versions.get(collection, 0) + 1


async def cache_key(
    metric_id: str,
    collections: Sequence[str],
    filter_signature: str,
    floors: Optional[Sequence[str]],
) -> str:
    """floors is part of the key on purpose — leaving it out would serve one
    user's floor-scoped rows to another. Sorted so equivalent scopes share an
    entry."""
    versions = ".".join(f"{name}{await _version(name)}" for name in sorted(collections))
    scope = "all" if floors is None else ",".join(sorted(floors))
    return f"analytics:{metric_id}:{versions}:{filter_signature}:{scope}"


async def cached(
    metric_id: str,
    collections: Sequence[str],
    filter_signature: str,
    floors: Optional[Sequence[str]],
    loader: Callable[[], Awaitable[object]],
    ttl: int = _DEFAULT_TTL,
) -> object:
    """Return the cached aggregate or compute and store it."""
    key = await cache_key(metric_id, collections, filter_signature, floors)

    client = _redis()
    if client is not None:
        hit = await client.get(key)
        if hit is not None:
            return json.loads(hit)
        value = await loader()
        await client.set(key, json.dumps(value, default=str), ex=ttl)
        return value

    entry = _memory_entries.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    value = await loader()
    _memory_entries[key] = (time.monotonic() + ttl, value)
    return value
```

- [ ] **Step 4: Confirm the async test plugin is available**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_cache.py -v`

If it fails with "async def functions are not natively supported", check how the existing suite handles async tests:

```bash
cd backend && grep -rn "asyncio_mode\|pytest-asyncio\|anyio" pytest.ini setup.cfg pyproject.toml requirements*.txt tests/ 2>/dev/null | head
```

Match whatever the existing async tests use (`test_tile_orders_delivered.py` is a known async test file — follow its exact decorator and config). Do not add a new async test dependency if one is already configured.

Expected once resolved: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/analytics/cache.py backend/tests/unit/test_analytics_cache.py
git commit -m "Add version-keyed analytics cache

A write bumps a collection version and the cache key changes, so
dependent entries become unreachable without any explicit delete. Floor
scope is part of the key so cached rows cannot leak between users.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 12: `analytics/metrics.py` — the canonical KPI registry

Every KPI in spec §4.3 defined exactly once, as a pipeline builder. No workspace may redefine one.

**Files:**
- Create: `backend/services/analytics/metrics.py`
- Test: `backend/tests/unit/test_analytics_metrics.py`

**Interfaces:**
- Consumes: `AnalyticsFilter`, `build_match` (Task 9)
- Produces:
  - `revenue_pipeline(match) -> list[dict]`
  - `line_revenue_pipeline(match, group_by) -> list[dict]`
  - `outstanding_pipeline(match) -> list[dict]`
  - `METRIC_SOURCES: dict[str, list[str]]` — metric id → collections it reads, for `cache.cached`
  - `filter_signature(f) -> str`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_analytics_metrics.py`:

```python
"""One definition per KPI. Line-level revenue sums the denormalized
net_amount so brand and product revenue reconcile to grand_total."""
from __future__ import annotations

from services.analytics.filters import AnalyticsFilter
from services.analytics.metrics import (
    METRIC_SOURCES,
    filter_signature,
    line_revenue_pipeline,
    outstanding_pipeline,
    revenue_pipeline,
)


def test_revenue_sums_grand_total():
    group = next(s["$group"] for s in revenue_pipeline({"status": "ordered"}) if "$group" in s)
    assert group["revenue"] == {"$sum": "$grand_total"}
    assert group["orders"] == {"$sum": 1}


def test_revenue_pipeline_starts_with_the_supplied_match():
    match = {"status": "ordered", "floor_id": {"$in": ["ground-floor"]}}
    assert revenue_pipeline(match)[0] == {"$match": match}


def test_line_revenue_sums_net_amount_not_qty_times_price():
    # qty x unit_price ignores the discount cascade — that is the drift this
    # whole layer exists to prevent.
    stages = line_revenue_pipeline({"status": "ordered"}, "items.product_id")
    group = next(s["$group"] for s in stages if "$group" in s)
    assert group["revenue"] == {"$sum": "$items.net_amount"}


def test_line_revenue_unwinds_items():
    assert {"$unwind": "$items"} in line_revenue_pipeline({}, "items.product_id")


def test_line_revenue_groups_by_the_requested_field():
    stages = line_revenue_pipeline({}, "items.category_id")
    group = next(s["$group"] for s in stages if "$group" in s)
    assert group["_id"] == "$items.category_id"


def test_outstanding_only_counts_completed_payments():
    # 23 of 31 live payments are "pending" — recorded, not received. Counting
    # those as collected would understate what the business is owed.
    stages = outstanding_pipeline({"status": "ordered"})
    lookup = next(s["$lookup"] for s in stages if "$lookup" in s)
    assert lookup["from"] == "payments"
    conditions = lookup["pipeline"][0]["$match"]["$expr"]["$and"]
    assert {"$eq": ["$status", "completed"]} in conditions
    assert {"$eq": ["$quotation_id", "$$qid"]} in conditions


def test_every_metric_declares_its_source_collections():
    for metric in ("revenue", "orders", "aov", "outstanding", "brand_revenue", "product_revenue", "customer_ltv"):
        assert METRIC_SOURCES[metric], f"{metric} has no declared sources"


def test_outstanding_reads_both_quotations_and_payments():
    assert set(METRIC_SOURCES["outstanding"]) == {"quotations", "payments"}


def test_filter_signature_is_stable_for_equal_filters():
    a = AnalyticsFilter(floor_id="ground-floor", preset="this_month")
    b = AnalyticsFilter(floor_id="ground-floor", preset="this_month")
    assert filter_signature(a) == filter_signature(b)


def test_filter_signature_differs_when_any_field_differs():
    a = AnalyticsFilter(floor_id="ground-floor")
    b = AnalyticsFilter(floor_id="first-floor")
    assert filter_signature(a) != filter_signature(b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.analytics.metrics'`

- [ ] **Step 3: Write the module**

Create `backend/services/analytics/metrics.py`:

```python
"""Canonical KPI definitions — spec §4.3.

Each KPI is defined here exactly once. A workspace that needs Revenue calls
revenue_pipeline; it does not write its own $group. This is the structural
guarantee behind "one source of truth per KPI".
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict

from services.analytics.filters import AnalyticsFilter

# Which collections each metric reads — consumed by cache.cached so a write
# to any of them invalidates the metric automatically.
METRIC_SOURCES: dict[str, list[str]] = {
    "revenue": ["quotations"],
    "orders": ["quotations"],
    "aov": ["quotations"],
    "outstanding": ["quotations", "payments"],
    "conversion": ["quotations", "walkins"],
    "referral_revenue": ["quotations"],
    "brand_revenue": ["quotations", "products"],
    "product_revenue": ["quotations"],
    "customer_ltv": ["quotations"],
    "money_blocked": ["quotations", "payments", "customer_orders", "dispatches", "ready_batches", "purchase_orders"],
}


def filter_signature(f: AnalyticsFilter) -> str:
    """Short stable hash of a filter, for cache keys."""
    raw = "|".join(f"{k}={v}" for k, v in sorted(asdict(f).items()))
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def revenue_pipeline(match: dict) -> list[dict]:
    """Revenue, Orders, AOV and distinct customers in one pass.

    Revenue is the sum of grand_total over confirmed orders only, dated by
    ordered_at (enforced upstream by filters.date_field_for).
    """
    return [
        {"$match": match},
        {"$group": {
            "_id": None,
            "revenue": {"$sum": "$grand_total"},
            "orders": {"$sum": 1},
            "customers": {"$addToSet": "$customer_id"},
        }},
        {"$project": {
            "_id": 0,
            "revenue": {"$round": ["$revenue", 2]},
            "orders": 1,
            "customers": {"$size": "$customers"},
            "aov": {"$cond": [{"$gt": ["$orders", 0]}, {"$round": [{"$divide": ["$revenue", "$orders"]}, 2]}, 0]},
        }},
    ]


def line_revenue_pipeline(match: dict, group_by: str, limit: int = 50) -> list[dict]:
    """Revenue grouped by a line-level field.

    Sums items.net_amount — the denormalized post-discount total — so brand,
    product and category revenue reconcile to grand_total. Never
    qty x unit_price: that ignores the discount cascade.
    """
    return [
        {"$match": match},
        {"$unwind": "$items"},
        {"$group": {
            "_id": f"${group_by}",
            "revenue": {"$sum": "$items.net_amount"},
            "quantity": {"$sum": "$items.qty"},
            "orders": {"$addToSet": "$id"},
            "customers": {"$addToSet": "$customer_id"},
        }},
        {"$project": {
            "_id": 0,
            "key": "$_id",
            "revenue": {"$round": ["$revenue", 2]},
            "quantity": 1,
            "orders": {"$size": "$orders"},
            "customers": {"$size": "$customers"},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]


def outstanding_pipeline(match: dict) -> list[dict]:
    """Ordered value minus payments actually received.

    Only status="completed" payments count as collected. A "pending" payment
    is recorded, not received — treating it as collected would understate
    what the business is owed.
    """
    return [
        {"$match": match},
        {"$lookup": {
            "from": "payments",
            "let": {"qid": "$id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$quotation_id", "$$qid"]},
                    {"$eq": ["$status", "completed"]},
                ]}}},
                {"$group": {"_id": None, "paid": {"$sum": "$amount"}}},
            ],
            "as": "collected",
        }},
        {"$addFields": {"paid": {"$ifNull": [{"$first": "$collected.paid"}, 0]}}},
        {"$group": {
            "_id": None,
            "ordered": {"$sum": "$grand_total"},
            "collected": {"$sum": "$paid"},
        }},
        {"$project": {
            "_id": 0,
            "ordered": {"$round": ["$ordered", 2]},
            "collected": {"$round": ["$collected", 2]},
            "outstanding": {"$round": [{"$subtract": ["$ordered", "$collected"]}, 2]},
        }},
    ]
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit/test_analytics_metrics.py -v`
Expected: PASS — 10 passed

- [ ] **Step 5: Verify the pipelines against the live database**

Run:

```bash
cd backend && ./.venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, '.')
from db import db
from services.analytics.metrics import revenue_pipeline, line_revenue_pipeline, outstanding_pipeline
async def main():
    match = {'status': 'ordered'}
    print('KPIs      :', await db.quotations.aggregate(revenue_pipeline(match)).to_list(5))
    print('Outstanding:', await db.quotations.aggregate(outstanding_pipeline(match)).to_list(5))
    lines = await db.quotations.aggregate(line_revenue_pipeline(match, 'items.product_id', limit=1000)).to_list(1000)
    print('Line revenue total:', round(sum(r['revenue'] for r in lines), 2))
asyncio.run(main())
"
```

Expected: revenue `3977337.0` over 35 orders; **line revenue total must equal the revenue figure to within a rupee** — that reconciliation is the whole point of Tasks 1-3. If it does not match, stop: either the backfill did not run or a discount path is unaccounted for.

- [ ] **Step 6: Commit**

```bash
git add backend/services/analytics/metrics.py backend/tests/unit/test_analytics_metrics.py
git commit -m "Add the canonical KPI registry

Revenue, orders, AOV, outstanding and line-level revenue defined once.
Line revenue sums items.net_amount so brand and product revenue
reconcile to grand_total instead of drifting.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 13: Chart foundation — `react-native-svg`, `ChartFrame`, `Sparkline`

**Files:**
- Modify: `frontend/package.json` (via `expo install`)
- Create: `frontend/src/components/charts/ChartFrame.tsx`
- Create: `frontend/src/components/charts/Sparkline.tsx`

**Interfaces:**
- Produces:
  - `ChartState = "ready" | "loading" | "empty" | "no_prior_period" | "insufficient_history"`
  - `<ChartFrame height state stateLabel testID>{(width) => ReactNode}</ChartFrame>`
  - `<Sparkline points={number[]} height? state? testID? />`

- [ ] **Step 1: Install the dependency**

Run: `cd frontend && npx expo install react-native-svg`
Expected: `react-native-svg` added to `package.json` at the version Expo pins for this SDK. Do **not** use `npm install react-native-svg` — that can pick a version incompatible with the installed Expo SDK.

- [ ] **Step 2: Verify it resolves on web**

Run: `cd frontend && node -e "console.log(require('./package.json').dependencies['react-native-svg'])"`
Expected: a version string is printed.

- [ ] **Step 3: Write `ChartFrame`**

Create `frontend/src/components/charts/ChartFrame.tsx`:

```tsx
import { ReactNode, useState } from "react";
import { LayoutChangeEvent, Text, View } from "react-native";

import { colors, spacing, type } from "@/src/theme/tokens";

/** Why a chart is not showing data. Mirrors the backend's history_state so
 *  the UI never has to invent a reason — or a number. */
export type ChartState = "ready" | "loading" | "empty" | "no_prior_period" | "insufficient_history";

const STATE_COPY: Record<Exclude<ChartState, "ready">, string> = {
  loading: "Loading…",
  empty: "No data in this period",
  no_prior_period: "No previous period available.",
  insufficient_history: "Historical comparison available after more business history is collected.",
};

type Props = {
  height: number;
  state?: ChartState;
  stateLabel?: string;
  testID?: string;
  children: (width: number) => ReactNode;
};

/**
 * The one frame every BuildCon chart renders inside.
 *
 * Owns responsive width measurement and every non-data state, so an
 * individual chart only ever draws marks. Adding a new chart type must not
 * require changing this file.
 *
 * Width comes from onLayout rather than useWindowDimensions because charts
 * sit inside cards and grids whose width is not the window's.
 */
export function ChartFrame({ height, state = "ready", stateLabel, testID, children }: Props) {
  const [width, setWidth] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  return (
    <View testID={testID} onLayout={onLayout} style={{ height, justifyContent: "center" }}>
      {state !== "ready" ? (
        <View style={{ alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md }}>
          <Text style={[type.caption, { color: colors.textMuted, textAlign: "center" }]}>
            {stateLabel || STATE_COPY[state]}
          </Text>
        </View>
      ) : width > 0 ? (
        children(width)
      ) : null}
    </View>
  );
}
```

- [ ] **Step 4: Write `Sparkline`**

Create `frontend/src/components/charts/Sparkline.tsx`:

```tsx
import Svg, { Polyline } from "react-native-svg";

import { colors } from "@/src/theme/tokens";

import { ChartFrame, type ChartState } from "./ChartFrame";

type Props = {
  points: number[];
  height?: number;
  state?: ChartState;
  testID?: string;
};

/**
 * The KPI-card trend line. Deliberately axis-less and label-less: it shows
 * shape, and the card's value shows magnitude.
 *
 * A single data point cannot describe a trend, so it renders the empty state
 * rather than a misleading flat line — the same honesty rule the backend's
 * history_state follows.
 */
export function Sparkline({ points, height = 36, state, testID }: Props) {
  const resolved: ChartState = state ?? (points.length < 2 ? "empty" : "ready");

  return (
    <ChartFrame height={height} state={resolved} testID={testID}>
      {(width) => {
        const min = Math.min(...points);
        const max = Math.max(...points);
        const span = max - min || 1;
        const stepX = width / (points.length - 1);
        const coords = points
          .map((value, i) => `${i * stepX},${height - ((value - min) / span) * height}`)
          .join(" ");

        return (
          <Svg width={width} height={height}>
            <Polyline points={coords} fill="none" stroke={colors.brand} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          </Svg>
        );
      }}
    </ChartFrame>
  );
}
```

- [ ] **Step 5: Confirm the token names actually exist**

Run: `cd frontend && grep -nE "textMuted|brand" src/theme/tokens.ts | head`
Expected: both `colors.brand` and `colors.textMuted` are present. If `textMuted` is named differently in this codebase, use the real name — do not add a new token.

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors. One pre-existing unrelated error in `TileOrderCard.tsx:107` is known and predates this work — confirm it is the only failure, and that it also appears on a clean checkout before treating it as pre-existing.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/charts/
git commit -m "Add the BuildCon chart foundation

react-native-svg plus ChartFrame, which owns responsive sizing and every
non-data state so individual charts only draw marks. Sparkline renders an
empty state for a single point rather than a misleading flat line.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 14: Grouped workspace shell

The navigation from spec §16.2 — five groups plus More — and the layout every workspace renders inside. Workspaces themselves are Phase 1+; this task ships the shell and the Executive route only.

**Files:**
- Create: `frontend/src/components/analytics/WorkspaceSwitcher.tsx`
- Create: `frontend/app/(admin)/sales-data/_layout.tsx`

**Interfaces:**
- Produces:
  - `WORKSPACE_GROUPS: { key, label, members: { label, route }[] }[]`
  - `<WorkspaceSwitcher />`

- [ ] **Step 1: Write the switcher**

Create `frontend/src/components/analytics/WorkspaceSwitcher.tsx`:

```tsx
import { usePathname, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { colors, radii, spacing, type } from "@/src/theme/tokens";

type Member = { label: string; route: string };
type Group = { key: string; label: string; members: Member[] };

/**
 * Navigation grouped by the question the owner is asking, not by engineering
 * boundary (spec §16.2). Routes and backend services are unchanged by this
 * grouping — it is presentation only.
 *
 * Each group opens to its first member, so a click is never spent on a menu.
 */
export const WORKSPACE_GROUPS: Group[] = [
  { key: "overview", label: "Overview", members: [
    { label: "Executive", route: "/(admin)/sales-data/executive" },
    { label: "Today's Priorities", route: "/(admin)/sales-data/today" },
  ] },
  { key: "money", label: "Money", members: [
    { label: "Revenue", route: "/(admin)/sales-data/sales" },
    { label: "Collections", route: "/(admin)/sales-data/collections" },
    { label: "Forecasting", route: "/(admin)/sales-data/forecasting" },
  ] },
  { key: "customers", label: "Customers", members: [
    { label: "Customers", route: "/(admin)/sales-data/customers" },
    { label: "Architects", route: "/(admin)/sales-data/referrals/architects" },
    { label: "Interior Designers", route: "/(admin)/sales-data/referrals/interior-designers" },
    { label: "Relationships", route: "/(admin)/sales-data/relationships" },
  ] },
  { key: "products", label: "Products", members: [
    { label: "Products", route: "/(admin)/sales-data/products" },
    { label: "Brands", route: "/(admin)/sales-data/brands" },
    { label: "Suppliers", route: "/(admin)/sales-data/suppliers" },
  ] },
  { key: "operations", label: "Operations", members: [
    { label: "Operations", route: "/(admin)/sales-data/operations" },
  ] },
];

export function WorkspaceSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  const activeGroup = WORKSPACE_GROUPS.find((g) => g.members.some((m) => pathname.startsWith(m.route.replace("/(admin)", ""))));

  return (
    <View style={{ gap: spacing.xs }}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
        {WORKSPACE_GROUPS.map((group) => {
          const isActive = activeGroup?.key === group.key;
          return (
            <Pressable
              key={group.key}
              testID={`workspace-group-${group.key}`}
              accessibilityLabel={group.label}
              onPress={() => {
                setOpenGroup(group.members.length > 1 ? (openGroup === group.key ? null : group.key) : null);
                router.push(group.members[0].route as never);
              }}
              style={{
                minHeight: 44,
                justifyContent: "center",
                paddingHorizontal: spacing.md,
                borderRadius: radii.pill,
                backgroundColor: isActive ? colors.brand : "transparent",
              }}
            >
              <Text style={[type.bodyStrong, { color: isActive ? colors.onBrand : colors.text }]}>{group.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {openGroup ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs }}>
          {WORKSPACE_GROUPS.find((g) => g.key === openGroup)!.members.map((member) => (
            <Pressable
              key={member.route}
              testID={`workspace-member-${member.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
              accessibilityLabel={member.label}
              onPress={() => router.push(member.route as never)}
              style={{ minHeight: 44, justifyContent: "center", paddingHorizontal: spacing.md }}
            >
              <Text style={type.body}>{member.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      ) : null}
    </View>
  );
}
```

Note: the outer `Pressable` sets `accessibilityLabel` but deliberately **not** `accessibilityRole="button"` — that combination on a row containing other pressables is what produced nested `<button>` elements in the 2026-07-24 `QueueRow` bug.

- [ ] **Step 2: Write the layout**

Create `frontend/app/(admin)/sales-data/_layout.tsx`:

```tsx
import { Slot } from "expo-router";
import { View } from "react-native";

import { WorkspaceSwitcher } from "@/src/components/analytics/WorkspaceSwitcher";
import { spacing } from "@/src/theme/tokens";

/**
 * Shell shared by every Sales Data workspace. The switcher lives here so a
 * workspace never renders its own navigation and they cannot drift apart.
 */
export default function SalesDataLayout() {
  return (
    <View style={{ flex: 1, gap: spacing.md }}>
      <WorkspaceSwitcher />
      <View style={{ flex: 1 }}>
        <Slot />
      </View>
    </View>
  );
}
```

- [ ] **Step 3: Confirm the token names exist**

Run: `cd frontend && grep -nE "onBrand|pill|xs:" src/theme/tokens.ts | head`
Expected: `colors.onBrand`, `radii.pill` and `spacing.xs` are present. If any is named differently here, use the existing name rather than adding a token.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors beyond the known `TileOrderCard.tsx:107` one.

- [ ] **Step 5: Verify live in the browser**

Start the dev server via `preview_start` (`.claude/launch.json` at the outer working-directory root, `cwd: forge2.0/frontend`), log in, and open `/sales-data/executive`.

Confirm: the five group chips render; clicking **Money** navigates to `/sales-data/sales` and reveals its members; the active group is highlighted; every chip measures at least 44px tall; and the console has no errors — in particular no "cannot contain a nested button" warning.

Routes that do not exist yet (Collections, Suppliers, Relationships, Today) will 404 — that is expected at Phase 0 and they are built in later phases.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/analytics/ "frontend/app/(admin)/sales-data/_layout.tsx"
git commit -m "Add the grouped Sales Data workspace shell

Navigation grouped by business question per spec §16.2. The switcher
lives in the shared layout so no workspace renders its own nav.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 15: Phase 0 verification

No new code — this proves the foundation before Phase 1 builds on it.

- [ ] **Step 1: Full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/unit -v`
Expected: all pass. This plan adds 72 tests (Task 1: 10, Task 2: 4, Task 3: 3, Task 4: 4, Task 8: 5, Task 9: 12, Task 10: 16, Task 11: 8, Task 12: 10), so the count should be the pre-plan baseline plus 72. **Record the real baseline before Task 1 rather than trusting 197** — the working tree carries uncommitted edits from earlier sessions, and the Tile Orders ledger notes 2 pre-existing unrelated failures. Zero previously-passing tests may break.

- [ ] **Step 2: Reconciliation against live data**

Run:

```bash
cd backend && ./.venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, '.')
from db import db
from services.analytics.metrics import revenue_pipeline, line_revenue_pipeline
async def main():
    match = {'status': 'ordered'}
    kpi = (await db.quotations.aggregate(revenue_pipeline(match)).to_list(1))[0]
    by_product = await db.quotations.aggregate(line_revenue_pipeline(match, 'items.product_id', limit=10000)).to_list(10000)
    by_category = await db.quotations.aggregate(line_revenue_pipeline(match, 'items.category_id', limit=10000)).to_list(10000)
    p, c = sum(r['revenue'] for r in by_product), sum(r['revenue'] for r in by_category)
    print('revenue   :', kpi['revenue'])
    print('by product:', round(p, 2))
    print('by category:', round(c, 2))
    print('RECONCILES:', abs(p - kpi['revenue']) < 1 and abs(c - kpi['revenue']) < 1)
asyncio.run(main())
"
```

Expected: `RECONCILES: True`. This is the single most important check in Phase 0 — if product and category revenue do not both sum to total revenue, every workspace built on this layer will show contradictory numbers.

- [ ] **Step 3: Floor-scope probe**

Verify `build_match` never returns an unscoped query for a restricted caller:

```bash
cd backend && ./.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from services.analytics.filters import AnalyticsFilter, build_match, FloorAccessError
w = ('2026-07-01T00:00:00+00:00', '2026-07-31T23:59:59+00:00')
print('unrestricted, all :', build_match(AnalyticsFilter(floor_id='all'), None, w).get('floor_id'))
print('restricted,   all :', build_match(AnalyticsFilter(floor_id='all'), ['ground-floor'], w).get('floor_id'))
try:
    build_match(AnalyticsFilter(floor_id='first-floor'), ['ground-floor'], w)
    print('LEAK: cross-floor access was allowed')
except FloorAccessError:
    print('cross-floor refused: ok')
"
```

Expected: unrestricted `None`; restricted `{'\$in': ['ground-floor']}`; `cross-floor refused: ok`.

- [ ] **Step 4: App boots**

Run: `cd backend && ./.venv/bin/python -c "import server; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Report**

Summarize for the user: tests passing, reconciliation result, migrations applied, and anything deferred. Phase 0 is complete only when Step 2 prints `RECONCILES: True`.

---

## Self-Review

**Spec coverage** — Phase 0 in spec §17 lists: `ordered_at` (Task 4, 5), `items.net_amount` (Tasks 1, 2, 3), index migration (Task 6), owner targets in Settings (Task 8), `services/analytics/` skeleton with `filters`/`periods`/`metrics`/`cache` (Tasks 9, 10, 11, 12), chart kit foundation (Task 13), grouped workspace shell (Task 14). All covered. Task 7 (running migrations) and Task 15 (verification) are execution steps the spec implies rather than names.

**Deliberately deferred to Phase 1**, since nothing in Phase 0 consumes them yet: the cache `bump()` call sites in `services/domain_outbox.py` (the function exists and is tested; wiring it to writes belongs with the first workspace that caches), and the remaining domain modules (`revenue.py`, `attention.py`, etc.) which are Phase 1 content, not skeleton.

**Placeholder scan** — the initial import guard in Task 3 Step 1 is replaced inline by the real file content in the same step; no other TODOs, no "similar to Task N", every code step carries complete code.

**Type consistency** — `net_amounts` / `stamp_net_amounts` / `per_line_net_amounts` signatures match between Tasks 1, 2, 3. `build_match(f, accessible_floors, window, product_ids)` is identical in Tasks 9, 12, 15. `ChartState` is defined in `ChartFrame` and imported by `Sparkline` in Task 13. `WORKSPACE_GROUPS` shape matches its use in Task 14.

**One risk flagged inline rather than assumed away:** Task 11 Step 4 does not assume `pytest-asyncio` is configured — it tells the implementer to match whatever the existing async tests use.
