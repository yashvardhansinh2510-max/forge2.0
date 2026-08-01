"""Read-path floor-isolation probe.

Mints a real staff session against a running backend and hits every
floor-scoped read three ways -- no X-Floor-Id, first-floor, ground-floor --
asserting the set of floor_id values actually present in each response.

This catches ambient-state leaks that clicking through the UI hides: a query
that silently runs unfiltered still *renders* fine in a browser.

Usage:
    FORGE_PROBE_PASSWORD=... ./.venv/bin/python -m scripts.probe_floor_isolation
    FORGE_PROBE_PASSWORD=... ./.venv/bin/python -m scripts.probe_floor_isolation --base-url http://127.0.0.1:8010

Exit code is the number of endpoints that failed isolation, so it is usable
as a CI gate.
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
        return 2

    # One loop for the entire run -- see _floors_from_db().
    rows, failures = asyncio.run(probe(args.base_url, args.email, args.password))

    def cell(r: dict, name: str) -> str:
        floors = ",".join(sorted(v for v in r[name] if v != "None")) or "-"
        return f"{floors} ({r[f'{name}_count']})"

    print(f"{'endpoint':<18} {'unscoped':<30} {'first-floor':<18} {'ground-floor':<18} verdict")
    print("-" * 104)
    for r in rows:
        print(f"{r['endpoint']:<18} {cell(r, 'unscoped'):<30} {cell(r, 'first_floor'):<18} "
              f"{cell(r, 'ground_floor'):<18} {r['verdict']}")

    print(f"\n{len(rows) - failures}/{len(rows)} endpoints isolated correctly.")
    print("Counts in parentheses. A zero count is NOT evidence of isolation -- "
          "compare it against the release report's figures before calling it a pass.")
    return failures


if __name__ == "__main__":
    sys.exit(main())
