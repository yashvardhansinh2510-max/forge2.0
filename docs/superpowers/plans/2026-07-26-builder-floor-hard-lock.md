# Builder Floor Hard-Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Tiles Selection/Quotation/Orders screens and the sanitary Quotation Builder immune to the caller's ambient "active floor" state — each always operates on its own floor's data, enforced server-side — fixing floor bleed-through, "All floors" merging into the tile picker, and tile add-product/save failures.

**Architecture:** Two complementary mechanisms, both reusing existing, already-tested infrastructure (`auth.py`'s `floor_query`/`floor_for_write`/`require_floor_access`, the `X-Floor-Id` header, `get_current_user`'s existing header validation):

1. **ID-addressed endpoints** (`/quotations/{id}`, `/customers/{id}`, `/products/{id}`, ...) switch from "filter the lookup query by ambient floor, 404 on mismatch" to "fetch by ID, then authorize the caller against *that record's own* `floor_id`" via a new shared helper, `get_floor_scoped_or_404`. This eliminates spurious 404s/save-failures whenever ambient state doesn't happen to match the record — which is the actual root cause of the reported "Could not place order" / "Save failed" symptoms, not just a display glitch.
2. **List/search/create endpoints** (`/products`, `/brands`, `/categories`, `/products/recent`, `/products/frequent`, `POST /customers`, `POST /quotations`) still depend on `user.active_floor_id`, which is populated from the `X-Floor-Id` header — already validated against the caller's real permissions inside `get_current_user` (403 if not allowed). The two builder screens now send an explicit, constant `floorId` override on every one of these calls (`ground-floor` for Tiles, `first-floor` for the sanitary builder) instead of relying on whatever the global floor switcher happens to be set to — added as an optional per-call override in the frontend `api` client, never touching global/shared floor-selector state.

**Tech Stack:** FastAPI + Motor (async MongoDB) backend, Expo/React Native Web frontend. Backend tests use the existing pattern in `backend/tests/unit/` — call the route's own async function directly with `asyncio.run(...)` and `monkeypatch`, no live server/DB (see `test_catalog_routes_floor_scoping.py`). Frontend has no test infrastructure (no jest/testing-library) — frontend verification is `npx tsc --noEmit` plus live browser checks, not automated tests.

## Global Constraints

- No data deletion, no schema change, no DB migration in this plan — purely query/routing correctness fixes.
- Never remove the existing `floor_query`/`floor_for_write` imports/usages that remain correct elsewhere in a touched file — only change the specific call sites named in each task.
- Every backend task's tests follow the existing `monkeypatch` + direct-function-call pattern already used in `backend/tests/unit/` — no live server, no live DB.
- Run `cd backend && pytest tests/unit -v` after every backend task; run `cd frontend && npx tsc --noEmit` after every frontend task. Both must stay clean.

---

## Task 1: Shared `get_floor_scoped_or_404` helper in `auth.py`

**Files:**
- Modify: `backend/auth.py` (add helper after `require_floor_access`, currently ending at line 338)
- Test: `backend/tests/unit/test_auth_get_floor_scoped_or_404.py` (new)

