# Qutone Ground Floor Tiles Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import "Qutone" — the first Ground Floor Tiles brand — from `QUTONE 2026.xlsx` (452 rows, 403 embedded product photos, single sheet) into the production BuildCon House catalog, using the exact same `catalog_pipeline` architecture already proven for the 5 sanitary brands (Hansgrohe/Axor/Grohe/Vitra/Geberit/Oyster), targeting `floor_id="ground-floor"` end-to-end.

**Architecture:** Add one new `BrandAdapter` (`QutoneAdapter`) that parses the single XLSX source and extracts embedded images via the existing `extract_images_from_xlsx_ex` engine — no new extraction code needed. Register it in the adapter registry and the HTTP import allowlist. Import via a new standalone script modeled byte-for-byte on the existing `run_oyster_import.py` precedent: pre-import integrity scan → DB snapshot backup → adapter extract → `certifier.validate()` → auto-accept → `orchestrator.import_accepted()` (Brand/Category autocreate, dedupe-by-`(sku,brand_id,floor_id)`, Supabase image upload via `services/media_service.upload_and_register`) → post-import integrity diff → QA report. Every write happens through the existing pipeline; nothing bypasses it.

Three small, generic (non-Qutone-specific) fixes to the shared pipeline are required because this is the first *tiles* brand and the first *non-`first-floor`* import ever run through it:
1. `ProductRow`/`Product` gained a `size` field months ago for exactly this purpose but no adapter or orchestrator code ever wired it up — wire it up generically so any adapter can populate it.
2. The orchestrator's category auto-create step eagerly pre-seeds all 12 *sanitary-only* `ALLOWED_CATEGORIES` onto whichever floor is being imported into — harmless on `first-floor` (all 12 already exist there from months of real imports) but would pollute `ground-floor`'s category list with 11 empty, irrelevant sanitary categories (Faucets, Bidets, Urinals, ...) on the very first Qutone run. The per-row auto-create path already makes this loop fully redundant, so it's removed.
3. `image_extractor.py` always resizes-to-1024px + recompresses (JPEG q=82 / WebP q=80) any image over 60KB or with alpha. The user's explicit requirement is "preserve original quality, do not compress, do not resize" — add an opt-out `optimize` flag, defaulting to `True` (zero behavior change for the 5 existing brands), and have the Qutone adapter pass `False`.

**Tech Stack:** Python 3.14, FastAPI backend, MongoDB Atlas (Motor async driver, replica-set), Supabase Storage (`media_storage/supabase_driver.py`), openpyxl for XLSX parsing, pytest for tests.

## Global Constraints

- **No new storage pattern / no new collections.** Products are flat `Product` documents (one per size+finish variant), grouped by a shared `family_key` string, exactly like every existing brand. `Category`/`Brand`/`Product`/`ProductMedia`/`CatalogImportJob` schemas are already floor-scoped and already sufficient — no migration is needed.
- **`floor_id="ground-floor"` for every Qutone brand/category/product/media doc.** The `ground-floor` floor document already exists in the live DB (auto-seeded by `services/floor_scope.py` on every backend boot) — nothing to create there.
- **No SKU/article code exists in the source file.** Confirmed by direct inspection of all 452 rows: no SKU column, and `(SERIES NAME, PRODUCT NAME, PRODUCT SIZE, FINISHES)` is unique across all 452 rows. SKU is therefore synthesized, deterministic, and idempotent: `QUTONE-{SERIES_COMPACT}-{NAME_COMPACT}-{SIZE_COMPACT}-{FINISH_CODE}` — same inputs always regenerate the same SKU, so re-running the import upserts instead of duplicating (verified by the orchestrator's existing `(sku, brand_id, floor_id)` upsert key — see `catalog_pipeline/orchestrator.py:291`).
- **Never fabricate missing data.** The source has no Description column and no separate MRP-vs-dealer-price split (only one `RATE` column, e.g. `"225 PER SQFT"`). `description` stays `null`. `mrp` and `price` (per-sqft rate) are both set to the same parsed value — there is only one price tier in this source, so inventing a second one would be fabrication. This mirrors the existing Oyster adapter's documented convention of setting both fields from the single price the source actually provides.
- **`RATE` format is always `"<number> PER SQFT"`** (confirmed: all 452 rows match `^\s*([\d,.]+)\s*PER\s*SQFT\s*$` case-insensitive). A future file with a row that doesn't match this pattern must not crash the batch — flag it (`needs_pricing`, price imported at ₹0) and continue, exactly like Oyster's `needs_pricing` convention.
- **Finish normalization is an explicit lookup table**, not fuzzy regex guessing — 6 distinct raw finish strings observed (`MATT`, `GLOSSY`, `CHIFFON`, `DOVE`, `SILK`, `STRUCTURE-MATT`), verified by direct inspection. Any new/unrecognized string encountered at run time is flagged for manual review, not silently mapped or dropped.
- **Images: preserve original quality — no resize, no recompress.** 403/452 rows have an embedded JPEG (already only 240×360px / ~40-55KB in the source — this is the supplier's real resolution, not something this pipeline can improve). The remaining 49 rows (the file's last 49 data rows) have no embedded image at all — flagged as `missing_images` in the summary, product still imported without a photo, never held back.
- **Confidence/auto-accept must not be gated on image presence.** A row with no image is still real, priced, complete product data — it must still auto-import (with the missing-image flag surfaced separately), matching how the existing Oyster adapter's confidence score already ignores image presence and only reflects finish-recognition + price-parse success.
- **Production write safety gate:** the import script must support `--dry-run` (extract + validate + certify only, zero DB/Supabase writes), run and reviewed before the real import, which writes directly to the live `buildcon_house` Atlas DB and the `forge-products` Supabase bucket.
- **"Company Name" / supplier is stored in `Product.specs.company_name`, not a dedicated top-level field.** Confirmed architecturally: `Product` has no `company`/`supplier_id` field distinct from `brand_id` — every existing brand treats the manufacturer brand AS the company identity for catalog purposes (there's a separate, unrelated `Supplier` model used only by Purchase Orders). In this source, `company NAME` is `"QUTONE"` on all 452 rows, identical to the brand itself, so `brand_id` (resolving to the Qutone `Brand` doc) already carries this relationship for querying/filtering/display; `specs.company_name` preserves the raw source value too, satisfying "do not discard any information present in the source files" without inventing a new schema field for a value that's otherwise redundant with `brand_id`.
- Reuse `catalog_pipeline.orchestrator.import_accepted()` for all writes — it already handles Brand/Category autocreate-or-reuse, `(sku, brand_id, floor_id)` dedup (idempotent), snapshot-based rollback, and Supabase image upload via `services/media_service.upload_and_register`. Do not hand-roll any of this.

---

## File Structure

- **Modify:** `backend/catalog_pipeline/base.py` — add `size: str = MISSING` to `ProductRow` (+ `to_public()`).
- **Modify:** `backend/catalog_pipeline/orchestrator.py` — thread `size` into the product payload; remove the `ALLOWED_CATEGORIES` eager pre-seed loop (dead/harmful — the per-row auto-create path already covers this generically).
- **Modify:** `backend/catalog_pipeline/image_extractor.py` — add `optimize: bool = True` to `_decode_supplier_image()` and `extract_images_from_xlsx_ex()`.
- **Create:** `backend/catalog_pipeline/adapters/qutone.py` — `QutoneAdapter` class: header-driven column mapping (not hardcoded column letters), finish normalization table, deterministic SKU/family_key generation, row-anchored image extraction with `optimize=False`.
- **Modify:** `backend/catalog_pipeline/adapters/__init__.py` — register `"qutone": QutoneAdapter` in `REGISTRY`.
- **Modify:** `backend/routes/catalog_import_routes.py` — add `"Qutone"` to `SUPPORTED_BRANDS`.
- **Create:** `backend/tests/unit/test_qutone_adapter.py` — unit tests for finish normalization, SKU/family_key determinism, rate parsing, and full `extract()` against a synthetic in-memory workbook.
- **Create:** `backend/tests/unit/test_image_extractor_optimize_flag.py` — proves `optimize=False` preserves bytes exactly; `optimize=True` (and the default) still resizes/recompresses, so existing brands are unaffected.
- **Create:** `backend/tests/unit/test_catalog_import_qutone_floor_scoping.py` — orchestrator-level integration test: Brand/Category auto-created scoped to `ground-floor`, `size`/`specs` fields persisted, idempotent re-run, and a regression test proving no sanitary categories leak onto `ground-floor`.
- **Create:** `backend/scripts/run_qutone_import.py` — standalone runner script (modeled on `run_oyster_import.py`): reads the local copy of the source file, runs the full pipeline, supports `--dry-run`.
- **Create (copied, not authored):** `backend/temp/qutone_source_files/QUTONE 2026.xlsx` — stable in-repo copy of the source file (matches the existing `backend/temp/oyster_source_files/` precedent; the original lives in the user's Downloads folder, which isn't a stable path for a script to depend on).
- **Output (generated by the script, not hand-written):** `memory/qutone_qa_report.json` (import summary — total imported, duplicates skipped, failed rows, images uploaded, missing images, validation warnings).

---

### Task 1: Wire up the dormant `Product.size` field through `ProductRow`

**Files:**
- Modify: `backend/catalog_pipeline/base.py`
- Modify: `backend/catalog_pipeline/orchestrator.py:244-276` (payload dict)
- Test: `backend/tests/unit/test_orchestrator_size_field.py`

**Interfaces:**
- Produces: `ProductRow.size: str` (defaults to `MISSING`, same sentinel convention as every other optional field), included in `ProductRow.to_public()`. Consumed by Task 4 (`QutoneAdapter` sets it) and Task 6 (integration test asserts it lands on the persisted `Product` doc).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_orchestrator_size_field.py
"""Product.size already exists in the schema (models.py: "e.g. '600x600mm' —
tile nominal size") but no adapter or orchestrator code ever populated it —
this is the generic wiring, not Qutone-specific."""
from __future__ import annotations

import asyncio

import pytest

import catalog_pipeline.orchestrator as orchestrator


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, _n):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs: dict[str, dict] = {d["id"]: d for d in (docs or [])}

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return dict(doc)
        return None

    def find(self, query=None, *_args, **_kwargs):
        query = query or {}
        matched = [d for d in self.docs.values() if all(d.get(k) == v for k, v in query.items() if not isinstance(v, dict))]
        return _FakeCursor(matched)

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)

    async def insert_many(self, docs):
        for d in docs:
            d.setdefault("id", f"snap-{len(self.docs)}")
            self.docs[d["id"]] = dict(d)

    async def update_one(self, query, update):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                doc.update(update.get("$set", {}))
                return


