"""Read-path floor-isolation probe.

Mints a real staff session against a running backend and hits every
floor-scoped read three ways -- no X-Floor-Id, first-floor, ground-floor --
asserting the set of floor_id values actually present in each response.

This catches ambient-state leaks that clicking through the UI hides: a query
that silently runs unfiltered still *renders* fine in a browser.

Usage:
    FORGE_PROBE_PASSWORD=... ./.venv/bin/python -m scripts.probe_floor_isolation
    FORGE_PROBE_PASSWORD=... ./.venv/bin/python -m scripts.probe_floor_isolation --base-url http://127.0.0.1:8010

Exit code: 0–N = number of endpoints that failed isolation (usable as a CI gate),
64 = usage error (password not configured).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

SANITARY = "first-floor"
GROUND = "ground-floor"

# (label, path, key holding the row list, collection to resolve ids against)
#
# The 4th field exists because some endpoints project floor_id OUT of their
# response -- /api/tile-orders/customer-orders is one, confirmed 2026-08-02.
# For those, the response body carries no evidence either way, and a probe
# that inspected only the payload would report a cheerful "ok" while proving
# nothing. When a collection is given, ids from the response are resolved
# against Mongo and their stored floor_id is what gets asserted.
ENDPOINTS: list[tuple[str, str, str | None, str | None]] = [
    ("Quotations", "/api/quotations", None, None),
    ("Customers", "/api/customers", None, None),
    ("Purchase orders", "/api/purchase-orders", None, None),
    ("Payments", "/api/payments", None, None),
    ("Follow-ups", "/api/followups", None, None),
    ("Walk-ins", "/api/walkins", None, None),
    ("Activity feed", "/api/activity", None, None),
    ("Notifications", "/api/notifications", None, None),
    ("Suppliers", "/api/suppliers", None, None),
    ("Tile orders", "/api/tile-orders/customer-orders", "orders", "customer_orders"),
]

# Tile Orders is pinned to Ground Floor unconditionally by tiles_floor_query(),
# regardless of the header sent. It is expected to ignore the header, so a
# first-floor request legitimately returns ground-floor rows.
HEADER_INDEPENDENT = {"Tile orders"}

# (endpoint, floor) pairs where zero rows is the correct, verified answer.
# Sanitary Bathroom genuinely has no walk-ins recorded -- confirmed against
# live data 2026-08-02. Every other scoped-zero is treated as a broken query,
# because an empty result and a correctly-isolated result are indistinguishable
# from the response alone.
KNOWN_EMPTY: set[tuple[str, str]] = {("Walk-ins", "first_floor")}


def _request(url: str, token: str | None, floor: str | None) -> object:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if floor:
        req.add_header("X-Floor-Id", floor)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def login(base_url: str, email: str, password: str) -> str:
    req = urllib.request.Request(
        f"{base_url}/api/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["access_token"]


def _rows(body: object, list_key: str | None) -> list[dict]:
    rows = body.get(list_key, []) if list_key and isinstance(body, dict) else body
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


async def floor_set(body: object, list_key: str | None, collection: str | None) -> tuple[set[str], int]:
    """Return (distinct floor_id values, row count).

    The count matters: an endpoint returning [] has an empty floor set and so
    trivially "does not leak". Empty is not proof of isolation -- it is
    equally consistent with a broken query. The count is what distinguishes
    the two, and is what gets compared against the release report's figures.

    When `collection` is set, the endpoint does not serialize floor_id, so
    the returned ids are resolved against Mongo instead. A response body that
    simply omits the field must never be read as evidence of isolation.
    """
    rows = _rows(body, list_key)
    if collection:
        return await _floors_from_db(collection, [r["id"] for r in rows if r.get("id")]), len(rows)
    return {str(r.get("floor_id")) for r in rows}, len(rows)


async def _floors_from_db(collection: str, ids: list[str]) -> set[str]:
    """Resolve stored floor_id for the given ids.

    Must run inside the caller's single event loop. motor binds its client to
    the running loop, so one asyncio.run() per lookup closes the loop out from
    under the next one ("RuntimeError: Event loop is closed") -- the whole
    probe therefore runs in one loop, entered once in main().
    """
    if not ids:
        return set()

    from db import db  # backend/db.py -- only imported on the DB-verify path

    found = await db[collection].find(
        {"id": {"$in": ids}}, {"_id": 0, "floor_id": 1},
    ).to_list(len(ids))
    return {str(d.get("floor_id")) for d in found}


async def probe(base_url: str, email: str, password: str) -> tuple[list[dict], int]:
    token = login(base_url, email, password)
    rows: list[dict] = []
    failures = 0

    for label, path, list_key, collection in ENDPOINTS:
        result: dict[str, object] = {"endpoint": label}
        for name, floor in (("unscoped", None), ("first_floor", SANITARY), ("ground_floor", GROUND)):
            try:
                seen, count = await floor_set(
                    _request(f"{base_url}{path}", token, floor), list_key, collection,
                )
            except urllib.error.HTTPError as exc:
                seen, count = {f"<HTTP {exc.code}>"}, -1
            except urllib.error.URLError as exc:
                # Backend unreachable mid-run -- record it as a failure row
                # instead of letting the traceback kill the whole probe.
                seen, count = {f"<URLError {exc.reason}>"}, -1
            result[name] = seen
            result[f"{name}_count"] = count

        problems: list[str] = []

        # A scoped request returning 0 rows while the unscoped request
        # returned >0 rows is a failure, except where a zero is legitimately
        # expected (KNOWN_EMPTY). An empty floor set is otherwise
        # indistinguishable from a broken/unfiltered query, so it must never
        # pass silently as "ok" -- see floor_set()'s docstring.
        unscoped_count = result["unscoped_count"]
        if isinstance(unscoped_count, int) and unscoped_count > 0:
            for name in ("first_floor", "ground_floor"):
                if result[f"{name}_count"] == 0 and (label, name) not in KNOWN_EMPTY:
                    problems.append(
                        f"{name} returned 0 rows (unscoped had {unscoped_count}) -- query may be broken"
                    )

        if label not in HEADER_INDEPENDENT:
            for name, expected in (("first_floor", SANITARY), ("ground_floor", GROUND)):
                leaked = result[name] - {expected}  # type: ignore[operator]
                if leaked:
                    problems.append(f"{name} leaked {sorted(leaked)}")
        else:
            # Tile Orders is pinned to Ground Floor regardless of header, so
            # ALL THREE variants must resolve to exactly {GROUND} -- checking
            # only ground_floor (as before) would miss a leak that appears
            # solely under X-Floor-Id: first-floor. Empty sets are ignored
            # here; the KNOWN_EMPTY check above already turns an unexpected
            # empty into its own failure.
            for name in ("unscoped", "first_floor", "ground_floor"):
                seen = result[name]
                if seen and seen != {GROUND}:  # type: ignore[operator]
                    problems.append(f"{name} returned {sorted(seen)} (expected pinned {{'{GROUND}'}})")  # type: ignore[arg-type]

        result["verdict"] = ("LEAK: " + "; ".join(problems)) if problems else "ok"
        if problems:
            failures += 1
        rows.append(result)

    return rows, failures


# ---------------------------------------------------------------------------
# Write-path probing
# ---------------------------------------------------------------------------
#
# The read probe above proves GET responses never leak rows across floors.
# Phase 0's most serious defects were on WRITE paths instead (POST /walkins
# trusting a caller-supplied floor_id; an unscoped transfer destination) --
# reads were clean throughout. This section attempts a representative
# id-addressed mutation against a record belonging to the OTHER business
# unit and asserts 404 (Phase 1 standardised cross-unit record access on
# 404, not 403 -- see auth.get_floor_scoped_or_404's docstring).
#
# Why this needs its own principal instead of reusing the read probe's
# owner login: owner/manager have has_all_floor_access() == True
# (auth.ROLE_HIERARCHY), so cross-unit id-addressed access is NOT blocked
# for them by design -- an owner can legitimately open any record on any
# floor by ID; a 404 there would itself be wrong (see
# get_floor_scoped_or_404's docstring). None of the seeded demo staff
# accounts are floor-restricted either (every account's floor_ids covers
# every floor) -- there is currently no real login that would ever observe
# a 404 here. So this probe borrows the SAME code path POST /auth/login
# uses (auth.create_session + auth.create_token) to mint a genuine session
# for the existing admin@forge.app account, having first temporarily
# narrowed its floor_ids to a single floor for the run -- no password
# needed, the account's credentials never change. Both the temporary
# floor_ids value and the session are removed before this function
# returns, including on a failed assertion (try/finally).
WRITE_TEST_PRINCIPAL_EMAIL = "admin@forge.app"
WRITE_TEST_FLOOR = GROUND       # the floor the temp principal is restricted to
WRITE_TEST_OTHER_FLOOR = SANITARY  # "the other business unit" for this run

# (label, collection to source record ids from, id-selection filter, method,
# path template -- "{id}" substituted with the record's own id, request body)
WRITE_PROBES: list[tuple[str, str, dict, str, str, dict]] = [
    ("Quotation", "quotations", {"status": {"$nin": ["ordered", "won"]}},
     "PATCH", "/api/quotations/{id}", {}),
    ("Customer", "customers", {},
     "PATCH", "/api/customers/{id}", {}),
    ("Purchase order", "purchase_orders", {},
     "PATCH", "/api/purchase-orders/{id}", {}),
    ("Tile order dispatch", "dispatches", {"is_deleted": False},
     "PATCH", "/api/tile-orders/dispatches/{id}/transport", {}),
]
# Payment is handled separately below: it is id-addressed via a BODY field
# (quotation_id), not a URL path segment -- POST /api/payments against an
# order id belonging to the other floor. Reuses the Quotation ids above.
# The quotation-status filter above (excluding ordered/won) is what keeps
# this genuinely non-mutating: create_payment 400s on "not a confirmed
# order yet" before it ever inserts anything, for both the same-unit and
# cross-unit request.
PAYMENT_PROBE_LABEL = "Payment (order id)"


def _write_request(method: str, url: str, token: str, floor: str, body: dict) -> int:
    """Fire one write request, return the HTTP status code. Never raises --
    an HTTPError IS the result being tested, not a probe failure."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method=method,
        headers={"Content-Type": "application/json"},
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-Floor-Id", floor)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _write_verdict(same_status: int | str, cross_status: int | str) -> str:
    problems: list[str] = []
    if same_status == 404:
        problems.append(f"same-unit request 404'd ({same_status}) -- the gate is blocking legitimate same-floor access")
    if cross_status != 404:
        problems.append(f"cross-unit request did NOT 404 (got {cross_status}) -- cross-unit record access leaked past the floor gate")
    return ("LEAK: " + "; ".join(problems)) if problems else "ok"