**Interfaces:**
- Produces: `async def get_floor_scoped_or_404(collection, doc_id: str, user: UserPublic, *, id_field: str = "id", not_found: str = "Not found", projection: dict | None = None, session: Any = None) -> dict` — raises `HTTPException(404)` if no document matches `{id_field: doc_id}`, raises `HTTPException(403)` (via `require_floor_access`) if the caller can't access the document's `floor_id` (defaulting to `"first-floor"` if absent), otherwise returns the raw document dict.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_auth_get_floor_scoped_or_404.py
"""Regression test: fetching a record by its own ID must authorize against
that record's floor_id, not pre-filter the query by the caller's ambient
active-floor selection (which 404s legitimate requests whenever ambient
state doesn't happen to match the record)."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from auth import get_floor_scoped_or_404
from models import UserPublic


def _user(role: str = "sales", floor_ids: list[str] | None = None, active_floor_id: str = "") -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role=role,
        floor_ids=floor_ids if floor_ids is not None else ["ground-floor", "first-floor"],
        active_floor_id=active_floor_id,
    )


class _FakeCollection:
    def __init__(self, docs: list[dict]):
        self._docs = {d["id"]: d for d in docs}

    async def find_one(self, query, projection=None, session=None):
        return self._docs.get(query.get("id"))


def test_returns_document_even_when_ambient_floor_differs():
    """The exact bug: caller's active_floor_id is 'first-floor' but the
    quotation they're fetching by ID lives on 'ground-floor' — a
    floor_query()-filtered lookup would 404 here; this helper must not."""
    collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(active_floor_id="first-floor")

    doc = asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert doc == {"id": "q1", "floor_id": "ground-floor"}


def test_missing_document_is_404():
    collection = _FakeCollection([])
    user = _user()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_floor_scoped_or_404(collection, "missing", user, not_found="Quotation not found"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "Quotation not found"


def test_unauthorized_floor_is_403_not_404():
    collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(floor_ids=["first-floor"])  # no ground-floor access

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert exc.value.status_code == 403


def test_all_floor_user_bypasses_the_check():
    collection = _FakeCollection([{"id": "q1", "floor_id": "ground-floor"}])
    user = _user(role="owner", floor_ids=[])  # owners get all-floor access regardless of floor_ids

    doc = asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert doc["id"] == "q1"


def test_missing_floor_id_defaults_to_first_floor():
    collection = _FakeCollection([{"id": "q1"}])  # legacy doc, no floor_id at all
    user = _user(floor_ids=["first-floor"])

    doc = asyncio.run(get_floor_scoped_or_404(collection, "q1", user))

    assert doc["id"] == "q1"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_auth_get_floor_scoped_or_404.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_floor_scoped_or_404' from 'auth'`

- [ ] **Step 3: Add the helper**

In `backend/auth.py`, change the `typing` import (line 6) from:

```python
from typing import Optional
```

to:

```python
from typing import Any, Optional
```

Then add this function immediately after `require_floor_access` (currently the last lines of the file, ~336-338):

```python
async def get_floor_scoped_or_404(
    collection: Any, doc_id: str, user: UserPublic, *,
    id_field: str = "id", not_found: str = "Not found",
    projection: dict | None = None, session: Any = None,
) -> dict:
    """Fetch a record by its own ID — never pre-filtered by the caller's
    ambient active-floor selection — then authorize against the record's
    OWN floor_id. Use this for every endpoint addressed by a specific
    record ID instead of `floor_query(user, {id_field: doc_id})`: filtering
    the initial query by ambient state 404s a legitimate request whenever
    that ambient state doesn't happen to match the record, even though the
    record exists and the caller genuinely has access to it."""
    doc = await collection.find_one({id_field: doc_id}, projection, session=session)
    if not doc:
        raise HTTPException(status_code=404, detail=not_found)
    require_floor_access(doc.get("floor_id", "first-floor"), user)
    return doc
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_auth_get_floor_scoped_or_404.py -v`
Expected: 5 passed

- [ ] **Step 5: Run the full unit suite to check for regressions**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -v`
Expected: all pass (same count as before + 5)

- [ ] **Step 6: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/auth.py backend/tests/unit/test_auth_get_floor_scoped_or_404.py && git commit -m "$(cat <<'EOF'
feat: add get_floor_scoped_or_404 — authorize ID-addressed lookups by the record's own floor, not ambient state

Filtering a by-ID lookup by the caller's active-floor header 404s a
legitimate request whenever that header doesn't happen to match the
record's actual floor (e.g. a tiles quotation reached while the global
floor switcher is still on the sanitary floor). Fetch by ID, then
authorize against the record's own floor_id instead.
EOF
)"
```

---

## Task 2: Apply the helper to `routes/quotation_routes.py`

**Files:**
- Modify: `backend/routes/quotation_routes.py` (6 call sites: `create_quotation`'s customer lookup ~line 124, `get_quotation` ~182, `update_quotation`'s initial fetch ~195 and customer-change fetch ~205, `place_order_preview` ~727, `place_order_confirm` ~745, `quotation_pdf` ~560)
- Test: `backend/tests/unit/test_quotation_routes_floor_scoped_lookups.py` (new)

**Interfaces:**
- Consumes: `get_floor_scoped_or_404` from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_quotation_routes_floor_scoped_lookups.py
"""Regression test: quotation-by-ID endpoints must not 404 just because the
caller's ambient active-floor header doesn't match the quotation's floor."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import routes.quotation_routes as quotation_routes
from models import UserPublic


def _user(active_floor_id: str = "first-floor") -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=active_floor_id,
    )


class _FakeQuotations:
    def __init__(self, doc: dict | None):
        self._doc = doc

    async def find_one(self, query, projection=None, session=None):
        if self._doc and query.get("id") == self._doc["id"]:
            return self._doc
        return None


class _FakeDb:
    def __init__(self, quotation: dict | None):
        self.quotations = _FakeQuotations(quotation)


def test_get_quotation_ignores_ambient_floor_mismatch(monkeypatch):
    doc = {"id": "q1", "floor_id": "ground-floor", "number": "FQ-2026-0001"}
    monkeypatch.setattr(quotation_routes, "db", _FakeDb(doc))

    # Ambient state says first-floor; the quotation is ground-floor. Must
    # still resolve, not 404.
    result = asyncio.run(quotation_routes.get_quotation("q1", user=_user(active_floor_id="first-floor")))

    assert result.id == "q1"


def test_get_quotation_still_404s_for_a_real_miss(monkeypatch):
    monkeypatch.setattr(quotation_routes, "db", _FakeDb(None))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(quotation_routes.get_quotation("missing", user=_user()))

    assert exc.value.status_code == 404