class _FakeDb:
    def __init__(self):
        self.brands = _FakeCollection()
        self.categories = _FakeCollection()
        self.products = _FakeCollection()
        self.catalog_import_snapshots = _FakeCollection()


@pytest.fixture(autouse=True)
def _patch_db_and_uploads(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(orchestrator, "db", fake_db)

    async def _noop_upload(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_upload_supplier_images", _noop_upload)
    return fake_db


def test_size_field_flows_from_row_to_persisted_product(_patch_db_and_uploads):
    job = {
        "id": "job-size-1", "supplier_name": "TestBrand", "floor_id": "first-floor",
        "rows": [{
            "row_id": "r1", "status": "accepted", "sku": "SKU-1", "mrp": 100.0,
            "category": "Tiles", "name": "Test Tile", "size": "600X600",
        }],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="first-floor"))
    fake_db = orchestrator.db
    product = next(iter(fake_db.products.docs.values()))
    assert product["size"] == "600X600"


def test_missing_size_stays_null_not_fabricated(_patch_db_and_uploads):
    job = {
        "id": "job-size-2", "supplier_name": "TestBrand", "floor_id": "first-floor",
        "rows": [{
            "row_id": "r1", "status": "accepted", "sku": "SKU-2", "mrp": 100.0,
            "category": "Faucets", "name": "Test Faucet",
        }],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="first-floor"))
    fake_db = orchestrator.db
    product = next(iter(fake_db.products.docs.values()))
    assert product["size"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_orchestrator_size_field.py -v`
Expected: FAIL — `assert product["size"] == "600X600"` raises `KeyError: 'size'` (the payload dict never sets this key today).

- [ ] **Step 3: Add the `size` field to `ProductRow`**

In `backend/catalog_pipeline/base.py`, add the field next to `dimensions` (line 32) and to `to_public()` (after the `dimensions` entry, line 55):

```python
    dimensions: str = MISSING
    size: str = MISSING            # tile nominal size, e.g. "600X600" — distinct from `dimensions`
    description: str = MISSING
```

```python
            "dimensions": self.dimensions, "size": self.size, "description": self.description,
```//replaces the existing `"dimensions": self.dimensions, "description": self.description,` line

- [ ] **Step 4: Thread `size` into the orchestrator's product payload**

In `backend/catalog_pipeline/orchestrator.py`, in the `payload = {...}` dict (starts at line 244), add one line after `"dimensions": _clean(r.get("dimensions")),` (line 259):

```python
                "dimensions": _clean(r.get("dimensions")),
                "size": _clean(r.get("size")),
                "warranty": _clean(r.get("warranty")),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_orchestrator_size_field.py -v`
Expected: PASS

- [ ] **Step 6: Run the full existing unit suite to confirm zero regressions**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit -v`
Expected: PASS (all pre-existing tests unaffected — `size` defaults to `MISSING`/`None` for every row that doesn't set it, i.e. every existing brand).

- [ ] **Step 7: Commit**

```bash
git add backend/catalog_pipeline/base.py backend/catalog_pipeline/orchestrator.py backend/tests/unit/test_orchestrator_size_field.py
git commit -m "feat: wire the dormant Product.size field through ProductRow and the import orchestrator"
```

---

### Task 2: Remove the sanitary-only category pre-seed loop from `import_accepted`

**Files:**
- Modify: `backend/catalog_pipeline/orchestrator.py:149-158`
- Test: `backend/tests/unit/test_catalog_import_no_category_pollution.py`

**Interfaces:**
- No signature changes — `import_accepted()`'s external contract (params, return dict) is unchanged. Removes an internal side effect only.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_catalog_import_no_category_pollution.py
"""orchestrator.import_accepted() used to eagerly pre-seed all 12
sanitary-only ALLOWED_CATEGORIES onto whichever floor_id it was given
(catalog_pipeline/orchestrator.py, pre-fix lines 152-158) — harmless on
first-floor (all 12 already exist there from real imports) but would litter
a brand-new floor like ground-floor with 11 empty, irrelevant categories
(Faucets, Bidets, Urinals, ...) the moment the first tile import runs. The
per-row auto-create path a few lines below already creates whatever
category a row's own data specifies, generically, for any floor — the
eager pre-seed loop is redundant and actively harmful, so it's removed."""
from __future__ import annotations

import asyncio

import pytest

import catalog_pipeline.orchestrator as orchestrator


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, _n):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs: dict[str, dict] = {d["id"]: d for d in (docs or [])}

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return dict(doc)
        return None

    def find(self, query=None, *_args, **_kwargs):
        query = query or {}
        matched = [d for d in self.docs.values() if all(d.get(k) == v for k, v in query.items() if not isinstance(v, dict))]
        return _FakeCursor(matched)

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)

    async def insert_many(self, docs):
        for d in docs:
            d.setdefault("id", f"snap-{len(self.docs)}")
            self.docs[d["id"]] = dict(d)

    async def update_one(self, query, update):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                doc.update(update.get("$set", {}))
                return


class _FakeDb:
    def __init__(self):
        self.brands = _FakeCollection()
        self.categories = _FakeCollection()
        self.products = _FakeCollection()
        self.catalog_import_snapshots = _FakeCollection()


@pytest.fixture(autouse=True)
def _patch_db_and_uploads(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(orchestrator, "db", fake_db)

    async def _noop_upload(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_upload_supplier_images", _noop_upload)
    return fake_db


def test_importing_a_tiles_row_creates_only_the_tiles_category_on_ground_floor(_patch_db_and_uploads):
    job = {
        "id": "job-cat-1", "supplier_name": "Qutone", "floor_id": "ground-floor",
        "rows": [{
            "row_id": "r1", "status": "accepted", "sku": "SKU-TILE-1", "mrp": 225.0,
            "category": "Tiles", "name": "Test Tile",
        }],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="ground-floor"))
    fake_db = orchestrator.db
    category_names = {c["name"] for c in fake_db.categories.docs.values()}
    assert category_names == {"Tiles"}  # NOT the 12 sanitary categories too


def test_sanitary_row_still_auto_creates_its_own_category_generically(_patch_db_and_uploads):
    job = {
        "id": "job-cat-2", "supplier_name": "Grohe", "floor_id": "first-floor",
        "rows": [{
            "row_id": "r1", "status": "accepted", "sku": "SKU-FCT-1", "mrp": 1500.0,
            "category": "Faucets", "name": "Test Faucet",
        }],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="first-floor"))
    fake_db = orchestrator.db
    category_names = {c["name"] for c in fake_db.categories.docs.values()}
    assert category_names == {"Faucets"}  # only what the row actually needed, not all 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_catalog_import_no_category_pollution.py -v`