async def write_probe(base_url: str) -> tuple[list[dict], int]:
    from db import db  # backend/db.py -- only imported on the DB-verify path
    import auth        # create_session/create_token -- the real login code path

    admin = await db.users.find_one(
        {"email": WRITE_TEST_PRINCIPAL_EMAIL}, {"_id": 0, "id": 1, "role": 1, "floor_ids": 1},
    )
    if not admin:
        print(f"write probe: {WRITE_TEST_PRINCIPAL_EMAIL} not found -- skipping write probe", file=sys.stderr)
        return [], 0

    admin_id = admin["id"]
    original_floor_ids = admin.get("floor_ids")
    session_id: str | None = None
    rows: list[dict] = []
    failures = 0

    try:
        await db.users.update_one({"id": admin_id}, {"$set": {"floor_ids": [WRITE_TEST_FLOOR]}})
        session_id = await auth.create_session("staff", admin_id, None)
        token = auth.create_token(admin_id, "staff", {"role": admin["role"], "session_id": session_id})

        # Resolve one real record id per floor for each probed collection.
        ids_by_collection: dict[str, dict[str, str]] = {}
        for _label, collection, extra, *_rest in WRITE_PROBES:
            if collection in ids_by_collection:
                continue
            found: dict[str, str] = {}
            for floor in (WRITE_TEST_FLOOR, WRITE_TEST_OTHER_FLOOR):
                doc = await db[collection].find_one({"floor_id": floor, **extra}, {"_id": 0, "id": 1})
                if doc:
                    found[floor] = doc["id"]
            ids_by_collection[collection] = found

        for label, collection, _extra, method, path_tpl, body in WRITE_PROBES:
            ids = ids_by_collection[collection]
            if WRITE_TEST_FLOOR not in ids or WRITE_TEST_OTHER_FLOOR not in ids:
                rows.append({
                    "endpoint": label, "same_unit": "<no fixture>", "cross_unit": "<no fixture>",
                    "verdict": "SKIP: no record found on one or both floors to probe with",
                })
                continue
            same_status = _write_request(
                method, f"{base_url}{path_tpl.format(id=ids[WRITE_TEST_FLOOR])}", token, WRITE_TEST_FLOOR, body,
            )
            cross_status = _write_request(
                method, f"{base_url}{path_tpl.format(id=ids[WRITE_TEST_OTHER_FLOOR])}", token, WRITE_TEST_FLOOR, body,
            )
            verdict = _write_verdict(same_status, cross_status)
            if verdict != "ok":
                failures += 1
            rows.append({"endpoint": label, "same_unit": same_status, "cross_unit": cross_status, "verdict": verdict})

        # Payment: id-addressed via body.quotation_id, not the URL path.
        quotation_ids = ids_by_collection.get("quotations", {})
        if WRITE_TEST_FLOOR in quotation_ids and WRITE_TEST_OTHER_FLOOR in quotation_ids:
            same_status = _write_request(
                "POST", f"{base_url}/api/payments", token, WRITE_TEST_FLOOR,
                {"quotation_id": quotation_ids[WRITE_TEST_FLOOR], "amount": 1},
            )
            cross_status = _write_request(
                "POST", f"{base_url}/api/payments", token, WRITE_TEST_FLOOR,
                {"quotation_id": quotation_ids[WRITE_TEST_OTHER_FLOOR], "amount": 1},
            )
            verdict = _write_verdict(same_status, cross_status)
            if verdict != "ok":
                failures += 1
            rows.append({"endpoint": PAYMENT_PROBE_LABEL, "same_unit": same_status, "cross_unit": cross_status, "verdict": verdict})
        else:
            rows.append({
                "endpoint": PAYMENT_PROBE_LABEL, "same_unit": "<no fixture>", "cross_unit": "<no fixture>",
                "verdict": "SKIP: no record found on one or both floors to probe with",
            })

    finally:
        # Restore, unconditionally -- even if an assertion above raised or a
        # request errored unexpectedly. This is the only live-data mutation
        # write probing performs (a staff account's own floor_ids), and it
        # is always undone in the same run.
        await db.users.update_one({"id": admin_id}, {"$set": {"floor_ids": original_floor_ids}})
        if session_id:
            await db.user_sessions.delete_one({"id": session_id})

    return rows, failures


