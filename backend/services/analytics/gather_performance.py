"""The only place the Performance workspace (spec §7 Workspace 2) reads Mongo.

Same rule as Phase 1's gather.py: every read goes through build_match, so
floor scoping and the ordered_at-vs-created_at date-field choice exist in
exactly one place. No clause here ever writes {"floor_id": ...} by hand.

Live data reality (docs/superpowers/plans/2026-08-01-executive-os-phase-2.md,
probed 2026-08-01/08): Quotation has no approved_at field and no timestamp
records a selection converting into a quotation, so three of the funnel's
seven stage-to-stage transitions — selections->quotations, quotations-
>approved, approved->confirmed_orders — cannot honestly report a duration.
gather_funnel returns None for those three, never a fabricated estimate
derived from updated_at (updated_at re-stamps on every edit, so it cannot
date an event — the same reason Phase 0 banned it from revenue entirely).

The other four transitions DO have real timestamp pairs, joined the same way
Tile Orders logistics joins them elsewhere in this codebase: an ordered
Quotation -> its TileCustomerOrder (via TileCustomerOrder.quotation_id) ->
that order's TileReadyBatch/TileDispatch rows (via customer_order_id) ->
a Payment (via quotation_id, direct).
"""
from __future__ import annotations

from datetime import datetime

from services.analytics.filters import AnalyticsFilter, build_match
from services.analytics.gather import collected_by_quotation
from services.analytics.metrics import line_revenue_pipeline, revenue_pipeline
from services.analytics.performance import STAGE_ORDER
from services.analytics.periods import buckets

_MAX_ROWS = 5000


def _days_between(earlier: str | None, later: str | None) -> float | None:
    """Fractional days from `earlier` to `later`, or None if either is
    missing/unparseable/inverted. Never negative — an out-of-order pair
    means the join found the wrong record, not a real negative duration."""
    if not earlier or not later:
        return None
    try:
        delta = (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds() / 86400
    except (TypeError, ValueError):
        return None
    return delta if delta >= 0 else None


async def gather_revenue_trend(db, f: AnalyticsFilter, accessible_floors, window, granularity) -> list[dict]:
    """Bucketed revenue, one revenue_pipeline call per bucket — the same KPI
    definition the top-line Revenue card uses, never a re-derived $group."""
    result: list[dict] = []
    for period in buckets(window[0], window[1], granularity):
        match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="ordered"), accessible_floors, (period.start, period.end))
        rows = await db.quotations.aggregate(revenue_pipeline(match)).to_list(None)
        result.append({"bucket": period.label, "revenue": rows[0]["revenue"] if rows else 0.0})
    return result


async def _quotation_person_stats(db, f: AnalyticsFilter, accessible_floors, window) -> dict[str, dict]:
    """Revenue + orders per created_by, for ordered quotations in `window`."""
    match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="ordered"), accessible_floors, window)
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$created_by",
            "name": {"$first": "$created_by_name"},
            "revenue": {"$sum": "$grand_total"},
            "orders": {"$sum": 1},
            "last_activity_at": {"$max": "$created_at"},
        }},
    ]
    rows = await db.quotations.aggregate(pipeline).to_list(None)
    return {r["_id"]: r for r in rows if r.get("_id")}


async def _walkin_person_stats(db, f: AnalyticsFilter, accessible_floors, window) -> dict[str, dict]:
    """Walk-ins handled per salesperson, in `window`."""
    match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, window)
    match["is_deleted"] = {"$ne": True}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$salesperson_id",
            "name": {"$first": "$salesperson_name"},
            "walkins_handled": {"$sum": 1},
            "last_activity_at": {"$max": "$visited_at"},
        }},
    ]
    rows = await db.walkins.aggregate(pipeline).to_list(None)
    return {r["_id"]: r for r in rows if r.get("_id")}