Expected: FAIL — `test_importing_a_tiles_row...` fails because `category_names` is `{"Tiles", "Faucets", "Basins", "Water Closets", "Showers", "Bathtubs", "Accessories", "Flush Plates", "Urinals", "Kitchen Sinks", "Concealed Cisterns", "Bidets", "Thermostats"}` (13 categories, not 1).

- [ ] **Step 3: Remove the pre-seed loop**

In `backend/catalog_pipeline/orchestrator.py`, delete lines 151-158:

```python
    cats = await db.categories.find({"floor_id": floor_id}, {"_id": 0}).to_list(80)
    cat_by_name = {c["name"].lower(): c for c in cats}
    # Autocreate categories that don't exist yet (only for allowed labels)
    from catalog_pipeline.base import ALLOWED_CATEGORIES
    from models import Category
    for label in ALLOWED_CATEGORIES:
        if label.lower() not in cat_by_name:
            c = Category(name=label, slug=label.lower().replace(" ", "-"), floor_id=floor_id)
            await db.categories.insert_one(c.dict())
            cat_by_name[label.lower()] = c.dict()
```

Replace with just:

```python
    cats = await db.categories.find({"floor_id": floor_id}, {"_id": 0}).to_list(80)
    cat_by_name = {c["name"].lower(): c for c in cats}
    from models import Category
```