def test_place_order_preview_ignores_ambient_floor_mismatch(monkeypatch):
    doc = {"id": "q1", "floor_id": "ground-floor", "number": "FQ-2026-0001", "items": [
        {"id": "l1", "product_id": "p1", "sku": "SKU1", "name": "Tile", "qty": 2, "unit_price": 100.0},
    ]}
    monkeypatch.setattr(quotation_routes, "db", _FakeDb(doc))
    monkeypatch.setattr(quotation_routes, "per_line_net_amounts", lambda d: {"l1": 200.0})

    class _FakeProducts:
        async def find(self, *_a, **_kw):
            class _Cursor:
                async def to_list(self, _n):
                    return [{"id": "p1", "brand_id": None}]
            return _Cursor()

    quotation_routes.db.products = _FakeProducts()

    class _FakeBrands:
        async def find(self, *_a, **_kw):
            class _Cursor:
                async def to_list(self, _n):
                    return []
            return _Cursor()

    quotation_routes.db.brands = _FakeBrands()

    result = asyncio.run(quotation_routes.place_order_preview("q1", user=_user(active_floor_id="first-floor")))

    assert result["quotation_id"] == "q1"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_quotation_routes_floor_scoped_lookups.py -v`
Expected: FAIL — `get_quotation`/`place_order_preview` still 404 on the ambient-mismatch case (current `floor_query(user, ...)` filters it out).

- [ ] **Step 3: Apply the fix**

In `backend/routes/quotation_routes.py`, change the import (lines 10-13) from:

```python
from auth import (
    accessible_floor_ids, floor_for_write, floor_query, get_current_customer, get_current_user,
    require_min_role,
)
```

to:

```python
from auth import (
    accessible_floor_ids, floor_for_write, floor_query, get_current_customer, get_current_user,
    get_floor_scoped_or_404, require_min_role,
)
```

**`create_quotation`** (~line 124): change

```python
    customer = await db.customers.find_one(floor_query(user, {"id": body.customer_id}), {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
```

to:

```python
    customer = await get_floor_scoped_or_404(
        db.customers, body.customer_id, user, not_found="Customer not found", projection={"_id": 0},
    )
```

**`get_quotation`** (~line 182): change

```python
    doc = await db.quotations.find_one(floor_query(user, {"id": quotation_id}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return Quotation(**doc)
```

to:

```python
    doc = await get_floor_scoped_or_404(db.quotations, quotation_id, user, not_found="Quotation not found", projection={"_id": 0})
    return Quotation(**doc)
```

**`update_quotation`** (~line 195): change

```python
    doc = await db.quotations.find_one(floor_query(user, {"id": quotation_id}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
```

to:

```python
    doc = await get_floor_scoped_or_404(db.quotations, quotation_id, user, not_found="Quotation not found", projection={"_id": 0})
```

and, further down in the same function (~line 205), change

```python
        new_customer = await db.customers.find_one(floor_query(user, {"id": body.customer_id}), {"_id": 0})
        if not new_customer:
            raise HTTPException(status_code=404, detail="Customer not found")
```

to:

```python
        new_customer = await get_floor_scoped_or_404(
            db.customers, body.customer_id, user, not_found="Customer not found", projection={"_id": 0},
        )
```

**`quotation_pdf`** (~line 560): change

```python
    doc = await db.quotations.find_one(floor_query(user, {"id": quotation_id}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
```

to:

```python
    doc = await get_floor_scoped_or_404(db.quotations, quotation_id, user, not_found="Quotation not found", projection={"_id": 0})
```

**`place_order_preview`** (~line 727): change

```python
    doc = await db.quotations.find_one(floor_query(user, {"id": quotation_id}), {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if not doc.get("items"):
        raise HTTPException(status_code=400, detail="Cannot place order — quotation has no items")
```

to:

```python
    doc = await get_floor_scoped_or_404(db.quotations, quotation_id, user, not_found="Quotation not found", projection={"_id": 0})
    if not doc.get("items"):
        raise HTTPException(status_code=400, detail="Cannot place order — quotation has no items")
```

**`place_order_confirm`** (~line 745, inside the transaction): change

```python
                    doc = await db.quotations.find_one(floor_query(user, {"id": quotation_id}), {"_id": 0}, session=session)
                    if not doc:
                        raise HTTPException(status_code=404, detail="Quotation not found")
                    if not doc.get("items"):
```

to:

```python
                    doc = await get_floor_scoped_or_404(
                        db.quotations, quotation_id, user, not_found="Quotation not found",
                        projection={"_id": 0}, session=session,
                    )
                    if not doc.get("items"):
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_quotation_routes_floor_scoped_lookups.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full unit suite**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/quotation_routes.py backend/tests/unit/test_quotation_routes_floor_scoped_lookups.py && git commit -m "$(cat <<'EOF'
fix: quotation-by-ID routes authorize by the quotation's own floor, not ambient state

get_quotation, update_quotation, quotation_pdf, and the place-order
preview/confirm pair all 404'd whenever the caller's active-floor header
didn't happen to match the quotation's floor_id — the likely cause of
"Could not place order" and stalled tiles-builder saves. They now fetch
by ID and authorize against the document's own floor via
get_floor_scoped_or_404.
EOF
)"
```

---

## Task 3: Apply the helper to `routes/customer_routes.py`

**Files:**
- Modify: `backend/routes/customer_routes.py` (`get_customer` ~line 72, `update_customer`'s initial fetch ~line 86)
- Test: `backend/tests/unit/test_customer_routes_floor_scoped_lookups.py` (new)

**Interfaces:**
- Consumes: `get_floor_scoped_or_404` from Task 1.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_customer_routes_floor_scoped_lookups.py
"""Regression test: fetching/updating a customer by ID must not 404 just
because the caller's ambient active-floor header doesn't match the
customer's floor (e.g. a tiles-builder save while the global floor
switcher is still on the sanitary floor)."""
from __future__ import annotations

import asyncio

from models import UserPublic
import routes.customer_routes as customer_routes


def _user(active_floor_id: str = "first-floor") -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=active_floor_id,
    )


class _FakeCustomers:
    def __init__(self, doc: dict):
        self._doc = doc
        self.updated_with: dict | None = None

    async def find_one(self, query, projection=None, session=None):
        return self._doc if query.get("id") == self._doc["id"] else None

    async def update_one(self, query, update):
        self.updated_with = update


class _FakeDb:
    def __init__(self, doc: dict):
        self.customers = _FakeCustomers(doc)


def test_get_customer_ignores_ambient_floor_mismatch(monkeypatch):
    doc = {"id": "c1", "floor_id": "ground-floor", "name": "JK"}
    monkeypatch.setattr(customer_routes, "db", _FakeDb(doc))

    result = asyncio.run(customer_routes.get_customer("c1", user=_user(active_floor_id="first-floor")))

    assert result.id == "c1"


def test_update_customer_ignores_ambient_floor_mismatch(monkeypatch):
    from models import CustomerUpdatePayload
    doc = {"id": "c1", "floor_id": "ground-floor", "name": "JK", "portal_enabled": False}
    monkeypatch.setattr(customer_routes, "db", _FakeDb(doc))
    monkeypatch.setattr(customer_routes, "log_event", lambda **_kw: asyncio.sleep(0))

    result = asyncio.run(customer_routes.update_customer(
        "c1", CustomerUpdatePayload(name="JK Updated"), user=_user(active_floor_id="first-floor"),
    ))

    assert result.id == "c1"
    assert customer_routes.db.customers.updated_with["$set"]["name"] == "JK Updated"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_customer_routes_floor_scoped_lookups.py -v`
Expected: FAIL — both currently 404 on the ambient-mismatch case.

- [ ] **Step 3: Apply the fix**

In `backend/routes/customer_routes.py`, change the import (lines 4-6) from:

```python
from auth import (
    floor_for_write, floor_query, get_current_customer, get_current_user, hash_password, invalidate_principal_cache, require_min_role,
)
```

to:

```python
from auth import (
    floor_for_write, floor_query, get_current_customer, get_current_user, get_floor_scoped_or_404,
    hash_password, invalidate_principal_cache, require_min_role,
)
```

**`get_customer`** (~line 72): change

```python
    doc = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerPublic(**doc)
```

to:

```python
    doc = await get_floor_scoped_or_404(
        db.customers, customer_id, user, not_found="Customer not found", projection={"_id": 0, "password_hash": 0},
    )
    return CustomerPublic(**doc)
```

**`update_customer`** (~line 86), the initial fetch — change

```python
    existing = await db.customers.find_one(floor_query(user, {"id": customer_id}), {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Customer not found")
```

to:

```python
    existing = await get_floor_scoped_or_404(db.customers, customer_id, user, not_found="Customer not found", projection={"_id": 0})
```

(Leave the function's later `db.customers.update_one(floor_query(user, {"id": customer_id}), ...)` and the trailing re-fetch untouched — the caller's ambient floor is already confirmed valid earlier in the same request, and update filters here are just belt-and-suspenders on the same already-authorized ID.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_customer_routes_floor_scoped_lookups.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full unit suite**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/customer_routes.py backend/tests/unit/test_customer_routes_floor_scoped_lookups.py && git commit -m "$(cat <<'EOF'
fix: customer-by-ID routes authorize by the customer's own floor, not ambient state

Same fix shape as the quotation routes — get_customer/update_customer
404'd whenever the ambient active-floor header didn't match the
customer's floor_id, which blocked the tiles builder's header-edit
customer sync mid-save.
EOF
)"
```

---

## Task 4: Apply the helper to `routes/catalog_routes.py` (single-product lookups)

**Files:**
- Modify: `backend/routes/catalog_routes.py` (`get_product` ~366-373, `product_alternates` ~376-398, `complete_the_set` ~401-416)
- Test: `backend/tests/unit/test_catalog_routes_product_by_id_floor_scoping.py` (new)

**Interfaces:**
- Consumes: `get_floor_scoped_or_404` from Task 1; `catalog_service.product_by_id`, `catalog_service.alternate_products`, `catalog_service.complete_set_products` (all already accept `floor_ids: Optional[list[str]]`, unchanged signatures).

**Design note:** unlike the list/search endpoints, these three are addressed by a specific `product_id`. After authorizing via `get_floor_scoped_or_404`, `get_product` calls the service with `floor_ids=None` (unscoped — we already know the caller may see this one product). `product_alternates`/`complete_the_set` instead pass `floor_ids=[doc["floor_id"]]` — the SOURCE product's own floor — so suggested swap-in candidates are always same-floor as the product being viewed, regardless of the caller's ambient state (this also closes a latent bug: an "All floors" caller could previously get cross-floor swap suggestions, e.g. a tile alternate for a sanitary product).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_catalog_routes_product_by_id_floor_scoping.py
"""Regression test: product-by-ID endpoints must authorize by the product's
own floor, not the caller's ambient active-floor header, and alternates/
complete-the-set must scope their candidate pool to the SOURCE product's
floor rather than the caller's ambient state."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import routes.catalog_routes as catalog_routes
from models import UserPublic


def _user(active_floor_id: str = "first-floor") -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=active_floor_id,
    )


class _FakeProducts:
    def __init__(self, doc: dict):
        self._doc = doc

    async def find_one(self, query, projection=None, session=None):
        return self._doc if query.get("id") == self._doc["id"] else None


class _FakeDb:
    def __init__(self, doc: dict):
        self.products = _FakeProducts(doc)


def test_get_product_ignores_ambient_floor_mismatch(monkeypatch):
    doc = {"id": "p1", "floor_id": "ground-floor"}
    monkeypatch.setattr(catalog_routes, "db", _FakeDb(doc))
    fake = AsyncMock(return_value={"id": "p1"})
    monkeypatch.setattr(catalog_routes.catalog_service, "product_by_id", fake)

    result = asyncio.run(catalog_routes.get_product("p1", user=_user(active_floor_id="first-floor")))

    assert result == {"id": "p1"}
    fake.assert_awaited_once_with("p1", floor_ids=None)


def test_alternates_scope_pool_to_source_floor_not_ambient(monkeypatch):
    doc = {"id": "p1", "floor_id": "ground-floor"}
    monkeypatch.setattr(catalog_routes, "db", _FakeDb(doc))
    fake = AsyncMock(return_value={"source_product_id": "p1", "items": []})
    monkeypatch.setattr(catalog_routes.catalog_service, "alternate_products", fake)

    asyncio.run(catalog_routes.product_alternates("p1", user=_user(active_floor_id="first-floor")))

    _, kwargs = fake.await_args
    assert kwargs["floor_ids"] == ["ground-floor"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_catalog_routes_product_by_id_floor_scoping.py -v`
Expected: FAIL — both currently 404 (ambient mismatch) or pass the wrong `floor_ids`.

- [ ] **Step 3: Apply the fix**

In `backend/routes/catalog_routes.py`, change the import (line 8) from:

```python
from auth import floor_for_write, floor_query, floor_scope_ids, get_current_user, require_min_role
```

to:

```python
from auth import floor_for_write, floor_query, floor_scope_ids, get_current_user, get_floor_scoped_or_404, require_min_role
```

**`get_product`** (~366-373): change

```python
@router.get("/products/{product_id}")
async def get_product(product_id: str, user: UserPublic = Depends(get_current_user)):
    if not await db.products.find_one(floor_query(user, {"id": product_id}), {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Product not found")
    doc = await catalog_service.product_by_id(product_id, floor_ids=floor_scope_ids(user))
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return doc
```

to:

```python
@router.get("/products/{product_id}")
async def get_product(product_id: str, user: UserPublic = Depends(get_current_user)):
    await get_floor_scoped_or_404(db.products, product_id, user, not_found="Product not found", projection={"_id": 0, "id": 1})
    doc = await catalog_service.product_by_id(product_id, floor_ids=None)
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return doc
```

**`product_alternates`** (~376-398): change

```python
    if not await db.products.find_one(floor_query(user, {"id": product_id}), {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Product not found")
    result = await catalog_service.alternate_products(product_id, user.id, limit, floor_ids=floor_scope_ids(user))
```

to:

```python
    source = await get_floor_scoped_or_404(db.products, product_id, user, not_found="Product not found", projection={"_id": 0, "id": 1, "floor_id": 1})
    result = await catalog_service.alternate_products(product_id, user.id, limit, floor_ids=[source.get("floor_id", "first-floor")])
```

**`complete_the_set`** (~401-416): change

```python
    if not await db.products.find_one(floor_query(user, {"id": product_id}), {"_id": 0, "id": 1}):
        raise HTTPException(status_code=404, detail="Product not found")
    result = await catalog_service.complete_set_products(product_id, limit, floor_ids=floor_scope_ids(user))
```

to:

```python
    source = await get_floor_scoped_or_404(db.products, product_id, user, not_found="Product not found", projection={"_id": 0, "id": 1, "floor_id": 1})
    result = await catalog_service.complete_set_products(product_id, limit, floor_ids=[source.get("floor_id", "first-floor")])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_catalog_routes_product_by_id_floor_scoping.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full unit suite**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/catalog_routes.py backend/tests/unit/test_catalog_routes_product_by_id_floor_scoping.py && git commit -m "$(cat <<'EOF'
fix: product-by-ID catalog routes authorize by the product's own floor

get_product/product_alternates/complete_the_set 404'd on ambient-floor
mismatch same as the quotation/customer routes. Alternates and
complete-the-set now also scope their candidate pool to the SOURCE
product's floor instead of the caller's ambient state, closing a latent
cross-floor-suggestion bug for All-floors callers.
EOF
)"
```

---

## Task 5: `api` client — per-call floor override

**Files:**
- Modify: `frontend/src/api/client.ts` (lines 51-77: `request()` + the `api` export)

**Interfaces:**
- Produces: `api.get<T>(path, opts?: { floorId?: string })`, `api.post<T>(path, body?, opts?: { floorId?: string })`, `api.patch<T>(path, body?, opts?: { floorId?: string })` — when `opts.floorId` is set, it's sent as `X-Floor-Id` for that call only, taking precedence over the globally-stored selected floor. Global floor-selector storage (`SELECTED_FLOOR_KEY`) is never read or written by this override.

- [ ] **Step 1: Change `request()`**

In `frontend/src/api/client.ts`, change:

```typescript
async function request<T>(method: string, path: string, body?: any): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const floorId = await storage.getItem<string>(SELECTED_FLOOR_KEY, "");
  if (floorId) headers["X-Floor-Id"] = floorId;
```

to:

```typescript
async function request<T>(method: string, path: string, body?: any, opts?: { floorId?: string }): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const floorId = opts?.floorId ?? (await storage.getItem<string>(SELECTED_FLOOR_KEY, ""));
  if (floorId) headers["X-Floor-Id"] = floorId;
```

- [ ] **Step 2: Thread `opts` through the `api` export**

Change:

```typescript
export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: any) => request<T>("POST", p, b),
  put: <T>(p: string, b?: any) => request<T>("PUT", p, b),
  patch: <T>(p: string, b?: any) => request<T>("PATCH", p, b),
  delete: <T>(p: string) => request<T>("DELETE", p),
```

to:

```typescript
export const api = {
  get: <T>(p: string, opts?: { floorId?: string }) => request<T>("GET", p, undefined, opts),
  post: <T>(p: string, b?: any, opts?: { floorId?: string }) => request<T>("POST", p, b, opts),
  put: <T>(p: string, b?: any, opts?: { floorId?: string }) => request<T>("PUT", p, b, opts),
  patch: <T>(p: string, b?: any, opts?: { floorId?: string }) => request<T>("PATCH", p, b, opts),
  delete: <T>(p: string, opts?: { floorId?: string }) => request<T>("DELETE", p, undefined, opts),
```

(Leave the rest of the `api` object — e.g. any download-URL builder methods below this block — untouched.)

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (existing call sites omit the new optional param, which is valid).

- [ ] **Step 4: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/src/api/client.ts && git commit -m "$(cat <<'EOF'
feat: api client accepts a per-call X-Floor-Id override

Lets a specific screen pin its own floor context on outgoing requests
without touching the globally shared floor-selector state — needed so
the Tiles and sanitary Quotation Builder screens can hard-lock their own
catalog/customer/quotation calls regardless of the global floor switcher.
EOF
)"
```

---

## Task 6: Wire `floorId: "ground-floor"` into the Tiles builder

**Files:**
- Modify: `frontend/src/components/tiles/TilesProductPicker.tsx` (search call, ~line 35)
- Modify: `frontend/src/components/tiles/TilesDocBuilder.tsx` (3 call sites: customers GET ~line 156, customer POST create ~line 320, quotation POST create ~line 345)

**Interfaces:**
- Consumes: `api.get`/`api.post` with `opts.floorId` from Task 5.

- [ ] **Step 1: `TilesProductPicker.tsx`**

Change:

```typescript
      const res = await api.get<{ items: Product[]; total: number }>(`/products?${params.toString()}`);
```

to:

```typescript
      const res = await api.get<{ items: Product[]; total: number }>(`/products?${params.toString()}`, { floorId: "ground-floor" });
```

- [ ] **Step 2: `TilesDocBuilder.tsx` — customers GET**

Change (~line 156):

```typescript
  useEffect(() => {
    api.get<Customer[]>("/customers").then(setCustomers).catch(() => {});
  }, []);
```

to:

```typescript
  useEffect(() => {
    api.get<Customer[]>("/customers", { floorId: "ground-floor" }).then(setCustomers).catch(() => {});
  }, []);
```

- [ ] **Step 3: `TilesDocBuilder.tsx` — customer create**

Change (~line 320):

```typescript
        const created = await api.post<Customer>("/customers", { name, phone: header.phone.trim() || null });
```

to:

```typescript
        const created = await api.post<Customer>("/customers", { name, phone: header.phone.trim() || null }, { floorId: "ground-floor" });
```

- [ ] **Step 4: `TilesDocBuilder.tsx` — quotation create**

Change (~line 345):

```typescript
        const created = await api.post<{ id: string; number: string }>("/quotations", { ...payload, doc_type: docType });
```

to:

```typescript
        const created = await api.post<{ id: string; number: string }>("/quotations", { ...payload, doc_type: docType }, { floorId: "ground-floor" });
```

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 6: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/src/components/tiles/TilesProductPicker.tsx frontend/src/components/tiles/TilesDocBuilder.tsx && git commit -m "$(cat <<'EOF'
fix: Tiles builder pins ground-floor on every catalog/customer/quotation call

Product search, the customer list/create, and quotation create no longer
depend on the global floor switcher — they always request ground-floor
data, closing the "can't add products in the tiles quotation" and
first-floor-bleed-through reports.
EOF
)"
```

---

## Task 7: Wire `floorId: "first-floor"` into the sanitary Quotation Builder

**Files:**
- Modify: `frontend/src/components/quotation/context/BuilderContext.tsx` (10 call sites — see below)

**Interfaces:**
- Consumes: `api.get`/`api.post` with `opts.floorId` from Task 5.

- [ ] **Step 1: Initial reference-data load**

Change (~lines 269-276):

```typescript
        const [cs, cats, brs, rec, freq, recentQ] = await Promise.all([
          api.get<Customer[]>("/customers"),
          api.get<Category[]>("/categories"),
          api.get<Brand[]>("/brands"),
          api.get<Product[]>("/products/recent"),
          api.get<Product[]>("/products/frequent"),
          api.get<RecentQuotation[]>("/quotations/recent?limit=10"),
        ]);
```

to:

```typescript
        const [cs, cats, brs, rec, freq, recentQ] = await Promise.all([
          api.get<Customer[]>("/customers", { floorId: "first-floor" }),
          api.get<Category[]>("/categories", { floorId: "first-floor" }),
          api.get<Brand[]>("/brands", { floorId: "first-floor" }),
          api.get<Product[]>("/products/recent", { floorId: "first-floor" }),
          api.get<Product[]>("/products/frequent", { floorId: "first-floor" }),
          api.get<RecentQuotation[]>("/quotations/recent?limit=10"),
        ]);
```

(`/quotations/recent` is left as-is — it's a list of the CALLER's own recent quotations across whatever floors they're allowed, used for the left-rail panel, not a catalog/creation call this fix is scoped to.)

- [ ] **Step 2: Categories re-fetch on brand change**

Change (~lines 304-307):

```typescript
        const cats = await api.get<Category[]>(
          selectedBrandId ? `/categories?brand_id=${selectedBrandId}` : "/categories",
        );
```

to:

```typescript
        const cats = await api.get<Category[]>(
          selectedBrandId ? `/categories?brand_id=${selectedBrandId}` : "/categories",
          { floorId: "first-floor" },
        );
```

- [ ] **Step 3: Product search (first page)**

Change (~line 348):

```typescript
        const res = await api.get<{ items: Product[]; total: number }>(`/products?${params.toString()}`);
```

to:

```typescript
        const res = await api.get<{ items: Product[]; total: number }>(`/products?${params.toString()}`, { floorId: "first-floor" });
```

(This occurs twice in the file — once in the page-1 effect ~line 348, once in `loadMoreProducts` ~line 380. Apply the identical change to both.)

- [ ] **Step 4: Quotation create**

Change (~line 421):

```typescript
        const created = await api.post<{ id: string; number: string }>("/quotations", payload);
```

to:

```typescript
        const created = await api.post<{ id: string; number: string }>("/quotations", payload, { floorId: "first-floor" });
```

- [ ] **Step 5: Customer create**

Change (~lines 588-590):

```typescript
      const created = await api.post<Customer>("/customers", {
        name: data.name, phone: data.phone || null, project: data.project || null, address: data.address || null,
      });
```

to:

```typescript
      const created = await api.post<Customer>("/customers", {
        name: data.name, phone: data.phone || null, project: data.project || null, address: data.address || null,
      }, { floorId: "first-floor" });
```

- [ ] **Step 6: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 7: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/src/components/quotation/context/BuilderContext.tsx && git commit -m "$(cat <<'EOF'
fix: sanitary Quotation Builder pins first-floor on every catalog/customer/quotation call

Mirrors the Tiles builder fix — brands, categories, recent/frequent,
product search, and customer/quotation creation no longer depend on the
global floor switcher, so ground-floor tile products can no longer leak
into a sanitary quotation regardless of "All floors" or stale ambient
state.
EOF
)"
```

---

## Task 8: Access-control guard on direct URL entry

**Files:**
- Modify: `frontend/src/hooks/use-floor-access.ts` (add `useRequireFloorAccess`)
- Modify: `frontend/app/(admin)/tiles/selection.tsx`, `frontend/app/(admin)/tiles/quotation.tsx`, `frontend/app/(admin)/tiles/orders/index.tsx`, `frontend/app/(admin)/tiles/orders/[id].tsx`, `frontend/app/(admin)/quotations/new.tsx`

**Interfaces:**
- Produces: `useRequireFloorAccess(floorId: string): void` — redirects to `/(admin)/dashboard` with an error toast if the signed-in user's floor access (from `useFloorAccess()`) doesn't include `floorId`. No-ops while access is still loading.

- [ ] **Step 1: Add the guard hook**

In `frontend/src/hooks/use-floor-access.ts`, add these imports at the top:

```typescript
import { useRouter } from "expo-router";

import { toast } from "@/src/components/Toast";
```

and this function at the end of the file:

```typescript
export function useRequireFloorAccess(floorId: string) {
  const { access } = useFloorAccess();
  const router = useRouter();
  useEffect(() => {
    if (!access) return; // still loading — nothing to enforce yet
    const allowed = access.all_floors || access.floor_ids.includes(floorId);
    if (!allowed) {
      toast.error("You don't have access to that floor");
      router.replace("/(admin)/dashboard" as any);
    }
  }, [access, floorId, router]);
}
```

- [ ] **Step 2: Guard the three Tiles routes**

`frontend/app/(admin)/tiles/selection.tsx` — change:

```typescript
import { TilesDocBuilder } from "@/src/components/tiles/TilesDocBuilder";

export default function TilesSelectionScreen() {
  return <TilesDocBuilder docType="tiles_selection" />;
}
```

to:

```typescript
import { TilesDocBuilder } from "@/src/components/tiles/TilesDocBuilder";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function TilesSelectionScreen() {
  useRequireFloorAccess("ground-floor");
  return <TilesDocBuilder docType="tiles_selection" />;
}
```

`frontend/app/(admin)/tiles/quotation.tsx` — change:

```typescript
import { TilesDocBuilder } from "@/src/components/tiles/TilesDocBuilder";

export default function TilesQuotationScreen() {
  return <TilesDocBuilder docType="tiles_quotation" />;
}
```

to:

```typescript
import { TilesDocBuilder } from "@/src/components/tiles/TilesDocBuilder";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function TilesQuotationScreen() {
  useRequireFloorAccess("ground-floor");
  return <TilesDocBuilder docType="tiles_quotation" />;
}
```

`frontend/app/(admin)/tiles/orders/index.tsx` — add the import alongside the existing ones:

```typescript
import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { TileOrderCard, type OrderCard } from "@/src/components/tiles/TileOrderCard";
import { useBp } from "@/src/design/responsive";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
```

becomes:

```typescript
import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { TileOrderCard, type OrderCard } from "@/src/components/tiles/TileOrderCard";
import { useBp } from "@/src/design/responsive";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
```

and change:

```typescript
export default function TileOrdersScreen() {
  const router = useRouter();
  const { isPhone, isTablet } = useBp();
```

to:

```typescript
export default function TileOrdersScreen() {
  useRequireFloorAccess("ground-floor");
  const router = useRouter();
  const { isPhone, isTablet } = useBp();
```

`frontend/app/(admin)/tiles/orders/[id].tsx` — add the same import (alongside its existing `colors, radius, spacing, type` import line) and change:

```typescript
export default function TileOrderDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
```

to:

```typescript
export default function TileOrderDetailScreen() {
  useRequireFloorAccess("ground-floor");
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
```

- [ ] **Step 3: Guard the sanitary builder entry**

In `frontend/app/(admin)/quotations/new.tsx`, change:

```typescript
import { BuilderProvider, BuilderShell } from "@/src/components/quotation";

export default function QuotationBuilderScreen() {
  const router = useRouter();
```

to:

```typescript
import { BuilderProvider, BuilderShell } from "@/src/components/quotation";
import { useRequireFloorAccess } from "@/src/hooks/use-floor-access";

export default function QuotationBuilderScreen() {
  useRequireFloorAccess("first-floor");
  const router = useRouter();
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/src/hooks/use-floor-access.ts frontend/app/\(admin\)/tiles/selection.tsx frontend/app/\(admin\)/tiles/quotation.tsx frontend/app/\(admin\)/tiles/orders/index.tsx "frontend/app/(admin)/tiles/orders/[id].tsx" frontend/app/\(admin\)/quotations/new.tsx && git commit -m "$(cat <<'EOF'
fix: redirect away from Tiles/sanitary builder screens without floor access

The sidebar already hid these nav links from unauthorized staff, but a
direct URL/bookmark still reached the screen and just cascaded into
failed API calls. Now redirects to the dashboard with a clear message
instead.
EOF
)"
```

---

## Task 9: Live end-to-end verification (no commit)

Not a code change — confirms the fix actually works against the real app, per this repo's convention that frontend correctness is verified live (no frontend test infra).

- [ ] **Step 1: Start the backend and frontend dev servers** (ask before restarting the shared `:8010` backend if another session might be using it — see project memory)

- [ ] **Step 2: As an owner/manager account, set the floor switcher to "All floors"**

- [ ] **Step 3: Navigate directly to `/tiles/quotation` by typing the URL** (not via the sidebar link)
- Confirm the product picker only returns tile products (search for a known sanitary-only term, e.g. a Hansgrohe/Grohe SKU — zero results expected)
- Add a product, confirm the row populates
- Pick or create a customer, confirm no "Customer not found"/"Save failed" toast
- Save, confirm no error toast and the doc persists (reload the page, confirm it's still there)

- [ ] **Step 4: From the same "All floors" state, navigate directly to `/quotations/new`**
- Confirm the product picker/brand rail only returns sanitary products (search for a known tile SKU — zero results expected)
- Confirm the global floor switcher still reads "All floors" after leaving both builders (proves no global state was mutated)

- [ ] **Step 5: Confirm untouched screens still merge under "All floors"**
- Open Catalog browse, Dashboard, Customers, Purchases list — confirm they still show both floors' data together (regression guard — these were explicitly NOT locked)

- [ ] **Step 6: Confirm the access-control guard**
- Log in as (or temporarily assign) a staff account scoped to `first-floor` only
- Navigate directly to `/tiles/selection` by URL — confirm it redirects to the dashboard with a toast, rather than showing a broken screen

- [ ] **Step 7: Report results to the user** — summarize pass/fail for each check above; if anything fails, that's a new bug to triage (likely a missed call site), not a reason to mark this plan done.