async def _followup_last_contact(db, f: AnalyticsFilter, accessible_floors) -> dict[str, str]:
    """Last-contacted timestamp per assignee — un-windowed, like Phase 1's
    _salespeople(): "who has gone quiet" is about recency, not the report
    period, so an open-ended followup query is the honest one."""
    match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, (None, None))
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$assigned_to", "last_contacted_at": {"$max": "$last_contacted_at"}}},
    ]
    rows = await db.followups.aggregate(pipeline).to_list(None)
    return {r["_id"]: r["last_contacted_at"] for r in rows if r.get("_id") and r.get("last_contacted_at")}


async def gather_salespeople(
    db, f: AnalyticsFilter, accessible_floors, window, previous_window,
) -> tuple[list[dict], dict[str, float], dict[str, int]]:
    """Current per-salesperson rows, plus the previous period's revenue and
    rank by id — three small aggregations (quotations, walkins, followups),
    joined on person id, not a fourth full-collection scan."""
    revenue_map = await _quotation_person_stats(db, f, accessible_floors, window)
    walkin_map = await _walkin_person_stats(db, f, accessible_floors, window)
    followup_map = await _followup_last_contact(db, f, accessible_floors)

    person_ids = {pid for pid in (set(revenue_map) | set(walkin_map) | set(followup_map)) if pid}
    current: list[dict] = []
    for pid in person_ids:
        rev = revenue_map.get(pid, {})
        walk = walkin_map.get(pid, {})
        candidates = [rev.get("last_activity_at"), walk.get("last_activity_at"), followup_map.get(pid)]
        last_activity_at = max((c for c in candidates if c), default=None)
        current.append({
            "salesperson_id": pid,
            "name": rev.get("name") or walk.get("name") or "Unknown",
            "revenue": float(rev.get("revenue") or 0),
            "orders": int(rev.get("orders") or 0),
            "walkins_handled": int(walk.get("walkins_handled") or 0),
            "last_activity_at": last_activity_at,
        })

    prev_map = await _quotation_person_stats(db, f, accessible_floors, previous_window)
    prev_revenue = {pid: float(row.get("revenue") or 0) for pid, row in prev_map.items() if pid}
    ranked = sorted(prev_revenue.items(), key=lambda kv: -kv[1])
    prev_rank = {pid: rank for rank, (pid, _) in enumerate(ranked, start=1)}

    return current, prev_revenue, prev_rank


async def _selection_durations(db, f: AnalyticsFilter, accessible_floors, window) -> list[float]:
    """walkins->selections: WalkIn.visited_at -> the selection quotation's
    created_at, joined via WalkIn.selection_quotation_id — the one real
    timestamp pair the "Live data reality" note confirms for this leg."""
    walkin_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, window)
    walkin_match["is_deleted"] = {"$ne": True}
    walkin_match["selection_quotation_id"] = {"$ne": None}
    walkins = await db.walkins.find(walkin_match, {"_id": 0, "visited_at": 1, "selection_quotation_id": 1}).to_list(_MAX_ROWS)
    selection_ids = [w["selection_quotation_id"] for w in walkins if w.get("selection_quotation_id")]
    if not selection_ids:
        return []

    selection_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, (None, None))
    selection_match["id"] = {"$in": selection_ids}
    selections = await db.quotations.find(selection_match, {"_id": 0, "id": 1, "created_at": 1}).to_list(_MAX_ROWS)
    created_at_by_id = {s["id"]: s.get("created_at") for s in selections if s.get("id")}

    durations: list[float] = []
    for w in walkins:
        delta = _days_between(w.get("visited_at"), created_at_by_id.get(w.get("selection_quotation_id")))
        if delta is not None:
            durations.append(delta)
    return durations