(`Category` is still needed a few lines below in the per-row auto-create block at line 189; `ALLOWED_CATEGORIES` is no longer imported here since nothing in this function references it anymore.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_catalog_import_no_category_pollution.py -v`
Expected: PASS

- [ ] **Step 5: Run the full existing unit suite to confirm zero regressions**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit -v`
Expected: PASS — `test_catalog_import_resilience.py`'s fixtures pre-seed their own `Faucets` category directly in `_FakeDb.__init__`, so they never depended on the eager pre-seed loop.

- [ ] **Step 6: Commit**

```bash
git add backend/catalog_pipeline/orchestrator.py backend/tests/unit/test_catalog_import_no_category_pollution.py
git commit -m "fix: stop pre-seeding sanitary-only categories onto every imported floor"
```

---

### Task 3: Add an `optimize` opt-out to the image extraction pipeline

**Files:**
- Modify: `backend/catalog_pipeline/image_extractor.py:287,333,470,590`
- Test: `backend/tests/unit/test_image_extractor_optimize_flag.py`

**Interfaces:**
- Produces: `_decode_supplier_image(raw: bytes, ext: str, *, optimize: bool = True) -> Optional[ExtractedImage]` and `extract_images_from_xlsx_ex(xlsx_bytes: bytes, *, optimize: bool = True) -> Iterator[tuple[str, int, int, ExtractedImage]]` — both keep their existing positional signature and default to the current behavior, so every existing caller (Hansgrohe, Vitra, Oyster adapters; `extract_images_from_pdf_ex`) is unaffected. Consumed by Task 4 (`QutoneAdapter` passes `optimize=False`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_image_extractor_optimize_flag.py
"""The pipeline always resizes-to-1024px + recompresses (JPEG q=82 / WebP
q=80) any image over 60KB or with alpha (image_extractor.py::_optimize,
called unconditionally from _decode_supplier_image). Qutone's explicit
requirement is "preserve original quality, do not compress, do not
resize" — this proves the new opt-out actually bypasses that step, and
that the default (used by every existing brand) is unchanged."""
from __future__ import annotations
import base64
import hashlib
import io

from PIL import Image

from catalog_pipeline.image_extractor import _decode_supplier_image


def _make_large_jpeg_bytes(size=(2000, 2000)) -> bytes:
    im = Image.new("RGB", size, color=(120, 60, 200))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _decode_data_url(data_url: str) -> bytes:
    _, b64 = data_url.split(",", 1)
    return base64.b64decode(b64)


def test_optimize_true_resizes_and_recompresses_large_images():
    raw = _make_large_jpeg_bytes()
    result = _decode_supplier_image(raw, "jpeg", optimize=True)
    assert result is not None
    assert max(result.width, result.height) == 2000  # probed dims always describe the SOURCE, pre-optimize
    stored = _decode_data_url(result.data_url)
    stored_im = Image.open(io.BytesIO(stored))
    assert max(stored_im.size) <= 1024
    assert len(stored) < len(raw)


def test_optimize_false_preserves_original_bytes_exactly():
    raw = _make_large_jpeg_bytes()
    result = _decode_supplier_image(raw, "jpeg", optimize=False)
    assert result is not None
    assert max(result.width, result.height) == 2000
    stored = _decode_data_url(result.data_url)
    assert stored == raw
    assert result.sha1 == hashlib.sha1(raw).hexdigest()[:16]


def test_optimize_defaults_to_true_for_backward_compatibility_with_existing_brands():
    raw = _make_large_jpeg_bytes()
    result_default = _decode_supplier_image(raw, "jpeg")
    result_explicit_true = _decode_supplier_image(raw, "jpeg", optimize=True)
    assert result_default.bytes_len == result_explicit_true.bytes_len
    assert result_default.bytes_len < len(raw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_image_extractor_optimize_flag.py -v`
Expected: FAIL with `TypeError: _decode_supplier_image() got an unexpected keyword argument 'optimize'`

- [ ] **Step 3: Add the `optimize` parameter**

In `backend/catalog_pipeline/image_extractor.py`, change the `_decode_supplier_image` signature (line 287) and the unconditional optimize call (line 333):

```python
def _decode_supplier_image(raw: bytes, ext: str, *, optimize: bool = True) -> Optional[ExtractedImage]:
```

```python
    # Optimise: cap huge photos to 1024px for storage without perceptible
    # quality loss. Never changes the reported width/height above — those
    # still describe the source. Callers that need byte-for-byte original
    # quality (e.g. the Qutone tiles adapter) pass optimize=False.
    if optimize:
        raw, mime = _optimize(raw, mime)
```

Change `extract_images_from_xlsx_ex` (line 470) to accept and forward the same flag:

```python
def extract_images_from_xlsx_ex(xlsx_bytes: bytes, *, optimize: bool = True) -> Iterator[tuple[str, int, int, ExtractedImage]]:
```

At its call site (line 590), forward the flag:

```python
                    img = _decode_supplier_image(raw, ext, optimize=optimize)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_image_extractor_optimize_flag.py -v`
Expected: PASS

- [ ] **Step 5: Run the full existing unit suite to confirm zero regressions**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit -v`
Expected: PASS — every existing caller (`extract_images_from_xlsx`, `extract_images_from_pdf_ex`, `extract_images_from_pdf_positioned`, and the Hansgrohe/Vitra/Oyster adapters) calls without the new keyword, so they keep getting `optimize=True`, identical to today.

- [ ] **Step 6: Commit**

```bash
git add backend/catalog_pipeline/image_extractor.py backend/tests/unit/test_image_extractor_optimize_flag.py
git commit -m "feat: add optimize opt-out to image extraction for brands that require original quality"
```

---

### Task 4: `QutoneAdapter` — column mapping, finish normalization, SKU generation, full `extract()`

**Files:**
- Create: `backend/catalog_pipeline/adapters/qutone.py`
- Test: `backend/tests/unit/test_qutone_adapter.py`

**Interfaces:**
- Consumes: `MISSING`, `BrandAdapter`, `ExtractionReport`, `ProductRow`, `dedupe_iter` from `catalog_pipeline.base` (Task 1 added `ProductRow.size`); `ExtractedImage`, `extract_images_from_xlsx_ex` from `catalog_pipeline.image_extractor` (Task 3 added the `optimize` kwarg).
- Produces: `QutoneAdapter` class (subclass of `BrandAdapter`), plus module-level helpers `normalize_finish(raw: str) -> tuple[str|None, str|None, str|None]`, `parse_rate_per_sqft(raw) -> tuple[float|None, str|None]`, `sku_for(series: str, name: str, size: str, finish_code: str) -> str`, `family_key_for(series: str, name: str) -> str` — consumed by Task 7's runner script and Task 6's integration tests.

Confirmed source layout (via direct inspection of the real file — `openpyxl.load_workbook('QUTONE 2026.xlsx', data_only=True)`, sheet `Sheet1`, 453 rows × 10 cols):
- Row 1 headers: `SR.`, `company NAME`, `PRODUCT NAME`, `IMAGE`, `PRODUCT SIZE`, `SERIES NAME`, `FINISHES`, `BOX IN PIS`, `BOX SQFT`, `RATE`.
- Rows 2-453: one row per (series, product name, size, finish) combination — all 452 combinations are unique.
- `RATE` is always the string pattern `"<number> PER SQFT"` (e.g. `"225 PER SQFT"`) — 452/452 rows match.
- Embedded images: 403 JPEGs anchored in column D ("IMAGE"), all 240×360px, one per row, zero rows with more than one image. The remaining 49 rows (the file's last 49 data rows) have no image at all.
- 6 distinct `FINISHES` values observed: `MATT` (227), `GLOSSY` (189), `CHIFFON` (22), `DOVE` (9), `SILK` (3), `STRUCTURE-MATT` (2).
- `company NAME` is `"QUTONE"` on every row (same as the brand itself).

- [ ] **Step 1: Write the failing tests for mapping/normalization/SKU generation**

```python
# backend/tests/unit/test_qutone_adapter.py
from catalog_pipeline.adapters.qutone import normalize_finish, parse_rate_per_sqft, sku_for, family_key_for
from catalog_pipeline.base import MISSING


def test_normalize_finish_covers_all_six_observed_supplier_values():
    cases = {
        "MATT": "Matt", "GLOSSY": "Glossy", "CHIFFON": "Chiffon",
        "DOVE": "Dove", "SILK": "Silk", "STRUCTURE-MATT": "Structure Matt",
        "matt": "Matt",  # case-insensitive
        " GLOSSY ": "Glossy",  # whitespace-tolerant
    }
    for raw, expected_label in cases.items():
        label, code, note = normalize_finish(raw)
        assert label == expected_label, f"{raw!r} -> {label!r}, expected {expected_label!r}"
        assert code and code.isupper()
        assert note is None


def test_normalize_finish_flags_unrecognized_values_for_manual_review():
    label, code, note = normalize_finish("SOME NEW FINISH NOBODY HAS SEEN")
    assert label is None
    assert code is None
    assert note and "manual review" in note.lower()


def test_parse_rate_per_sqft_handles_the_real_source_format():
    assert parse_rate_per_sqft("225 PER SQFT") == (225.0, None)
    assert parse_rate_per_sqft("160 per sqft") == (160.0, None)
    assert parse_rate_per_sqft("1,250 PER SQFT") == (1250.0, None)


def test_parse_rate_per_sqft_flags_unrecognized_formats_without_crashing():
    value, note = parse_rate_per_sqft("TBD")
    assert value is None
    assert note and "RATE" in note


def test_sku_and_family_key_are_deterministic_across_calls():
    sku1 = sku_for("IMARBLE 2.0", "PANAMA DOVE", "1200X2400", "MT")
    sku2 = sku_for("IMARBLE 2.0", "PANAMA DOVE", "1200X2400", "MT")
    assert sku1 == sku2 == "QUTONE-IMARBLE20-PANAMADOVE-1200X2400-MT"

    fk1 = family_key_for("IMARBLE 2.0", "PANAMA DOVE")
    fk2 = family_key_for("IMARBLE 2.0", "PANAMA DOVE")
    assert fk1 == fk2 == "qutone:imarble-2-0:panama-dove"


def test_sku_differs_by_size_and_finish_within_same_family():
    base = sku_for("IMARBLE 2.0", "PANAMA DOVE", "1200X2400", "MT")
    diff_finish = sku_for("IMARBLE 2.0", "PANAMA DOVE", "1200X2400", "GL")
    diff_size = sku_for("IMARBLE 2.0", "PANAMA DOVE", "1200X1800", "MT")
    assert len({base, diff_finish, diff_size}) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_qutone_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'catalog_pipeline.adapters.qutone'`

- [ ] **Step 3: Write the adapter — mapping, normalization, SKU generation**

```python
# backend/catalog_pipeline/adapters/qutone.py
"""QUTONE XLSX adapter (Ground Floor > Tiles).

Ships as a single workbook, single sheet, one row per (series, product name,
size, finish) combination:

  Row 1  : column headers (SR., company NAME, PRODUCT NAME, IMAGE,
           PRODUCT SIZE, SERIES NAME, FINISHES, BOX IN PIS, BOX SQFT, RATE)
  Row 2+ : one row per size/finish variant. The embedded product photo
           floats over the "IMAGE" cell of that exact row — verified 1:1
           row anchoring (zero rows with more than one image), so
           row+column anchor matching is safe here.

Rules:
* Brand is always "Qutone"; category is always "Tiles" (this brand only
  ever ships tile pricelists — a brand adapter encoding its own known
  category is the same pattern every existing adapter already uses, e.g.
  Oyster's `COLLECTION_NAME = "Brook"`).
* No SKU/article code exists anywhere in the source. Verified unique across
  all 452 real rows: (SERIES NAME, PRODUCT NAME, PRODUCT SIZE, FINISHES).
  SKU is therefore synthesized, deterministic:
  `QUTONE-{SERIES_COMPACT}-{NAME_COMPACT}-{SIZE_COMPACT}-{FINISH_CODE}` —
  same inputs always regenerate the same SKU (required for idempotency). A
  handful of rows in a future refreshed file could repeat a listing — the
  first occurrence keeps the plain SKU and each repeat gets a numeric
  suffix (`-2`, `-3`, ...), matching the Oyster adapter's convention, so it
  still imports as its own product instead of being dropped.
* "FINISHES" is normalized via an explicit FINISH_LOOKUP table (not fuzzy
  regex) built from the 6 distinct raw strings actually observed in the
  real file. Anything new is flagged for manual review, never guessed.
* Family key groups sibling size/finish variants of the same product within
  the same series: `qutone:{series_slug}:{name_slug}`.
* "RATE" is the only price the source provides (format "<number> PER
  SQFT") — used for both `mrp` and `dealer_price`/`price`, since there is
  no separate MRP tier in this source (inventing one would be
  fabrication). A row whose RATE doesn't match the expected format is
  flagged `needs_pricing` and imported at ₹0 rather than held back.
* Column positions are discovered from the header row text, not hardcoded
  letters/indices — tolerant of the source file being re-exported with
  columns in a different order on a future refresh.
"""
from __future__ import annotations
import io
import re

from ..base import MISSING, BrandAdapter, ExtractionReport, ProductRow, dedupe_iter
from ..image_extractor import ExtractedImage, extract_images_from_xlsx_ex

BRAND = "Qutone"
CATEGORY = "Tiles"

# Explicit lookup, not regex guessing — built from the 6 distinct raw
# "FINISHES" cell values actually present in the real source file
# (verified by direct inspection before writing this table).
FINISH_LOOKUP: dict[str, tuple[str, str]] = {
    "MATT": ("Matt", "MT"),
    "GLOSSY": ("Glossy", "GL"),
    "CHIFFON": ("Chiffon", "CH"),
    "DOVE": ("Dove", "DV"),
    "SILK": ("Silk", "SK"),
    "STRUCTURE-MATT": ("Structure Matt", "SM"),
}

_RATE_RE = re.compile(r"^\s*([\d,]+(?:\.\d+)?)\s*PER\s*SQFT\s*$", re.I)


def normalize_finish(raw: str) -> tuple[str | None, str | None, str | None]:
    """Returns (finish_label, finish_code, note). `note` is set only when the
    value is unrecognized (needs manual review) — callers should surface it
    rather than silently swallowing it."""
    s = re.sub(r"\s+", " ", str(raw or "").replace("\xa0", " ")).strip().upper()
    hit = FINISH_LOOKUP.get(s)
    if hit:
        return hit[0], hit[1], None
    return None, None, f"unrecognized finish {raw!r} — needs manual review"


def parse_rate_per_sqft(raw) -> tuple[float | None, str | None]:
    """Returns (price_per_sqft, note). `note` is set when the source RATE
    cell doesn't match the expected "<number> PER SQFT" format — the row
    still imports (at ₹0, flagged needs_pricing), never dropped."""
    s = str(raw or "").strip()
    m = _RATE_RE.match(s)
    if not m:
        return None, f"unrecognized RATE format {raw!r} — expected '<number> PER SQFT'"
    try:
        return float(m.group(1).replace(",", "")), None
    except ValueError:
        return None, f"unrecognized RATE format {raw!r} — expected '<number> PER SQFT'"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _compact(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def family_key_for(series: str, name: str) -> str:
    return f"qutone:{_slug(series)}:{_slug(name)}"


def sku_for(series: str, name: str, size: str, finish_code: str) -> str:
    series_c = _compact(series)[:24] or "SERIES"
    name_c = _compact(name)[:32] or "PRODUCT"
    size_c = _compact(size)[:16] or "SIZE"
    return f"QUTONE-{series_c}-{name_c}-{size_c}-{finish_code}"


def _fmt_pcs(v) -> str | None:
    if v == MISSING or v is None:
        return None
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(f)
    except (TypeError, ValueError):
        return str(v)


def _find_header_row(all_rows: list[list]) -> int:
    for i, r in enumerate(all_rows[:5]):
        cells = [str(c or "").lower().strip() for c in r]
        if any("product name" in c for c in cells):
            return i
    return 0


def _build_col_map(header_row: list) -> dict[str, int]:
    col_map: dict[str, int] = {}
    for c, val in enumerate(header_row):
        key = str(val or "").lower().strip()
        if not key:
            continue
        if "company" in key:
            col_map["company"] = c
        elif "product name" in key:
            col_map["name"] = c
        elif key == "image" or "image" in key:
            col_map["image"] = c
        elif "size" in key:
            col_map["size"] = c
        elif "series" in key:
            col_map["series"] = c
        elif "finish" in key:
            col_map["finish"] = c
        elif "box" in key and ("pc" in key or "pis" in key):
            col_map["pcs_per_box"] = c
        elif "box" in key and "sqft" in key:
            col_map["sqft_per_box"] = c
        elif "rate" in key:
            col_map["rate"] = c
    return col_map
```

- [ ] **Step 4: Run tests to verify the mapping/normalization/SKU tests pass**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_qutone_adapter.py -v -k "not extract"`
Expected: PASS (the `extract()`-based tests from Step 5 don't exist yet, so filter them out for now)

- [ ] **Step 5: Write the failing tests for full `extract()`**

Append to `backend/tests/unit/test_qutone_adapter.py`:

```python
import io

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

from catalog_pipeline.adapters.qutone import QutoneAdapter


def _build_workbook(*, with_image_on_row2: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["SR.", "company NAME", "PRODUCT NAME", "IMAGE", "PRODUCT SIZE", "SERIES NAME", "FINISHES", "BOX IN PIS", "BOX SQFT", "RATE"])
    ws.append([1, "QUTONE", "PANAMA DOVE", None, "1200X2400", "IMARBLE 2.0", "MATT", 1, 31, "225 PER SQFT"])
    ws.append([2, "QUTONE", "PANAMA DOVE", None, "1200X2400", "IMARBLE 2.0", "GLOSSY", 1, 31, "225 PER SQFT"])
    ws.append([3, "QUTONE", "PANAMA DOVE", None, "1200X1800", "IMARBLE 2.0", "WEIRDFINISH", 2, 46.5, "160 PER SQFT"])
    ws.append([4, "QUTONE", "PANAMA SAINT", None, "1200X2400", "IMARBLE 2.0", "MATT", 1, 31, "not a rate"])

    if with_image_on_row2:
        buf = io.BytesIO()
        PILImage.new("RGB", (240, 360), color=(200, 100, 50)).save(buf, format="JPEG")
        buf.seek(0)
        img = XLImage(buf)
        img.anchor = "D2"
        ws.add_image(img)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_extracts_all_rows_with_deterministic_sku():
    data = _build_workbook()
    rows, report = QutoneAdapter().extract(data, "QUTONE 2026.xlsx")
    assert report.parsed_rows == 4
    assert len(rows) == 4
    rows2, _ = QutoneAdapter().extract(data, "QUTONE 2026.xlsx")
    assert [r.sku for r in rows] == [r.sku for r in rows2]


def test_family_key_groups_same_product_and_series_across_finishes_and_sizes():
    data = _build_workbook()
    rows, _ = QutoneAdapter().extract(data, "QUTONE 2026.xlsx")
    dove_rows = [r for r in rows if r.name.startswith("PANAMA DOVE")]
    assert len(dove_rows) == 3
    assert len({r.family_key for r in dove_rows}) == 1
    saint = next(r for r in rows if r.name.startswith("PANAMA SAINT"))
    assert saint.family_key != dove_rows[0].family_key


def test_size_and_pricing_fields_map_correctly():
    data = _build_workbook()
    rows, _ = QutoneAdapter().extract(data, "QUTONE 2026.xlsx")
    r = rows[0]
    assert r.size == "1200X2400"
    assert r.mrp == 225.0
    assert r.dealer_price == 225.0
    assert r.specs["pcs_per_box"] == "1"
    assert r.specs["sqft_per_box"] == 31
    assert r.category == "Tiles"
    assert r.brand == "Qutone"


def test_unrecognized_finish_is_flagged_not_dropped():
    data = _build_workbook()
    rows, _ = QutoneAdapter().extract(data, "QUTONE 2026.xlsx")
    weird = next(r for r in rows if r.size == "1200X1800")
    assert weird.finish_code == MISSING
    assert any("needs manual review" in issue for issue in weird.issues)


def test_malformed_rate_is_flagged_and_priced_at_zero_not_dropped():
    data = _build_workbook()
    rows, _ = QutoneAdapter().extract(data, "QUTONE 2026.xlsx")
    saint = next(r for r in rows if r.name.startswith("PANAMA SAINT"))
    assert saint.mrp == 0.0
    assert any("RATE" in issue for issue in saint.issues)
    assert saint.specs.get("needs_pricing") is True


def test_row_without_embedded_image_is_flagged_missing():
    data = _build_workbook(with_image_on_row2=False)
    rows, report = QutoneAdapter().extract(data, "QUTONE 2026.xlsx")
    assert report.images_mapped == 0
    assert all(not r.images for r in rows)
    assert all(any("No image mapped" in issue for issue in r.issues) for r in rows)


def test_row_with_embedded_image_is_mapped_with_correct_dimensions():
    data = _build_workbook(with_image_on_row2=True)
    rows, report = QutoneAdapter().extract(data, "QUTONE 2026.xlsx")
    assert report.images_mapped == 1
    imaged = [r for r in rows if r.images]
    assert len(imaged) == 1
    assert imaged[0].image_meta[0]["width"] == 240
    assert imaged[0].image_meta[0]["height"] == 360
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_qutone_adapter.py -v -k extract`
Expected: FAIL — `QutoneAdapter` has no `extract` method yet (class doesn't exist at all).

- [ ] **Step 7: Implement `QutoneAdapter.extract()`**

Append to `backend/catalog_pipeline/adapters/qutone.py`:

```python
class QutoneAdapter(BrandAdapter):
    brand = BRAND
    supported_extensions = (".xlsx", ".xls")

    def extract(self, data: bytes, filename: str) -> tuple[list[ProductRow], ExtractionReport]:
        report = ExtractionReport(brand=self.brand, filename=filename, source_type="excel")
        rows: list[ProductRow] = []
        try:
            from openpyxl import load_workbook
        except Exception as e:  # pragma: no cover
            report.warnings.append(f"openpyxl missing: {e}")
            return rows, report

        try:
            wb = load_workbook(io.BytesIO(data), data_only=True)
        except Exception as e:
            report.warnings.append(f"xlsx open failed: {e}")
            return rows, report

        sku_counts: dict[str, int] = {}
        qrank = {"excellent": 4, "good": 3, "acceptable": 2, "poor": 1}

        for ws in wb.worksheets:
            all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
            if not all_rows:
                continue
            hdr_idx = _find_header_row(all_rows)
            col_map = _build_col_map(all_rows[hdr_idx])
            if not {"name", "size", "finish", "rate"} <= col_map.keys():
                report.warnings.append(
                    f"Sheet {ws.title!r} in {filename}: could not locate name/size/finish/rate columns"
                )
                continue

            # Images extracted with optimize=False — this brand's explicit
            # requirement is original quality, no resize/recompress.
            image_col = col_map.get("image")
            by_row: dict[int, ExtractedImage] = {}
            for sheet_name, row_idx, col_idx, img in extract_images_from_xlsx_ex(data, optimize=False):
                if sheet_name != ws.title:
                    continue
                if image_col is not None and col_idx != image_col:
                    continue
                prev = by_row.get(row_idx)
                if prev is None or (qrank.get(img.quality, 0), img.longest_edge) > (qrank.get(prev.quality, 0), prev.longest_edge):
                    by_row[row_idx] = img
            report.images_found += len(by_row)

            for r_idx, row in enumerate(all_rows[hdr_idx + 1:], start=hdr_idx + 2):
                def cell(key, _row=row):
                    idx = col_map.get(key)
                    return _row[idx] if idx is not None and idx < len(_row) else None

                name_cell, size_cell, finish_cell = cell("name"), cell("size"), cell("finish")
                if not name_cell or not size_cell or not finish_cell:
                    continue  # blank / section / trailer row

                company = str(cell("company") or "").strip()
                name = str(name_cell).strip()
                size = str(size_cell).strip()
                series = str(cell("series") or "").strip()
                finish_label, finish_code, finish_note = normalize_finish(finish_cell)
                display_finish = finish_label or str(finish_cell).strip()

                pcs_per_box = self.to_number(cell("pcs_per_box"))
                sqft_per_box = self.to_number(cell("sqft_per_box"))

                rate, rate_note = parse_rate_per_sqft(cell("rate"))
                needs_pricing = rate is None
                price = rate if rate is not None else 0.0

                family_key = family_key_for(series, name)
                base_sku = sku_for(series, name, size, finish_code or "UNK")
                occurrence = sku_counts.get(base_sku, 0) + 1
                sku_counts[base_sku] = occurrence
                sku = base_sku if occurrence == 1 else f"{base_sku}-{occurrence}"

                img = by_row.get(r_idx)
                image_urls = [img.data_url] if img else []
                image_meta = [img.to_dict()] if img else []
                image_quality = img.quality if img else "missing"
                if img:
                    report.images_mapped += 1

                pr = ProductRow(
                    brand=self.brand,
                    sku=sku,
                    name=f"{name} - {display_finish} ({size})",
                    category=CATEGORY,
                    subcategory=MISSING,
                    series=series or MISSING,
                    family_key=family_key,
                    variant=f"{size} · {display_finish}",
                    finish=finish_label or display_finish,
                    finish_code=finish_code or MISSING,
                    colour=MISSING,
                    material=MISSING,
                    dimensions=MISSING,
                    size=size,
                    description=MISSING,
                    mrp=price,
                    dealer_price=price,
                    warranty=MISSING,
                    collection=MISSING,
                    images=image_urls,
                    image_meta=image_meta,
                    image_quality=image_quality,
                    image_page=None,
                    specs={
                        "company_name": company or None,
                        "pcs_per_box": _fmt_pcs(pcs_per_box),
                        "sqft_per_box": None if sqft_per_box == MISSING else sqft_per_box,
                        "source_file": filename,
                        **({"needs_pricing": True} if needs_pricing else {}),
                        **({"duplicate_listing": True} if occurrence > 1 else {}),
                    },
                    tags=dedupe_iter([
                        CATEGORY.lower(), self.brand.lower(), (series or "").lower(), (finish_label or "").lower(),
                        *(["needs-pricing"] if needs_pricing else []),
                    ]),
                    # Confidence reflects data-quality signals only (finish
                    # recognized + price parsed) — NOT image presence, so
                    # rows with no supplier photo still auto-import instead
                    # of being held back for manual review.
                    confidence=0.95 if (finish_label and not needs_pricing) else 0.6,
                )
                if not finish_label:
                    pr.issues.append(finish_note or f"Unrecognized finish {finish_cell!r} — needs manual review")
                if needs_pricing:
                    pr.issues.append(rate_note or "Missing/unrecognized RATE in source — imported at ₹0, needs manual pricing")
                if not img:
                    pr.issues.append("No image mapped from supplier file")
                if occurrence > 1:
                    pr.issues.append(f"Duplicate listing in source file (occurrence {occurrence}) - SKU suffixed to keep as a separate product")
                rows.append(pr)

        report.parsed_rows = len(rows)
        return rows, report
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_qutone_adapter.py -v`
Expected: PASS (all tests, including the earlier mapping/SKU tests)

- [ ] **Step 9: Commit**

```bash
git add backend/catalog_pipeline/adapters/qutone.py backend/tests/unit/test_qutone_adapter.py
git commit -m "feat: add QutoneAdapter for Ground Floor Tiles catalog import"
```

---

### Task 5: Register `QutoneAdapter` in the registry and the HTTP import allowlist

**Files:**
- Modify: `backend/catalog_pipeline/adapters/__init__.py`
- Modify: `backend/routes/catalog_import_routes.py:22`

**Interfaces:**
- Consumes: `QutoneAdapter` from Task 4.
- Produces: `get_adapter("qutone")` returns a `QutoneAdapter` instance; `GET /catalog/imports/config/brands` includes `"Qutone"` — enables the existing human-review HTTP upload flow for any future Qutone pricelist refresh, not just the one-off script.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/unit/test_qutone_adapter.py
def test_qutone_is_registered_in_the_adapter_registry():
    from catalog_pipeline.adapters import get_adapter
    from catalog_pipeline.adapters.qutone import QutoneAdapter

    adapter = get_adapter("qutone")
    assert isinstance(adapter, QutoneAdapter)


def test_qutone_case_insensitive_lookup():
    from catalog_pipeline.adapters import get_adapter

    assert get_adapter("Qutone").brand == "Qutone"
    assert get_adapter("QUTONE").brand == "Qutone"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_qutone_adapter.py -v -k registered`
Expected: FAIL — `ValueError: No adapter for brand 'qutone'`

- [ ] **Step 3: Register the adapter**

In `backend/catalog_pipeline/adapters/__init__.py`, add the import and registry entry:

```python
"""Adapter registry — pick the right adapter for a brand."""
from .grohe import GroheAdapter
from .geberit import GeberitAdapter
from .vitra import VitraAdapter
from .hansgrohe import HansgroheAdapter
from .oyster import OysterAdapter
from .qutone import QutoneAdapter

REGISTRY = {
    "grohe": GroheAdapter,
    "geberit": GeberitAdapter,
    "vitra": VitraAdapter,
    # Hansgrohe (with AXOR merged as an internal collection).
    "hansgrohe": HansgroheAdapter,
    # AXOR routed to Hansgrohe adapter — same file format, brand folded.
    "axor": HansgroheAdapter,
    "oyster": OysterAdapter,
    "qutone": QutoneAdapter,
}
```

In `backend/routes/catalog_import_routes.py`, update line 22:

```python
SUPPORTED_BRANDS = ["Hansgrohe", "Axor", "Grohe", "Vitra", "Geberit", "Oyster", "Qutone"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_qutone_adapter.py -v`
Expected: PASS (full file, all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/catalog_pipeline/adapters/__init__.py backend/routes/catalog_import_routes.py backend/tests/unit/test_qutone_adapter.py
git commit -m "feat: register Qutone in the adapter registry and HTTP import allowlist"
```

---

### Task 6: Orchestrator integration — floor scoping, `size`/`specs` persistence, idempotent re-run

**Files:**
- Create: `backend/tests/unit/test_catalog_import_qutone_floor_scoping.py`

**Interfaces:**
- Consumes: `orchestrator.import_accepted()` (unchanged external signature; Tasks 1-2 changed only its internals). Exercises the full Qutone-shaped row payload end-to-end against a fake DB, the same pattern as `test_catalog_import_resilience.py`.

- [ ] **Step 1: Write the tests**

```python
# backend/tests/unit/test_catalog_import_qutone_floor_scoping.py
"""Qutone (Ground Floor Tiles) import integration — verifies the shared
orchestrator correctly floor-scopes brand/category creation and persists
the size/specs fields, with ZERO Qutone-specific code inside the
orchestrator itself (everything here is the same generic path every brand
already goes through)."""
from __future__ import annotations

import asyncio

import pytest

import catalog_pipeline.orchestrator as orchestrator


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, _n):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs: dict[str, dict] = {d["id"]: d for d in (docs or [])}

    async def find_one(self, query, *_args, **_kwargs):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return dict(doc)
        return None

    def find(self, query=None, *_args, **_kwargs):
        query = query or {}
        matched = [d for d in self.docs.values() if all(d.get(k) == v for k, v in query.items() if not isinstance(v, dict))]
        return _FakeCursor(matched)

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)

    async def insert_many(self, docs):
        for d in docs:
            d.setdefault("id", f"snap-{len(self.docs)}")
            self.docs[d["id"]] = dict(d)

    async def update_one(self, query, update):
        for doc in self.docs.values():
            if all(doc.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                doc.update(update.get("$set", {}))
                return


class _FakeDb:
    def __init__(self):
        self.brands = _FakeCollection()
        self.categories = _FakeCollection()
        self.products = _FakeCollection()
        self.catalog_import_snapshots = _FakeCollection()


@pytest.fixture(autouse=True)
def _patch_db_and_uploads(monkeypatch):
    fake_db = _FakeDb()
    monkeypatch.setattr(orchestrator, "db", fake_db)

    async def _noop_upload(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orchestrator, "_upload_supplier_images", _noop_upload)
    return fake_db


def _tile_row(row_id, sku, *, size="1200X2400", family_key="qutone:imarble-2-0:panama-dove"):
    return {
        "row_id": row_id, "status": "accepted", "sku": sku, "mrp": 225.0, "dealer_price": 225.0,
        "category": "Tiles", "name": f"Panama Dove - Matt ({size})", "series": "IMARBLE 2.0",
        "finish": "Matt", "size": size, "family_key": family_key,
        "specs": {"pcs_per_box": "1", "sqft_per_box": 31, "company_name": "QUTONE"},
    }


def test_brand_and_category_are_auto_created_scoped_to_ground_floor(_patch_db_and_uploads):
    fake_db = orchestrator.db
    job = {
        "id": "job-qutone-1", "supplier_name": "Qutone", "floor_id": "ground-floor",
        "rows": [_tile_row("r1", "QUTONE-IMARBLE20-PANAMADOVE-1200X2400-MT")],
    }

    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="ground-floor"))

    brand = next(iter(fake_db.brands.docs.values()))
    assert brand["name"] == "Qutone"
    assert brand["floor_id"] == "ground-floor"
    category = next(c for c in fake_db.categories.docs.values() if c["name"] == "Tiles")
    assert category["floor_id"] == "ground-floor"
    assert len(fake_db.categories.docs) == 1  # only Tiles — Task 2's pollution fix


def test_size_and_specs_fields_are_persisted_on_the_product(_patch_db_and_uploads):
    job = {
        "id": "job-qutone-2", "supplier_name": "Qutone", "floor_id": "ground-floor",
        "rows": [_tile_row("r1", "QUTONE-IMARBLE20-PANAMADOVE-1200X2400-MT")],
    }
    asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="ground-floor"))
    fake_db = orchestrator.db
    product = next(iter(fake_db.products.docs.values()))
    assert product["size"] == "1200X2400"
    assert product["specs"]["pcs_per_box"] == "1"
    assert product["specs"]["sqft_per_box"] == 31
    assert product["floor_id"] == "ground-floor"