async def run_all(base_url: str, email: str, password: str) -> tuple[list[dict], int, list[dict], int]:
    """Both probes share the single event loop -- see _floors_from_db()'s
    docstring for why a second asyncio.run() is unsafe here."""
    read_rows, read_failures = await probe(base_url, email, password)
    write_rows, write_failures = await write_probe(base_url)
    return read_rows, read_failures, write_rows, write_failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--email", default="owner@forge.app")
    parser.add_argument("--password", default=os.environ.get("FORGE_PROBE_PASSWORD"))
    args = parser.parse_args()

    if not args.password:
        print(
            "Error: no password provided. Pass --password or set the "
            "FORGE_PROBE_PASSWORD environment variable.",
            file=sys.stderr,
        )
        # Return 64 (EX_USAGE) instead of 2 to distinguish config errors from isolation failures.
        # Exit codes 0–10 are reserved for the count of endpoints that failed isolation.
        return 64

    # One loop for the entire run -- see _floors_from_db().
    read_rows, read_failures, write_rows, write_failures = asyncio.run(
        run_all(args.base_url, args.email, args.password)
    )

    def cell(r: dict, name: str) -> str:
        floors = ",".join(sorted(v for v in r[name] if v != "None")) or "-"
        return f"{floors} ({r[f'{name}_count']})"

    print("== Read paths ==")
    print(f"{'endpoint':<18} {'unscoped':<30} {'first-floor':<18} {'ground-floor':<18} verdict")
    print("-" * 104)
    for r in read_rows:
        print(f"{r['endpoint']:<18} {cell(r, 'unscoped'):<30} {cell(r, 'first_floor'):<18} "
              f"{cell(r, 'ground_floor'):<18} {r['verdict']}")
    print(f"\n{len(read_rows) - read_failures}/{len(read_rows)} read endpoints isolated correctly.")
    print("Counts in parentheses. A zero count is NOT evidence of isolation -- "
          "compare it against the release report's figures before calling it a pass.")

    print(f"\n== Write paths (cross-unit id-addressed mutations, must 404) ==")
    print(f"{'endpoint':<24} {'same-unit':<12} {'cross-unit':<12} verdict")
    print("-" * 104)
    for r in write_rows:
        print(f"{r['endpoint']:<24} {str(r['same_unit']):<12} {str(r['cross_unit']):<12} {r['verdict']}")
    print(f"\n{len(write_rows) - write_failures}/{len(write_rows)} write endpoints correctly reject cross-unit access.")
    print("same-unit must be a non-404 status (the gate let a legitimate same-floor "
          "request through); cross-unit must be exactly 404.")

    failures = read_failures + write_failures
    print(f"\n{len(read_rows) + len(write_rows) - failures}/{len(read_rows) + len(write_rows)} "
          f"total checks passed ({read_failures} read failure(s), {write_failures} write failure(s)).")
    return failures


if __name__ == "__main__":
    sys.exit(main())