async def _logistics_durations(db, f: AnalyticsFilter, accessible_floors, window) -> dict[str, list[float]]:
    """confirmed_orders->release, release->dispatch, dispatch->payment.

    Joined through TileCustomerOrder: an ordered Quotation's id resolves to
    a TileCustomerOrder via .quotation_id, whose id in turn is
    TileReadyBatch/TileDispatch's .customer_order_id. Payment joins the
    Quotation directly via .quotation_id. Release uses the earliest
    TileReadyBatch.created_at for that order (the same field Phase 1's
    gather.py._ready_items already treats as "ready_at"); dispatch uses the
    earliest TileDispatch.created_at; payment uses the earliest completed
    Payment's paid_at (falling back to created_at, which is what paid_at
    itself defaults to when unset).
    """
    ordered_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="ordered"), accessible_floors, window)
    orders = await db.quotations.find(ordered_match, {"_id": 0, "id": 1, "ordered_at": 1}).to_list(_MAX_ROWS)
    order_ids = [o["id"] for o in orders if o.get("id")]
    if not order_ids:
        return {"release": [], "dispatch": [], "payments": []}

    co_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, (None, None))
    co_match["quotation_id"] = {"$in": order_ids}
    customer_orders = await db.customer_orders.find(co_match, {"_id": 0, "id": 1, "quotation_id": 1}).to_list(_MAX_ROWS)
    co_id_by_quotation = {c["quotation_id"]: c["id"] for c in customer_orders if c.get("quotation_id") and c.get("id")}
    co_ids = list(co_id_by_quotation.values())

    earliest_release: dict[str, str] = {}
    earliest_dispatch: dict[str, str] = {}
    if co_ids:
        rb_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, (None, None))
        rb_match["customer_order_id"] = {"$in": co_ids}
        rb_match["is_deleted"] = {"$ne": True}
        async for b in db.ready_batches.find(rb_match, {"_id": 0, "customer_order_id": 1, "created_at": 1}):
            cid, created = b.get("customer_order_id"), b.get("created_at")
            if cid and created and (cid not in earliest_release or created < earliest_release[cid]):
                earliest_release[cid] = created

        d_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, (None, None))
        d_match["customer_order_id"] = {"$in": co_ids}
        d_match["is_deleted"] = {"$ne": True}
        async for d in db.dispatches.find(d_match, {"_id": 0, "customer_order_id": 1, "created_at": 1}):
            cid, created = d.get("customer_order_id"), d.get("created_at")
            if cid and created and (cid not in earliest_dispatch or created < earliest_dispatch[cid]):
                earliest_dispatch[cid] = created

    payment_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="completed"), accessible_floors, (None, None))
    payment_match["quotation_id"] = {"$in": order_ids}
    earliest_payment: dict[str, str] = {}
    async for p in db.payments.find(payment_match, {"_id": 0, "quotation_id": 1, "paid_at": 1, "created_at": 1}):
        qid = p.get("quotation_id")
        paid_at = p.get("paid_at") or p.get("created_at")
        if qid and paid_at and (qid not in earliest_payment or paid_at < earliest_payment[qid]):
            earliest_payment[qid] = paid_at

    release_durations: list[float] = []
    dispatch_durations: list[float] = []
    payment_durations: list[float] = []
    for o in orders:
        co_id = co_id_by_quotation.get(o.get("id"))
        released_at = earliest_release.get(co_id) if co_id else None
        dispatched_at = earliest_dispatch.get(co_id) if co_id else None
        paid_at = earliest_payment.get(o.get("id"))

        d1 = _days_between(o.get("ordered_at"), released_at)
        if d1 is not None:
            release_durations.append(d1)
        d2 = _days_between(released_at, dispatched_at)
        if d2 is not None:
            dispatch_durations.append(d2)
        d3 = _days_between(dispatched_at, paid_at)
        if d3 is not None:
            payment_durations.append(d3)

    return {"release": release_durations, "dispatch": dispatch_durations, "payments": payment_durations}