def test_rerunning_the_same_job_upserts_instead_of_duplicating(_patch_db_and_uploads):
    job = {
        "id": "job-qutone-3", "supplier_name": "Qutone", "floor_id": "ground-floor",
        "rows": [_tile_row("r1", "QUTONE-IMARBLE20-PANAMADOVE-1200X2400-MT")],
    }
    stats1 = asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="ground-floor"))
    stats2 = asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="ground-floor"))

    fake_db = orchestrator.db
    assert stats1["imported"] == 1 and stats1["updated"] == 0
    assert stats2["imported"] == 0 and stats2["updated"] == 1
    assert len(fake_db.products.docs) == 1  # never duplicated


def test_different_sizes_of_the_same_family_create_separate_products(_patch_db_and_uploads):
    job = {
        "id": "job-qutone-4", "supplier_name": "Qutone", "floor_id": "ground-floor",
        "rows": [
            _tile_row("r1", "QUTONE-IMARBLE20-PANAMADOVE-1200X2400-MT", size="1200X2400"),
            _tile_row("r2", "QUTONE-IMARBLE20-PANAMADOVE-1200X1800-MT", size="1200X1800"),
        ],
    }
    stats = asyncio.run(orchestrator.import_accepted(job, user_id="user-1", floor_id="ground-floor"))
    fake_db = orchestrator.db
    assert stats["imported"] == 2
    sizes = {p["size"] for p in fake_db.products.docs.values()}
    assert sizes == {"1200X2400", "1200X1800"}
    family_keys = {p["family_key"] for p in fake_db.products.docs.values()}
    assert family_keys == {"qutone:imarble-2-0:panama-dove"}  # same family, different size variants
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit/test_catalog_import_qutone_floor_scoping.py -v`
Expected: PASS (Tasks 1-2 already made the orchestrator support everything these tests check — this task only adds coverage, no production code changes)

- [ ] **Step 3: Run the full unit suite one more time**

Run: `cd "backend" && .venv/bin/python -m pytest tests/unit -v`
Expected: PASS, all tests green.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/test_catalog_import_qutone_floor_scoping.py
git commit -m "test: add orchestrator integration coverage for the Qutone/ground-floor import path"
```

---

### Task 7: Batch import script `run_qutone_import.py`

**Files:**
- Create: `backend/scripts/run_qutone_import.py`

**Interfaces:**
- Consumes: `QutoneAdapter` (Task 4), `catalog_pipeline.certifier.validate`, `catalog_pipeline.orchestrator.import_accepted` / `_offload_row_images`, `catalog_pipeline.integrity_guard.scan_catalog`, `backend/scripts/backup_db.py::backup`, `models.CatalogImportJob`. Modeled directly on the existing `backend/scripts/run_oyster_import.py` (same shape: pre-import integrity scan → snapshot backup → extract → certify → auto-accept → `import_accepted` → post-import integrity diff → JSON report), adapted for a single source file and an explicit `floor_id="ground-floor"` override.
- Produces: `memory/qutone_qa_report.json` — the import summary (total imported, duplicates skipped, failed rows, images uploaded, missing images, validation warnings) the user's spec asks for.

- [ ] **Step 1: Write the script**

```python
# backend/scripts/run_qutone_import.py
"""Qutone brand batch importer (Ground Floor > Tiles) — processes the single
QUTONE 2026 pricelist. Safe to re-run: every row's SKU is deterministic
(series+name+size+finish), so re-running always upserts the same ~452
products instead of duplicating them.

Usage:
    python scripts/run_qutone_import.py --dry-run   # extract+validate+certify only, NO db writes
    python scripts/run_qutone_import.py              # full import (writes to Mongo + Supabase)
"""
from __future__ import annotations
import argparse
import asyncio
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from catalog_pipeline.adapters.qutone import QutoneAdapter  # noqa: E402
from catalog_pipeline.certifier import validate  # noqa: E402
from catalog_pipeline.base import MISSING  # noqa: E402
from catalog_pipeline.orchestrator import import_accepted, _offload_row_images  # noqa: E402
from catalog_pipeline.integrity_guard import scan_catalog  # noqa: E402
from db import db  # noqa: E402
from models import CatalogImportJob  # noqa: E402
from backup_db import backup as backup_db  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_FILE = REPO_ROOT / "backend" / "temp" / "qutone_source_files" / "QUTONE 2026.xlsx"
REPORT_PATH = REPO_ROOT / "memory" / "qutone_qa_report.json"

FLOOR_ID = "ground-floor"


def _auto_accept(row_objs):
    for r in row_objs:
        if (
            r.status == "pending"
            and r.confidence >= 0.85
            and r.sku not in (MISSING, None)
            and r.mrp not in (MISSING, None)
            and r.category not in (MISSING, None)
        ):
            r.status = "accepted"
    return row_objs


async def main(dry_run: bool) -> None:
    t0 = time.time()

    if not SOURCE_FILE.exists():
        print(f"ABORTING - source file not found: {SOURCE_FILE}")
        raise SystemExit(1)

    if not dry_run:
        pre_report = await scan_catalog()
        if not pre_report.ok:
            print("ABORTING — catalog integrity check FAILED before this import even started.")
            print(json.dumps(pre_report.to_public(), indent=2))
            raise SystemExit(1)
        print(f"Pre-import integrity check: PASS ({pre_report.total_products} products)")

        pre_snapshot_dir = await backup_db(["products", "product_media", "brands", "categories"])
        print(f"Pre-import snapshot: {pre_snapshot_dir}")

    adapter = QutoneAdapter()
    filename = SOURCE_FILE.name
    data = SOURCE_FILE.read_bytes()
    rows, rep = adapter.extract(data, filename)
    print(f"[{filename}] rows={rep.parsed_rows} images_mapped={rep.images_mapped}/{rep.images_found}")

    if not rows:
        print("ABORTING — extraction produced 0 rows.")
        raise SystemExit(1)

    row_objs, cert = validate(rows)
    row_objs = _auto_accept(row_objs)
    all_rows_dicts = [r.to_public() for r in row_objs]
    accepted = sum(1 for r in all_rows_dicts if r.get("status") == "accepted")
    rejected = sum(1 for r in all_rows_dicts if r.get("status") == "rejected")
    needs_review = [r for r in all_rows_dicts if r.get("status") == "pending"]
    missing_images = sum(1 for r in all_rows_dicts if not r.get("images"))

    summary = {
        "mode": "dry-run" if dry_run else "import",
        "source_file": filename,
        "extraction": {
            "rows": rep.parsed_rows, "images_found": rep.images_found,
            "images_mapped": rep.images_mapped, "warnings": rep.warnings,
        },
        "total_rows": len(all_rows_dicts),
        "accepted": accepted,
        "rejected_true_duplicates": rejected,
        "needs_manual_review": len(needs_review),
        "needs_manual_review_detail": [
            {"sku": r.get("sku"), "name": r.get("name"), "issues": r.get("issues")}
            for r in needs_review
        ],
        "missing_images_in_source": missing_images,
        "certification": cert.to_public(),
        "runtime_s": round(time.time() - t0, 1),
    }

    if dry_run:
        print("\n" + "=" * 70)
        print("DRY RUN — no database or storage writes performed")
        print("=" * 70)
        print(json.dumps(summary, indent=2, default=str)[:20000])
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nFull dry-run report written to {REPORT_PATH}")
        return

    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    media_before = await db.product_media.count_documents({"floor_id": FLOOR_ID, "source_type": "supplier"})
    cats_before = {c["name"] for c in await db.categories.find({"floor_id": FLOOR_ID}, {"_id": 0, "name": 1}).to_list(200)}

    # Offload embedded base64 images out of the row dicts into a dedicated
    # collection so the CatalogImportJob document stays well under MongoDB's
    # 16MB BSON cap (mutates all_rows_dicts in place).
    blob_map = await _offload_row_images(all_rows_dicts)

    job = CatalogImportJob(
        filename=filename,
        source_type="excel",  # type: ignore[arg-type]
        supplier_name="Qutone",
        total_rows=len(all_rows_dicts),
        accepted_rows=accepted,
        rejected_rows=rejected,
        status="classified",  # type: ignore[arg-type]
        rows=all_rows_dicts,
        created_by=(owner or {}).get("id", "system"),
        floor_id=FLOOR_ID,
    )
    doc = job.dict()
    doc["extraction"] = summary["extraction"]
    doc["certification"] = cert.to_public()
    await db.catalog_imports.insert_one(doc)
    doc.pop("_id", None)

    stats = {"imported": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    if accepted:
        stats = await import_accepted(doc, (owner or {}).get("id", "system"), blob_map=blob_map, floor_id=FLOOR_ID)
        await db.catalog_imports.update_one(
            {"id": doc["id"]},
            {"$set": {"status": "imported", "accepted_rows": stats["imported"] + stats["updated"],
                      "rejected_rows": stats["skipped"]}},
        )

    cats_after = {c["name"] for c in await db.categories.find({"floor_id": FLOOR_ID}, {"_id": 0, "name": 1}).to_list(200)}
    media_after = await db.product_media.count_documents({"floor_id": FLOOR_ID, "source_type": "supplier"})

    post_report = await scan_catalog(baseline_snapshot_dir=str(pre_snapshot_dir))
    integrity_ok = post_report.ok

    post_snapshot_dir = await backup_db(
        ["products", "product_media", "brands", "categories", "customers",
         "quotations", "purchase_orders", "payments", "followups", "users", "suppliers"]
    )

    summary.update({
        "batch_result": "SUCCESS" if integrity_ok else "FAILED — INTEGRITY VIOLATION, MANUAL REVIEW REQUIRED",
        "categories_created_on_ground_floor": sorted(cats_after - cats_before),
        "products_imported": stats["imported"],
        "products_updated": stats["updated"],
        "products_skipped": stats["skipped"],
        "products_failed": stats["failed"],
        "duplicates_skipped": rejected + stats["skipped"],
        "import_errors": stats.get("errors", []),
        "images_uploaded": media_after - media_before,
        "missing_images_final": missing_images,
        "pre_import_snapshot": str(pre_snapshot_dir),
        "post_import_snapshot": str(post_snapshot_dir),
        "integrity_guard": post_report.to_public(),
    })
    print("\n" + "=" * 70)
    print(f"IMPORT REPORT — {summary['batch_result']}")
    print("=" * 70)
    print(json.dumps(summary, indent=2, default=str)[:20000])

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    if not integrity_ok:
        print(f"\n!!! INTEGRITY GUARD FAILED — restore from {pre_snapshot_dir} if needed. !!!")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Extract+validate+certify only, no DB/storage writes")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
```