async def gather_funnel(
    db, f: AnalyticsFilter, accessible_floors, window,
) -> tuple[dict[str, int], dict[str, list[float] | None], float]:
    """Counts per performance.STAGE_ORDER key, stage_durations (three
    transitions explicitly None — see module docstring), and avg_order_value
    for the same window, matching the spec's exact denominators table."""
    counts: dict[str, int] = dict.fromkeys(STAGE_ORDER, 0)

    walkin_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, window)
    walkin_match["is_deleted"] = {"$ne": True}
    counts["walkins"] = await db.walkins.count_documents(walkin_match)

    selection_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, window)
    selection_match["doc_type"] = "tiles_selection"
    counts["selections"] = await db.quotations.count_documents(selection_match)

    quotation_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, window)
    quotation_match["doc_type"] = {"$in": ["standard", "tiles_quotation"]}
    quotation_match["status"] = {"$nin": ["rejected", "lost"]}
    counts["quotations"] = await db.quotations.count_documents(quotation_match)

    approved_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="approved"), accessible_floors, window)
    counts["approved"] = await db.quotations.count_documents(approved_match)

    ordered_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="ordered"), accessible_floors, window)
    counts["confirmed_orders"] = await db.quotations.count_documents(ordered_match)

    release_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, window)
    release_match["is_deleted"] = {"$ne": True}
    counts["release"] = await db.ready_batches.count_documents(release_match)

    dispatch_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, window)
    dispatch_match["is_deleted"] = {"$ne": True}
    counts["dispatch"] = await db.dispatches.count_documents(dispatch_match)

    payment_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="completed"), accessible_floors, window)
    counts["payments"] = await db.payments.count_documents(payment_match)

    revenue_rows = await db.quotations.aggregate(revenue_pipeline(ordered_match)).to_list(None)
    avg_order_value = float(revenue_rows[0]["aov"]) if revenue_rows else 0.0

    logistics = await _logistics_durations(db, f, accessible_floors, window)
    stage_durations: dict[str, list[float] | None] = {
        "walkins": [],  # no "previous" stage to measure from
        "selections": await _selection_durations(db, f, accessible_floors, window),
        # No timestamp anywhere records a selection converting into a
        # quotation — Live data reality (2026-08-01/08). None, not an
        # estimate derived from updated_at.
        "quotations": None,
        # Quotation has no approved_at field, only approved_by. Same rule.
        "approved": None,
        # No approval->order timestamp beyond ordered_at itself, which the
        # funnel already uses to date "confirmed_orders". Same rule.
        "confirmed_orders": None,
        "release": logistics["release"],
        "dispatch": logistics["dispatch"],
        "payments": logistics["payments"],
    }

    return counts, stage_durations, avg_order_value


async def gather_category_revenue(db, f: AnalyticsFilter, accessible_floors, window) -> tuple[list[dict], dict[str, str]]:
    """Revenue by items.category_id — line_revenue_pipeline's own shape,
    grouped on the category field instead of the product default — plus the
    id->name lookup from db.categories, floor-scoped since categories are
    floor-owned (Category.floor_id)."""
    match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="ordered"), accessible_floors, window)
    rows = await db.quotations.aggregate(line_revenue_pipeline(match, group_by="items.category_id")).to_list(None)
    raw = [{"category_id": r.get("key"), "revenue": r.get("revenue"), "qty": r.get("quantity")} for r in rows]

    category_match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="any"), accessible_floors, (None, None))
    categories = await db.categories.find(category_match, {"_id": 0, "id": 1, "name": 1}).to_list(_MAX_ROWS)
    names = {c["id"]: c["name"] for c in categories if c.get("id")}

    return raw, names


async def gather_collections_orders(db, f: AnalyticsFilter, accessible_floors, window) -> list[dict]:
    """Ordered quotations with outstanding money: customer, order amount, and
    collected so far (reusing Phase 1's collected_by_quotation, which counts
    only status="completed" payments)."""
    match = build_match(AnalyticsFilter(floor_id=f.floor_id, status="ordered"), accessible_floors, window)
    orders = await db.quotations.find(
        match, {"_id": 0, "id": 1, "customer_id": 1, "customer_name": 1, "ordered_at": 1, "grand_total": 1},
    ).to_list(None)
    paid = await collected_by_quotation(db, [o["id"] for o in orders])
    return [{**o, "collected": paid.get(o["id"], 0.0)} for o in orders]