- [ ] **Step 2: Copy the source file into the repo**

The script depends on a stable in-repo path (the user's `~/Downloads/QUTONE 2026.xlsx` isn't stable — matches the existing `backend/temp/oyster_source_files/` precedent):

```bash
mkdir -p "backend/temp/qutone_source_files"
cp "/Users/yashvardhansinhjhala/Downloads/QUTONE 2026.xlsx" "backend/temp/qutone_source_files/QUTONE 2026.xlsx"
```

- [ ] **Step 3: Sanity-check the script imports and argparse work**

Run: `cd "backend" && .venv/bin/python scripts/run_qutone_import.py --help`
Expected: prints the usage line with `--dry-run`, no import errors.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/run_qutone_import.py "backend/temp/qutone_source_files/QUTONE 2026.xlsx"
git commit -m "feat: add Qutone batch import runner script and copy source pricelist into repo"
```

---

### Task 8: Dry-run verification against the real file

**Files:** none (verification only, no code changes)

- [ ] **Step 1: Run the dry-run**

Run: `cd "backend" && .venv/bin/python scripts/run_qutone_import.py --dry-run`

- [ ] **Step 2: Review `memory/qutone_qa_report.json` against expectations**

Confirm:
- `total_rows` == 452 (blank/trailer rows correctly excluded)
- `accepted` is close to 452 (all rows have a recognized finish and a parseable RATE in the real file, per the confirmed data audit — nothing should land in `needs_manual_review` unless the real file differs from what was inspected)
- `missing_images_in_source` == 49 (the file's last 49 data rows have no embedded photo)
- `certification.duplicates_sku` == 0 (all 452 `(series, name, size, finish)` combinations are unique in the real file)
- `extraction.images_mapped` == 403

If any of these diverge meaningfully from expectations, stop and investigate before proceeding — do not run the real import against a report that doesn't match what was verified during planning.

- [ ] **Step 3: Report the dry-run summary to the user and get explicit confirmation before the real import**

This is a production write: ~452 products + up to 403 images into the live `buildcon_house` Atlas DB and `forge-products` Supabase bucket. The dry-run report is the artifact to review before proceeding — summarize it for the user and wait for explicit go-ahead per Task 9.

---

### Task 9: Real import execution

**Files:** none (execution only, gated on Task 8's explicit user confirmation)

- [ ] **Step 1: Run the real import**

Run: `cd "backend" && .venv/bin/python scripts/run_qutone_import.py`

- [ ] **Step 2: Verify the printed `batch_result` is `"SUCCESS"`**

If it's the integrity-violation failure path instead, the script already printed the pre-import snapshot path to restore from — stop and report to the user rather than retrying blindly.

- [ ] **Step 3: Spot-check via the existing catalog API**

Run: `curl -s "http://127.0.0.1:8010/api/products?floor_id=ground-floor&limit=5" -H "Authorization: Bearer <token>"` (or equivalent authenticated request through whatever the current session's backend port is — see project memory for the live port) and confirm returned products have `brand_id` resolving to Qutone, `category_id` resolving to Tiles, non-empty `hero_image_url` for at least one product, and a populated `size` field.

- [ ] **Step 4: Report the final summary to the user**

Surface the final `memory/qutone_qa_report.json` contents: total products imported, duplicates skipped, failed rows, images uploaded, missing images, and validation warnings — matching the spec's required import summary exactly.
