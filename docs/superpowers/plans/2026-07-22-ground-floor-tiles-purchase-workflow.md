# Ground Floor Tiles Purchase Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Chalan-based material-release tracking (with optional Godown routing and per-batch dispatch) to Ground Floor tile purchase orders, plus Customer-wise and Company-wise order views — layered on the existing `PurchaseOrder` record with zero changes to the existing 6-stage Material Tracker.

**Architecture:** A new `Chalan` subdocument list embedded on `PurchaseOrder` (no new collection, no duplicate order records). A pure-function stage-rollup (`services/chalan_stage.py`) computes the order's customer-facing stage (`order`/`material_released`/`godown`/`dispatch`/`completed`) live from the chalans on every read — nothing is cached, so the Customer-wise view, Company-wise view, and order detail page can never disagree. New endpoints and a new PDF builder live alongside the existing Purchases Tracker code, following its established patterns exactly (`floor_query`, `log_event`, `require_min_role`, on-demand PDF generation).

**Tech Stack:** FastAPI + MongoDB (Motor) backend, Expo Router / React Native Web frontend, ReportLab for PDFs, pytest for backend unit tests (no frontend test infra exists in this repo — frontend tasks end with a manual browser-verification step instead).

**Design doc:** `docs/superpowers/specs/2026-07-22-ground-floor-tiles-purchase-workflow-design.md`

## Global Constraints

- Do not modify `backend/routes/purchases_tracker.py`'s existing 6-stage Material Tracker code, `backend/routes/purchase_routes.py`'s PO status state machine, or `services/domain_outbox.py::_handle_order_placed`. This work is purely additive.
- All new mutating endpoints use `Depends(require_min_role("warehouse"))` — the same, deliberately permissive bar the existing move/transfer/bulk-move endpoints in `purchases_tracker.py` already use (rank 30, the lowest operational role above `worker`).
- All new read endpoints use `Depends(get_current_user)` with `floor_query(user, ...)` — same pattern as every existing Purchases Tracker read endpoint.
- Chalan PDFs are generated on demand on every request, never persisted to storage — mirrors `routes/quotation_routes.py::quotation_pdf`, not the `PurchaseAttachment` Supabase-upload pattern (that pattern is for user-uploaded arbitrary files, not server-generated documents).
- In-app notifications use `await notify(...)` directly (not `asyncio.create_task`) so notification delivery is deterministic and testable — `notify()` is already best-effort/never-raises by design (`services/notifications.py`), so awaiting it directly is safe.
- Frontend token imports: use `@/src/theme/tokens` (`colors, radius, shadow, spacing, type, money, icon`) exclusively — this is what both `purchases.tsx` and `TilesDocBuilder.tsx` use. Do not import from `@/src/design/tokens` (a second, older token system also present in this repo but not what the Tiles module uses).
- Run backend tests with: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`

---

## Task 1: Chalan data model

**Files:**
- Modify: `backend/models.py` (insert before `class PurchaseOrder(TimestampedModel):` at line 662, and add one field inside that class)
- Test: `backend/tests/unit/test_models_chalan.py`

**Interfaces:**
- Produces: `ChalanLineItem(po_item_id: str, name: str, size: Optional[str], qty: float, unit: str)`, `ChalanStage = Literal["released", "at_godown", "dispatched"]`, `Chalan(id, number, created_at, created_by, created_by_name, items, reference_number, receiver_name, sender_name, stage, godown_received_at, godown_received_by, godown_received_by_name, dispatched_at, dispatched_by, dispatched_by_name, dispatch_note)`, `PurchaseOrder.chalans: list[Chalan]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_models_chalan.py`:

```python
"""Chalan model defaults — a tile order's material can be released in
multiple batches; each batch is a Chalan embedded on the PurchaseOrder
that produced it (no separate collection, no duplicate order records)."""
from __future__ import annotations

from models import Chalan, ChalanLineItem, PurchaseOrder


def test_chalan_defaults_to_released_stage():
    chalan = Chalan(
        number="CH-0001", created_by="u1", created_by_name="Test User",
        items=[ChalanLineItem(po_item_id="item-1", name="Glossy Ivory", size="600X600", qty=10, unit="Box")],
    )
    assert chalan.stage == "released"
    assert chalan.id
    assert chalan.created_at
    assert chalan.items[0].qty == 10
    assert chalan.godown_received_at is None
    assert chalan.dispatched_at is None


def test_purchase_order_defaults_to_no_chalans():
    po = PurchaseOrder(
        number="FPO-0001", customer_id="c1", customer_name="Test Customer",
        created_by="u1", created_by_name="Test User",
    )
    assert po.chalans == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_models_chalan.py -v`
Expected: FAIL with `ImportError: cannot import name 'Chalan' from 'models'`

- [ ] **Step 3: Add the models**

In `backend/models.py`, insert this immediately before `class PurchaseOrder(TimestampedModel):` (currently line 662):

```python
class ChalanLineItem(BaseModel):
    """One product line within a single material-release batch — a subset
    (or all) of a PurchaseOrderItem's quantity."""
    po_item_id: str          # references PurchaseOrderItem.id this batch covers
    name: str
    size: Optional[str] = None
    qty: float
    unit: str = "Box"        # "Box" | "PCS" — free text, printed as-is


ChalanStage = Literal["released", "at_godown", "dispatched"]


class Chalan(BaseModel):
    """A Delivery Release Receipt — proof that this batch of material was
    released from the supplier's factory. Embedded on PurchaseOrder.chalans
    (not a separate collection) so there is exactly one order document and
    nothing to keep in sync between views."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    number: str                              # "CH-1052"
    created_at: str = Field(default_factory=now_iso)
    created_by: str
    created_by_name: str
    items: list[ChalanLineItem] = []
    reference_number: Optional[str] = None
    receiver_name: Optional[str] = None
    sender_name: Optional[str] = None        # "Supplier Representative"
    stage: ChalanStage = "released"
    godown_received_at: Optional[str] = None
    godown_received_by: Optional[str] = None
    godown_received_by_name: Optional[str] = None
    dispatched_at: Optional[str] = None
    dispatched_by: Optional[str] = None
    dispatched_by_name: Optional[str] = None
    dispatch_note: Optional[str] = None


```

Then, inside `class PurchaseOrder(TimestampedModel):`, add one field after the existing `assigned_to_name: Optional[str] = None` line:

```python
    assigned_to_name: Optional[str] = None
    chalans: list[Chalan] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_models_chalan.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/models.py backend/tests/unit/test_models_chalan.py && git commit -m "feat: add Chalan model for tile order material-release tracking"
```

---

## Task 2: Stage-rollup pure functions

**Files:**
- Create: `backend/services/chalan_stage.py`
- Test: `backend/tests/unit/test_chalan_stage.py`

**Interfaces:**
- Consumes: raw `dict` shapes of `PurchaseOrder`/`Chalan`/`PurchaseOrderItem` (as stored in Mongo, not Pydantic instances — matches how the rest of `purchases_tracker.py` works with `dict`s straight off `find_one`)
- Produces: `remaining_qty_by_item(po: dict) -> dict[str, float]`, `is_fully_released(po: dict) -> bool`, `compute_order_stage(po: dict) -> str` (one of `"order"`, `"material_released"`, `"godown"`, `"dispatch"`, `"completed"`)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_chalan_stage.py`:

```python
"""Pure-function tests for the tile order stage rollup — no DB, no FastAPI,
just dicts in and a stage string out. See design doc's "Data model" section
for the exact stage semantics this implements."""
from __future__ import annotations

from services.chalan_stage import compute_order_stage, is_fully_released, remaining_qty_by_item


def _po(items, chalans):
    return {"items": items, "chalans": chalans}


def test_order_stage_no_chalans_yet():
    po = _po([{"id": "i1", "qty": 10}], [])
    assert compute_order_stage(po) == "order"
    assert remaining_qty_by_item(po) == {"i1": 10.0}


def test_order_stage_partial_release_stays_order():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [{"stage": "released", "items": [{"po_item_id": "i1", "qty": 4}]}],
    )
    assert compute_order_stage(po) == "order"
    assert remaining_qty_by_item(po) == {"i1": 6.0}
    assert is_fully_released(po) is False


def test_order_stage_material_released_when_single_chalan_covers_everything():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [{"stage": "released", "items": [{"po_item_id": "i1", "qty": 10}]}],
    )
    assert is_fully_released(po) is True
    assert compute_order_stage(po) == "material_released"


def test_order_stage_material_released_when_multiple_chalans_sum_to_full_qty():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [
            {"stage": "released", "items": [{"po_item_id": "i1", "qty": 6}]},
            {"stage": "released", "items": [{"po_item_id": "i1", "qty": 4}]},
        ],
    )
    assert compute_order_stage(po) == "material_released"


def test_order_stage_multi_item_order_not_fully_released_until_every_item_covered():
    po = _po(
        [{"id": "i1", "qty": 10}, {"id": "i2", "qty": 5}],
        [{"stage": "released", "items": [{"po_item_id": "i1", "qty": 10}]}],
    )
    # i2 has zero released qty — order stays "order" even though i1 is fully covered
    assert compute_order_stage(po) == "order"
    assert remaining_qty_by_item(po) == {"i1": 0.0, "i2": 5.0}


def test_order_stage_godown_when_any_batch_at_godown():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [
            {"stage": "at_godown", "items": [{"po_item_id": "i1", "qty": 6}]},
            {"stage": "released", "items": [{"po_item_id": "i1", "qty": 4}]},
        ],
    )
    assert compute_order_stage(po) == "godown"


def test_order_stage_dispatch_when_any_batch_dispatched_but_not_all():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [
            {"stage": "dispatched", "items": [{"po_item_id": "i1", "qty": 6}]},
            {"stage": "at_godown", "items": [{"po_item_id": "i1", "qty": 4}]},
        ],
    )
    assert compute_order_stage(po) == "dispatch"


def test_order_stage_completed_when_every_chalan_dispatched():
    po = _po(
        [{"id": "i1", "qty": 10}],
        [
            {"stage": "dispatched", "items": [{"po_item_id": "i1", "qty": 6}]},
            {"stage": "dispatched", "items": [{"po_item_id": "i1", "qty": 4}]},
        ],
    )
    assert compute_order_stage(po) == "completed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_chalan_stage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.chalan_stage'`

- [ ] **Step 3: Write the implementation**

Create `backend/services/chalan_stage.py`:

```python
"""Pure functions computing a tile order's customer-facing delivery stage
from its embedded chalans. No DB access — the caller passes the raw
PurchaseOrder dict (as read from Mongo) and gets a stage string back. See
docs/superpowers/specs/2026-07-22-ground-floor-tiles-purchase-workflow-design.md
for the stage semantics.

Stages: "order" -> "material_released" -> "godown" -> "dispatch" -> "completed".
Godown is optional — a chalan can go released -> dispatched directly, or
released -> at_godown -> dispatched. The order-level stage reflects the
FURTHEST progress reached by any chalan (not the weakest), except that
"completed" requires every chalan to be dispatched.
"""
from __future__ import annotations


def remaining_qty_by_item(po: dict) -> dict[str, float]:
    """{po_item_id: qty not yet covered by any chalan}, one entry per item
    on the order."""
    totals = {item["id"]: float(item.get("qty") or 0) for item in po.get("items", [])}
    released: dict[str, float] = {}
    for chalan in po.get("chalans", []):
        for line in chalan.get("items", []):
            item_id = line["po_item_id"]
            released[item_id] = released.get(item_id, 0.0) + float(line.get("qty") or 0)
    return {
        item_id: round(max(0.0, total - released.get(item_id, 0.0)), 4)
        for item_id, total in totals.items()
    }


def is_fully_released(po: dict) -> bool:
    """True once every item's quantity is covered by cumulative chalans."""
    remaining = remaining_qty_by_item(po)
    return all(qty <= 1e-6 for qty in remaining.values())


def compute_order_stage(po: dict) -> str:
    chalans = po.get("chalans") or []
    if not chalans or not is_fully_released(po):
        return "order"
    if all(c.get("stage") == "dispatched" for c in chalans):
        return "completed"
    if any(c.get("stage") == "dispatched" for c in chalans):
        return "dispatch"
    if any(c.get("stage") == "at_godown" for c in chalans):
        return "godown"
    return "material_released"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_chalan_stage.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/services/chalan_stage.py backend/tests/unit/test_chalan_stage.py && git commit -m "feat: add pure-function stage rollup for tile order chalans"
```

---

## Task 3: Chalan PDF builder

**Files:**
- Create: `backend/pdf_chalan.py`
- Test: `backend/tests/unit/test_pdf_chalan.py`

**Interfaces:**
- Consumes: `pdf_generator.LOGO_PATH`, `pdf_generator._escape`, `pdf_tiles._logo_flowable`, `pdf_tiles.DEFAULT_ADDRESS`, `pdf_tiles.DEFAULT_EMAIL`, `pdf_tiles.DEFAULT_MOBILE` (all already exist)
- Produces: `build_chalan_pdf(chalan: dict, po: dict, customer: dict, branding: dict | None = None) -> bytes`, `chalan_pdf_filename(chalan: dict, customer_name: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_pdf_chalan.py`:

```python
"""Smoke tests for the Chalan PDF builder — confirms it produces a real PDF
and the exact filename format the spec requires, not full visual/layout
correctness (matches this repo's existing PDF test coverage, i.e. none —
this is new, minimal, valuable coverage)."""
from __future__ import annotations

from pdf_chalan import build_chalan_pdf, chalan_pdf_filename


def _chalan():
    return {
        "number": "CH-1052", "created_at": "2026-07-22T10:00:00+00:00",
        "items": [{"po_item_id": "i1", "name": "Glossy Ivory", "size": "600X600", "qty": 40, "unit": "Box"}],
        "receiver_name": "Nileshbhai Pokiya", "sender_name": "Kajaria Rep",
        "reference_number": "REF-9",
    }


def _po():
    return {"customer_name": "Nileshbhai Pokiya", "supplier_name": "Kajaria"}


def _customer():
    return {"phone": "+91 98765 43210"}


def test_build_chalan_pdf_returns_pdf_bytes():
    pdf_bytes = build_chalan_pdf(_chalan(), _po(), _customer())
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")


def test_build_chalan_pdf_handles_missing_optional_fields():
    chalan = {"number": "CH-0001", "created_at": "2026-07-22T10:00:00+00:00", "items": []}
    pdf_bytes = build_chalan_pdf(chalan, {}, {})
    assert pdf_bytes.startswith(b"%PDF")


def test_chalan_pdf_filename_format():
    filename = chalan_pdf_filename(_chalan(), "Nileshbhai Pokiya")
    assert filename == "CH-1052 Nileshbhai Pokiya 22-07-2026.pdf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_pdf_chalan.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pdf_chalan'`

- [ ] **Step 3: Write the implementation**

Create `backend/pdf_chalan.py`:

```python
"""Chalan (Delivery Release Receipt) PDF — proof that ordered tile material
has been released from the supplier's factory. Generated fresh on every
request from a PurchaseOrder's embedded Chalan subdocument, the same way
quotation PDFs are generated on demand with nothing persisted to storage
(see routes/quotation_routes.py::quotation_pdf).
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pdf_generator import LOGO_PATH, _escape  # noqa: F401 — LOGO_PATH kept for parity with pdf_tiles imports
from pdf_tiles import DEFAULT_ADDRESS, DEFAULT_EMAIL, DEFAULT_MOBILE, _logo_flowable

INK = colors.HexColor("#111111")
GRID_BLACK = colors.HexColor("#000000")
HEADER_GREY = colors.HexColor("#D3D3D3")


def chalan_pdf_filename(chalan: dict, customer_name: str) -> str:
    """`CH-1052 Nileshbhai Pokiya 22-07-2026.pdf`."""
    created = (chalan.get("created_at") or "").replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(created).strftime("%d-%m-%Y")
    except ValueError:
        stamp = datetime.now().strftime("%d-%m-%Y")
    name = " ".join((customer_name or "Customer").split())
    safe = "".join(ch for ch in f"{chalan.get('number', 'CH')} {name} {stamp}" if ch not in '\\/:*?"<>|')
    return f"{safe}.pdf"


def build_chalan_pdf(chalan: dict, po: dict, customer: dict, branding: dict | None = None) -> bytes:
    b = branding or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=12 * mm,
        title=f"Chalan {chalan.get('number', '')}",
        author=b.get("footer_company_name") or "Buildcon House",
    )
    base = getSampleStyleSheet()
    styles = {
        "label": ParagraphStyle("label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=INK),
        "value": ParagraphStyle("value", parent=base["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK),
        "tableHead": ParagraphStyle("tableHead", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=INK, alignment=1),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=11, textColor=INK, alignment=1),
        "cellLeft": ParagraphStyle("cellLeft", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=11, textColor=INK),
        "footerLabel": ParagraphStyle("footerLabel", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=INK),
        "footerNote": ParagraphStyle("footerNote", parent=base["Normal"], fontName="Helvetica", fontSize=7.6, leading=10, textColor=colors.HexColor("#555555"), alignment=1),
    }

    story: list[Flowable] = []
    story.append(_logo_flowable(60))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1.2, color=INK, spaceAfter=4 * mm))

    header_rows = [
        [Paragraph("CHALAN NO:", styles["label"]), Paragraph(_escape(chalan.get("number") or ""), styles["value"]),
         Paragraph("DATE:", styles["label"]), Paragraph(_escape((chalan.get("created_at") or "")[:10]), styles["value"])],
        [Paragraph("CUSTOMER:", styles["label"]), Paragraph(_escape(po.get("customer_name") or ""), styles["value"]),
         Paragraph("SUPPLIER:", styles["label"]), Paragraph(_escape(po.get("supplier_name") or ""), styles["value"])],
        [Paragraph("PHONE:", styles["label"]), Paragraph(_escape(customer.get("phone") or ""), styles["value"]),
         Paragraph("REFERENCE:", styles["label"]), Paragraph(_escape(chalan.get("reference_number") or ""), styles["value"])],
    ]
    header = Table(header_rows, colWidths=[28 * mm, 62 * mm, 28 * mm, 62 * mm], rowHeights=[8 * mm] * 3)
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.extend([header, Spacer(1, 6 * mm)])

    head = [
        Paragraph("SR NO.", styles["tableHead"]), Paragraph("TILE NAME", styles["tableHead"]),
        Paragraph("SIZE", styles["tableHead"]), Paragraph("QUANTITY", styles["tableHead"]),
        Paragraph("UNIT", styles["tableHead"]),
    ]
    rows: list[list[object]] = [head]
    for index, item in enumerate(chalan.get("items") or [], 1):
        rows.append([
            Paragraph(str(index), styles["cell"]),
            Paragraph(_escape(item.get("name") or ""), styles["cellLeft"]),
            Paragraph(_escape(item.get("size") or ""), styles["cell"]),
            Paragraph(f"{float(item.get('qty') or 0):g}", styles["cell"]),
            Paragraph(_escape(item.get("unit") or "Box"), styles["cell"]),
        ])
    table = Table(rows, colWidths=[18 * mm, 72 * mm, 30 * mm, 30 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.9, GRID_BLACK),
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([table, Spacer(1, 14 * mm)])

    receiver_rows = [
        [Paragraph("Receiver Name:", styles["footerLabel"]), Paragraph(_escape(chalan.get("receiver_name") or ""), styles["value"])],
        [Paragraph("Receiver Signature:", styles["footerLabel"]), HRFlowable(width="60%", thickness=0.8, color=INK)],
    ]
    receiver = Table(receiver_rows, colWidths=[85 * mm, 85 * mm], rowHeights=[8 * mm, 14 * mm])
    receiver.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(receiver)
    story.append(Spacer(1, 10 * mm))

    sender_rows = [
        [Paragraph("Supplier Representative:", styles["footerLabel"]), Paragraph(_escape(chalan.get("sender_name") or ""), styles["value"])],
        [Paragraph("Sender Signature:", styles["footerLabel"]), HRFlowable(width="60%", thickness=0.8, color=INK)],
    ]
    sender = Table(sender_rows, colWidths=[85 * mm, 85 * mm], rowHeights=[8 * mm, 14 * mm])
    sender.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(sender)
    story.append(Spacer(1, 10 * mm))

    story.append(HRFlowable(width="100%", thickness=0.9, color=INK, spaceAfter=2 * mm))
    address_line = b.get("company_address") or DEFAULT_ADDRESS
    email = b.get("footer_email") or DEFAULT_EMAIL
    mobile = b.get("footer_phone") or DEFAULT_MOBILE
    story.append(Paragraph(
        f"{_escape(b.get('footer_company_name') or 'Buildcon House')} &middot; {_escape(address_line)} &middot; {_escape(email)} &middot; {_escape(mobile)}",
        styles["footerNote"],
    ))

    doc.build(story)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_pdf_chalan.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/pdf_chalan.py backend/tests/unit/test_pdf_chalan.py && git commit -m "feat: add Chalan PDF builder"
```

---

## Task 4: Generate Chalan endpoint

**Files:**
- Modify: `backend/routes/purchases_tracker.py` (imports near lines 39-50, new section before `@router.get("/export.xlsx")` at line 1434)
- Test: `backend/tests/unit/test_purchases_chalan_generation.py`

**Interfaces:**
- Consumes: `Chalan`, `ChalanLineItem` (Task 1), `remaining_qty_by_item`, `compute_order_stage` (Task 2), `next_number` (already imported in this file), `log_event` (already imported), `notify` (new import from `services.notifications`)
- Produces: `POST /purchases/{po_id}/chalans`, route function `generate_chalan`, request models `ChalanItemInput`, `GenerateChalanBody`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_purchases_chalan_generation.py`:

```python
"""Chalan generation endpoint — validates release quantities against what's
actually remaining, writes the chalan onto the PO, and notifies the order's
creator/assignee (never the customer directly — see design doc)."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user() -> UserPublic:
    return UserPublic(
        email="wh@forge.app", full_name="Warehouse Rep", role="warehouse",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


def _po(**overrides) -> dict:
    base = {
        "id": "po-1", "number": "FPO-0001", "customer_id": "cust-1",
        "customer_name": "Nileshbhai Pokiya", "created_by": "u-sales", "assigned_to": None,
        "items": [{"id": "item-1", "name": "Glossy Ivory 600x600", "finish": "600X600", "qty": 40}],
        "chalans": [],
    }
    base.update(overrides)
    return base


class _FakePOs:
    def __init__(self, po: dict | None):
        self._po = po
        self.pushed_chalan: dict | None = None
        self.update_calls = 0

    async def find_one(self, *_args, **_kwargs):
        if self._po is None:
            return None
        result = dict(self._po)
        if self.pushed_chalan:
            result["chalans"] = [self.pushed_chalan]
        return result

    async def update_one(self, _query, update):
        self.update_calls += 1
        self.pushed_chalan = update["$push"]["chalans"]


class _FakeDb:
    def __init__(self, po: dict | None):
        self.purchase_orders = _FakePOs(po)


async def _noop_log_event(**_kwargs):
    return None


async def _noop_notify(*_args, **_kwargs):
    return None


async def _fake_next_number(*_args, **_kwargs):
    return "CH-0001"


def test_generate_chalan_happy_path(monkeypatch):
    fake_db = _FakeDb(_po())
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    monkeypatch.setattr(tracker, "notify", _noop_notify)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)

    body = tracker.GenerateChalanBody(
        items=[tracker.ChalanItemInput(po_item_id="item-1", qty=15)],
        receiver_name="Nileshbhai Pokiya", sender_name="Kajaria Rep",
    )
    result = asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))

    assert result["chalan"]["number"] == "CH-0001"
    assert result["chalan"]["items"][0]["qty"] == 15
    assert result["stage"] == "order"  # only 15 of 40 released — not fully released yet
    assert fake_db.purchase_orders.update_calls == 1


def test_generate_chalan_rejects_over_release(monkeypatch):
    fake_db = _FakeDb(_po())
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "next_number", _fake_next_number)

    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=999)])
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_generate_chalan_404s_when_po_not_found(monkeypatch):
    fake_db = _FakeDb(None)
    monkeypatch.setattr(tracker, "db", fake_db)

    body = tracker.GenerateChalanBody(items=[tracker.ChalanItemInput(po_item_id="item-1", qty=1)])
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.generate_chalan("po-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_purchases_chalan_generation.py -v`
Expected: FAIL with `AttributeError: module 'routes.purchases_tracker' has no attribute 'GenerateChalanBody'`

- [ ] **Step 3: Write the implementation**

In `backend/routes/purchases_tracker.py`, update the imports block (currently lines 39-50):

```python
from auth import floor_inherit, floor_query, floor_scope_ids, get_current_user, require_min_role
from db import db
from models import (
    Chalan, ChalanLineItem, PurchaseOrder, PurchaseOrderItem, PurchaseShortage, PurchaseStageEvent, PurchaseStatusEvent,
    PURCHASE_STAGES, PurchaseStage, Quotation, QuotationLineItem, UserPublic, now_iso,
)
from routes.purchase_routes import ALLOWED_TRANSITIONS, STATUS_LABELS
from routes.quotation_routes import _next_number as _next_quotation_number, _pdf_branding
from services.activity_log import log_event, timeline_for
from services.chalan_stage import compute_order_stage, remaining_qty_by_item
from services.followup_engine import reconcile_followups
from services.notifications import notify
from services.sequence import next_number
from services.transfer_workflow import execute_transfer, transfer_history
```

Then, near the end of the file, immediately before `@router.get("/export.xlsx")` (currently line 1434), add:

```python
# =============================================================================
# Chalan / material-release workflow (Ground Floor Tiles) — see design doc
# docs/superpowers/specs/2026-07-22-ground-floor-tiles-purchase-workflow-design.md
# =============================================================================
class ChalanItemInput(BaseModel):
    po_item_id: str
    qty: float = Field(gt=0)


class GenerateChalanBody(BaseModel):
    items: list[ChalanItemInput] = Field(min_length=1)
    reference_number: Optional[str] = None
    receiver_name: Optional[str] = None
    sender_name: Optional[str] = None


@router.post("/{po_id}/chalans")
async def generate_chalan(
    po_id: str, body: GenerateChalanBody,
    user: UserPublic = Depends(require_min_role("warehouse")),
):
    """'Release Material' — generates a Chalan covering the given quantities.
    Multiple chalans can cover one order over time (batched release); the
    order only reaches the "material_released" customer-facing stage once
    every item's quantity is covered (see services/chalan_stage.py)."""
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    items_by_id = {item["id"]: item for item in po.get("items", [])}
    remaining = remaining_qty_by_item(po)
    chalan_items: list[ChalanLineItem] = []
    for entry in body.items:
        source = items_by_id.get(entry.po_item_id)
        if not source:
            raise HTTPException(status_code=400, detail=f"Unknown item {entry.po_item_id}")
        available = remaining.get(entry.po_item_id, 0.0)
        if entry.qty > available + 1e-6:
            raise HTTPException(
                status_code=400,
                detail=f"Only {available:g} of '{source.get('name')}' remains to release",
            )
        chalan_items.append(ChalanLineItem(
            po_item_id=entry.po_item_id, name=source.get("name", ""),
            size=source.get("finish"), qty=entry.qty, unit="Box",
        ))

    chalan = Chalan(
        number=await next_number("chalan", "CH", collection="purchase_orders", width=4),
        created_by=user.id, created_by_name=user.full_name,
        items=chalan_items, reference_number=body.reference_number,
        receiver_name=body.receiver_name, sender_name=body.sender_name,
    )
    now = now_iso()
    await db.purchase_orders.update_one(
        {"id": po_id},
        {"$push": {"chalans": chalan.dict()}, "$set": {"updated_at": now}},
    )
    fresh = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    stage = compute_order_stage(fresh)

    await log_event(
        event_type="purchase.chalan_generated",
        entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Generated Chalan {chalan.number} · {len(chalan_items)} item(s)",
        payload={"chalan_id": chalan.id, "chalan_number": chalan.number},
    )
    for recipient in {po.get("created_by"), po.get("assigned_to")} - {None}:
        await notify(
            recipient, "Material released by the supplier",
            body=f"Chalan {chalan.number} generated for {po.get('customer_name')} · {po.get('number')}",
            kind="success", link=f"/tiles/orders/{po_id}",
        )
    return {"po_id": po_id, "chalan": chalan.dict(), "stage": stage}


```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_purchases_chalan_generation.py -v`
Expected: PASS (3 tests)

Then run the full unit suite to confirm nothing existing broke:
Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_chalan_generation.py && git commit -m "feat: add POST /purchases/{po_id}/chalans (Release Material)"
```

---

## Task 5: Godown/Dispatch actions + Chalan PDF endpoint

**Files:**
- Modify: `backend/routes/purchases_tracker.py` (append after Task 4's `generate_chalan`)
- Test: `backend/tests/unit/test_purchases_chalan_lifecycle.py`

**Interfaces:**
- Consumes: `Chalan`/`compute_order_stage` (as above), `StreamingResponse` (already imported in this file), `build_chalan_pdf`/`chalan_pdf_filename` (Task 3), `_pdf_branding` (now imported per Task 4)
- Produces: `POST /purchases/{po_id}/chalans/{chalan_id}/godown-received` (`mark_chalan_godown_received`), `POST /purchases/{po_id}/chalans/{chalan_id}/dispatch` (`dispatch_chalan`, body model `DispatchChalanBody`), `GET /purchases/{po_id}/chalans/{chalan_id}/pdf` (`chalan_pdf`)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_purchases_chalan_lifecycle.py`:

```python
"""Godown/Dispatch chalan actions, tracked per-batch (a single order can
have some chalans dispatched while others are still at the factory or in
the godown — see design doc). Dispatch of the LAST outstanding chalan
notifies the order's creator/assignee that the order is fully complete."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user() -> UserPublic:
    return UserPublic(
        email="wh@forge.app", full_name="Warehouse Rep", role="warehouse",
        floor_ids=["ground-floor"], active_floor_id="ground-floor",
    )


def _po_with_chalan(stage: str = "released") -> dict:
    return {
        "id": "po-1", "number": "FPO-0001", "customer_id": "cust-1",
        "customer_name": "Nileshbhai Pokiya", "created_by": "u-sales", "assigned_to": "u-sales",
        "items": [{"id": "item-1", "name": "Glossy Ivory", "qty": 40}],
        "chalans": [{
            "id": "ch-1", "number": "CH-0001", "stage": stage, "created_at": "2026-07-22T10:00:00+00:00",
            "items": [{"po_item_id": "item-1", "qty": 40, "name": "Glossy Ivory", "unit": "Box"}],
        }],
    }


class _FakePOsMulti:
    """Applies `chalans.$.<field>` $set updates to the matching chalan by id
    — enough of Mongo's positional-operator semantics to test these two
    single-chalan-update endpoints without a live database."""

    def __init__(self, po: dict):
        self._po = po
        self.update_calls = 0

    async def find_one(self, *_args, **_kwargs):
        return dict(self._po)

    async def update_one(self, query, update):
        self.update_calls += 1
        chalan_id = query.get("chalans.id")
        for chalan in self._po["chalans"]:
            if chalan["id"] == chalan_id:
                for key, value in update.get("$set", {}).items():
                    if key.startswith("chalans.$."):
                        chalan[key[len("chalans.$."):]] = value


class _FakeCustomers:
    async def find_one(self, *_args, **_kwargs):
        return {"phone": "+91 98765 43210"}


class _FakeDb:
    def __init__(self, po: dict):
        self.purchase_orders = _FakePOsMulti(po)
        self.customers = _FakeCustomers()


async def _noop_log_event(**_kwargs):
    return None


def test_godown_received_transitions_stage(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)

    result = asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))

    assert result["stage"] == "godown"
    assert fake_db.purchase_orders._po["chalans"][0]["stage"] == "at_godown"


def test_godown_received_rejects_when_not_released(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("dispatched"))
    monkeypatch.setattr(tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.mark_chalan_godown_received("po-1", "ch-1", user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_dispatch_completes_order_and_notifies_when_last_chalan(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)
    monkeypatch.setattr(tracker, "log_event", _noop_log_event)
    notified: list[tuple] = []

    async def _capture_notify(*args, **kwargs):
        notified.append((args, kwargs))

    monkeypatch.setattr(tracker, "notify", _capture_notify)

    body = tracker.DispatchChalanBody(dispatch_note="Delivered by hand")
    result = asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))

    assert result["stage"] == "completed"
    assert fake_db.purchase_orders._po["chalans"][0]["stage"] == "dispatched"
    assert len(notified) == 1
    assert notified[0][0][1] == "Your tile order has been dispatched"


def test_dispatch_rejects_when_already_dispatched(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("dispatched"))
    monkeypatch.setattr(tracker, "db", fake_db)

    body = tracker.DispatchChalanBody()
    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.dispatch_chalan("po-1", "ch-1", body, user=_user()))
    assert getattr(exc.value, "status_code", None) == 400


def test_chalan_pdf_returns_pdf_response(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)

    response = asyncio.run(tracker.chalan_pdf("po-1", "ch-1", user=_user()))

    assert response.media_type == "application/pdf"


def test_chalan_pdf_404s_when_chalan_not_found(monkeypatch):
    fake_db = _FakeDb(_po_with_chalan("released"))
    monkeypatch.setattr(tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.chalan_pdf("po-1", "does-not-exist", user=_user()))
    assert getattr(exc.value, "status_code", None) == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_purchases_chalan_lifecycle.py -v`
Expected: FAIL with `AttributeError: module 'routes.purchases_tracker' has no attribute 'mark_chalan_godown_received'`

- [ ] **Step 3: Write the implementation**

In `backend/routes/purchases_tracker.py`, immediately after the `generate_chalan` function added in Task 4, add:

```python
@router.post("/{po_id}/chalans/{chalan_id}/godown-received")
async def mark_chalan_godown_received(
    po_id: str, chalan_id: str,
    user: UserPublic = Depends(require_min_role("warehouse")),
):
    """Records that this batch reached the Buildcon Godown — optional, only
    used on the "via godown" route (Route B). A chalan can also go straight
    from released to dispatched with this step skipped entirely."""
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    chalan = next((c for c in po.get("chalans", []) if c.get("id") == chalan_id), None)
    if not chalan:
        raise HTTPException(status_code=404, detail="Chalan not found")
    if chalan.get("stage") != "released":
        raise HTTPException(status_code=400, detail=f"Chalan is already {chalan.get('stage')}")

    now = now_iso()
    await db.purchase_orders.update_one(
        {"id": po_id, "chalans.id": chalan_id},
        {"$set": {
            "chalans.$.stage": "at_godown",
            "chalans.$.godown_received_at": now,
            "chalans.$.godown_received_by": user.id,
            "chalans.$.godown_received_by_name": user.full_name,
            "updated_at": now,
        }},
    )
    await log_event(
        event_type="purchase.chalan_godown_received",
        entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Chalan {chalan.get('number')} received at Godown",
        payload={"chalan_id": chalan_id},
    )
    fresh = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    return {"po_id": po_id, "chalan_id": chalan_id, "stage": compute_order_stage(fresh)}


class DispatchChalanBody(BaseModel):
    dispatch_note: Optional[str] = None


@router.post("/{po_id}/chalans/{chalan_id}/dispatch")
async def dispatch_chalan(
    po_id: str, chalan_id: str, body: DispatchChalanBody,
    user: UserPublic = Depends(require_min_role("warehouse")),
):
    """Final delivery for this batch — from the supplier directly, or from
    the Godown. When this is the LAST outstanding chalan on the order, the
    order-level stage becomes "completed" and the creator/assignee are
    notified the order has fully shipped."""
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    chalan = next((c for c in po.get("chalans", []) if c.get("id") == chalan_id), None)
    if not chalan:
        raise HTTPException(status_code=404, detail="Chalan not found")
    if chalan.get("stage") == "dispatched":
        raise HTTPException(status_code=400, detail="Chalan is already dispatched")

    now = now_iso()
    await db.purchase_orders.update_one(
        {"id": po_id, "chalans.id": chalan_id},
        {"$set": {
            "chalans.$.stage": "dispatched",
            "chalans.$.dispatched_at": now,
            "chalans.$.dispatched_by": user.id,
            "chalans.$.dispatched_by_name": user.full_name,
            "chalans.$.dispatch_note": body.dispatch_note,
            "updated_at": now,
        }},
    )
    await log_event(
        event_type="purchase.chalan_dispatched",
        entity_type="purchase", entity_id=po_id, actor=user,
        customer_id=po.get("customer_id"), purchase_id=po_id,
        summary=f"Chalan {chalan.get('number')} dispatched" + (f" · {body.dispatch_note}" if body.dispatch_note else ""),
        payload={"chalan_id": chalan_id},
    )
    fresh = await db.purchase_orders.find_one({"id": po_id}, {"_id": 0})
    stage = compute_order_stage(fresh)
    if stage == "completed":
        for recipient in {po.get("created_by"), po.get("assigned_to")} - {None}:
            await notify(
                recipient, "Your tile order has been dispatched",
                body=f"{po.get('number')} for {po.get('customer_name')} is fully dispatched",
                kind="success", link=f"/tiles/orders/{po_id}",
            )
    return {"po_id": po_id, "chalan_id": chalan_id, "stage": stage}


@router.get("/{po_id}/chalans/{chalan_id}/pdf")
async def chalan_pdf(po_id: str, chalan_id: str, user: UserPublic = Depends(get_current_user)):
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    chalan = next((c for c in po.get("chalans", []) if c.get("id") == chalan_id), None)
    if not chalan:
        raise HTTPException(status_code=404, detail="Chalan not found")
    customer = await db.customers.find_one({"id": po.get("customer_id")}, {"_id": 0, "password_hash": 0}) or {}
    from pdf_chalan import build_chalan_pdf, chalan_pdf_filename
    pdf_bytes = build_chalan_pdf(chalan, po, customer, await _pdf_branding())
    filename = chalan_pdf_filename(chalan, po.get("customer_name") or "")
    return StreamingResponse(
        iter([pdf_bytes]), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_purchases_chalan_lifecycle.py -v`
Expected: PASS (6 tests)

Then: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_chalan_lifecycle.py && git commit -m "feat: add Godown/Dispatch chalan actions and Chalan PDF endpoint"
```

---

## Task 6: Customer-wise / Company-wise / order-detail read endpoints

**Files:**
- Modify: `backend/routes/purchases_tracker.py` (append after Task 5's `chalan_pdf`)
- Test: `backend/tests/unit/test_purchases_orders_views.py`

**Interfaces:**
- Consumes: `compute_order_stage`, `remaining_qty_by_item` (Task 2)
- Produces: `GET /purchases/orders/customer-view` (`customer_view_orders`), `GET /purchases/orders/company-view` (`company_view_orders`), `GET /purchases/{po_id}/order-detail` (`order_detail`), helper `_order_card(po: dict, customer_phone: Optional[str]) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_purchases_orders_views.py`:

```python
"""Customer-wise/Company-wise order views and the order-detail endpoint —
all three read directly from `purchase_orders` (floor-scoped, same as every
other Purchases Tracker read), so there is nothing that can drift out of
sync between the two list views and the detail page."""
from __future__ import annotations

import asyncio

import pytest

from models import UserPublic
from routes import purchases_tracker as tracker


def _user(floor_id: str) -> UserPublic:
    return UserPublic(
        email="sales@forge.app", full_name="Sales", role="sales",
        floor_ids=["ground-floor", "first-floor"], active_floor_id=floor_id,
    )


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._rows


class _FakePOs:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_find_one_query = None

    def find(self, query, *_a, **_kw):
        self.last_query = query
        return _FakeCursor(self._rows)

    async def find_one(self, query, *_a, **_kw):
        self.last_find_one_query = query
        return dict(self._rows[0]) if self._rows else None


class _FakeCustomers:
    def find(self, *_a, **_kw):
        return _FakeCursor([])

    async def find_one(self, *_a, **_kw):
        return {"phone": "+91 98765 43210"}


class _FakeDb:
    def __init__(self, rows):
        self.purchase_orders = _FakePOs(rows)
        self.customers = _FakeCustomers()


def _sample_po():
    return {
        "id": "po-1", "number": "FPO-0001", "customer_id": "cust-1",
        "customer_name": "Nileshbhai Pokiya", "supplier_id": "sup-1",
        "supplier_name": "Kajaria", "status": "draft",
        "items": [{"id": "item-1", "qty": 40, "unit_cost": 55}],
        "chalans": [], "created_at": "2026-07-22T10:00:00+00:00",
    }


def test_customer_view_scopes_to_active_floor_and_shapes_cards(monkeypatch):
    fake_db = _FakeDb([_sample_po()])
    monkeypatch.setattr(tracker, "db", fake_db)

    result = asyncio.run(tracker.customer_view_orders(user=_user("ground-floor")))

    assert fake_db.purchase_orders.last_query.get("floor_id") == {"$in": ["ground-floor"]}
    assert result["orders"][0]["stage"] == "order"
    assert result["orders"][0]["total_value"] == 2200.0
    assert result["orders"][0]["total_products"] == 1


def test_company_view_groups_by_supplier(monkeypatch):
    fake_db = _FakeDb([_sample_po()])
    monkeypatch.setattr(tracker, "db", fake_db)

    result = asyncio.run(tracker.company_view_orders(user=_user("ground-floor")))

    assert fake_db.purchase_orders.last_query.get("floor_id") == {"$in": ["ground-floor"]}
    assert result["suppliers"][0]["supplier_name"] == "Kajaria"
    assert len(result["suppliers"][0]["orders"]) == 1


def test_order_detail_includes_stage_and_remaining_qty(monkeypatch):
    fake_db = _FakeDb([_sample_po()])
    monkeypatch.setattr(tracker, "db", fake_db)

    result = asyncio.run(tracker.order_detail("po-1", user=_user("ground-floor")))

    assert fake_db.purchase_orders.last_find_one_query.get("$and")[0] == {"floor_id": {"$in": ["ground-floor"]}}
    assert result["stage"] == "order"
    assert result["remaining_qty_by_item"] == {"item-1": 40.0}
    assert result["customer_phone"] == "+91 98765 43210"


def test_order_detail_404s_when_not_found(monkeypatch):
    fake_db = _FakeDb([])
    monkeypatch.setattr(tracker, "db", fake_db)

    with pytest.raises(Exception) as exc:
        asyncio.run(tracker.order_detail("po-missing", user=_user("ground-floor")))
    assert getattr(exc.value, "status_code", None) == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_purchases_orders_views.py -v`
Expected: FAIL with `AttributeError: module 'routes.purchases_tracker' has no attribute 'customer_view_orders'`

- [ ] **Step 3: Write the implementation**

In `backend/routes/purchases_tracker.py`, immediately after the `chalan_pdf` function added in Task 5, add:

```python
def _order_card(po: dict, customer_phone: Optional[str]) -> dict:
    total_value = round(sum(float(i.get("qty") or 0) * float(i.get("unit_cost") or 0) for i in po.get("items", [])), 2)
    return {
        "po_id": po["id"],
        "po_number": po.get("number"),
        "customer_id": po.get("customer_id"),
        "customer_name": po.get("customer_name"),
        "customer_phone": customer_phone,
        "supplier_id": po.get("supplier_id"),
        "supplier_name": po.get("supplier_name"),
        "status": po.get("status"),
        "stage": compute_order_stage(po),
        "total_products": len(po.get("items", [])),
        "total_value": total_value,
        "chalan_count": len(po.get("chalans", [])),
        "created_at": po.get("created_at"),
    }


@router.get("/orders/customer-view")
async def customer_view_orders(user: UserPublic = Depends(get_current_user)):
    """Order cards grouped by customer — Ground Floor Tiles Customer-wise
    view. Reads live from purchase_orders; nothing is cached or
    denormalized, so this always reflects the exact same record the
    Company-wise view and order-detail page show."""
    pos = await db.purchase_orders.find(floor_query(user), {"_id": 0}).sort("created_at", -1).to_list(2000)
    customer_ids = list({po.get("customer_id") for po in pos if po.get("customer_id")})
    customers = await db.customers.find(
        {"id": {"$in": customer_ids}}, {"_id": 0, "id": 1, "phone": 1},
    ).to_list(len(customer_ids) or 1)
    phone_by_customer = {c["id"]: c.get("phone") for c in customers}
    return {"orders": [_order_card(po, phone_by_customer.get(po.get("customer_id"))) for po in pos]}


@router.get("/orders/company-view")
async def company_view_orders(user: UserPublic = Depends(get_current_user)):
    """Same orders as customer-view, grouped by supplier instead — Ground
    Floor Tiles Company-wise view. Same underlying documents, no separate
    write path, so an update here is the exact same update the
    Customer-wise view sees."""
    pos = await db.purchase_orders.find(floor_query(user), {"_id": 0}).sort("created_at", -1).to_list(2000)
    grouped: dict[str, dict] = {}
    for po in pos:
        key = po.get("supplier_id") or "unassigned"
        bucket = grouped.setdefault(key, {
            "supplier_id": po.get("supplier_id"),
            "supplier_name": po.get("supplier_name") or "Unassigned",
            "orders": [],
        })
        bucket["orders"].append(_order_card(po, None))
    return {"suppliers": sorted(grouped.values(), key=lambda g: -len(g["orders"]))}


@router.get("/{po_id}/order-detail")
async def order_detail(po_id: str, user: UserPublic = Depends(get_current_user)):
    """Full order (items + every chalan) plus the computed stage and
    per-item remaining-to-release quantity — everything the order detail
    page and the Generate Chalan form need in one call."""
    po = await db.purchase_orders.find_one(floor_query(user, {"id": po_id}), {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    customer = await db.customers.find_one({"id": po.get("customer_id")}, {"_id": 0, "phone": 1}) or {}
    return {
        **po,
        "customer_phone": customer.get("phone"),
        "stage": compute_order_stage(po),
        "remaining_qty_by_item": remaining_qty_by_item(po),
    }


```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit/test_purchases_orders_views.py -v`
Expected: PASS (4 tests)

Then: `cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0/backend" && pytest tests/unit -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add backend/routes/purchases_tracker.py backend/tests/unit/test_purchases_orders_views.py && git commit -m "feat: add Customer-wise/Company-wise tile order views and order-detail endpoint"
```

---

## Task 7: Nav wiring

**Files:**
- Modify: `frontend/app/(admin)/_layout.tsx:145-148`

**Interfaces:**
- Consumes: `NavItem` type (already defined in this file), existing `useTilesNav()` hook (unchanged)

- [ ] **Step 1: Add the nav entry**

In `frontend/app/(admin)/_layout.tsx`, change:

```tsx
const TILES_ITEMS: NavItem[] = [
  { href: "/(admin)/tiles/selection", label: "Tiles Selection", icon: "grid", match: "selection" },
  { href: "/(admin)/tiles/quotation", label: "Tiles Quotation", icon: "layout", match: "quotation" },
];
```

to:

```tsx
const TILES_ITEMS: NavItem[] = [
  { href: "/(admin)/tiles/selection", label: "Tiles Selection", icon: "grid", match: "selection" },
  { href: "/(admin)/tiles/quotation", label: "Tiles Quotation", icon: "layout", match: "quotation" },
  { href: "/(admin)/tiles/orders", label: "Tile Orders", icon: "truck", match: "orders" },
];
```

- [ ] **Step 2: Commit**

This task has no test on its own — the route it links to doesn't exist until Task 9. Commit together with Task 9 instead of standalone; skip committing here.

---

## Task 8: TileOrderCard shared component

**Files:**
- Create: `frontend/src/components/tiles/TileOrderCard.tsx`

**Interfaces:**
- Produces: `type OrderStage`, `type OrderCard`, `StageProgress({ stage: OrderStage })`, `stageLabel(stage: OrderStage): string`, `TileOrderCard({ order: OrderCard, onPress: () => void })`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/tiles/TileOrderCard.tsx`:

```tsx
// Ground Floor → Tiles → Orders — shared order-card + 4-dot stage-progress
// indicator used by both Customer-wise and Company-wise views (index.tsx)
// and referenced by the order detail page, since all three render the exact
// same underlying order shape the backend returns.
import { Feather } from "@expo/vector-icons";
import { Pressable, Text, View } from "react-native";

import { colors, icon, money, radius, shadow, spacing, type } from "@/src/theme/tokens";

export type OrderStage = "order" | "material_released" | "godown" | "dispatch" | "completed";

export type OrderCard = {
  po_id: string;
  po_number: string;
  customer_id?: string | null;
  customer_name: string;
  customer_phone?: string | null;
  supplier_id?: string | null;
  supplier_name?: string | null;
  status: string;
  stage: OrderStage;
  total_products: number;
  total_value: number;
  chalan_count: number;
  created_at: string;
};

const STAGE_LABELS: Record<OrderStage, string> = {
  order: "Order",
  material_released: "Material Released",
  godown: "Godown",
  dispatch: "Dispatch",
  completed: "Completed",
};

// Position 0-3 on the 4-dot bar. "completed" and "dispatch" both light up
// through the last dot — only the label below distinguishes them.
const STAGE_DOT_INDEX: Record<OrderStage, number> = {
  order: 0, material_released: 1, godown: 2, dispatch: 3, completed: 3,
};

export function stageLabel(stage: OrderStage): string {
  return STAGE_LABELS[stage] || STAGE_LABELS.order;
}

export function StageProgress({ stage }: { stage: OrderStage }) {
  const activeIndex = STAGE_DOT_INDEX[stage];
  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      {[0, 1, 2, 3].map((index) => (
        <View key={index} style={{ flexDirection: "row", alignItems: "center" }}>
          <View
            style={{
              width: 9, height: 9, borderRadius: 5,
              backgroundColor: index <= activeIndex ? colors.brand : colors.border,
            }}
          />
          {index < 3 ? (
            <View style={{ width: 16, height: 2, backgroundColor: index < activeIndex ? colors.brand : colors.border }} />
          ) : null}
        </View>
      ))}
    </View>
  );
}

export function TileOrderCard({ order, onPress }: { order: OrderCard; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        {
          backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
          borderWidth: 1, borderColor: colors.border,
          padding: spacing.lg, gap: spacing.sm, opacity: pressed ? 0.85 : 1,
        },
        shadow.soft,
      ]}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={type.titleSm}>{order.customer_name}</Text>
          <Text numberOfLines={1} style={type.bodyMuted}>{order.customer_phone || "No phone on file"}</Text>
        </View>
        <Text style={type.captionStrong}>{order.po_number}</Text>
      </View>

      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Feather name="truck" size={icon.sm} color={colors.onSurfaceMuted} />
        <Text numberOfLines={1} style={[type.bodySm, { flex: 1, color: colors.onSurfaceMuted }]}>
          {order.supplier_name || "No supplier assigned"}
        </Text>
      </View>

      <View style={{ gap: spacing.xs }}>
        <StageProgress stage={order.stage} />
        <Text style={[type.captionStrong, { color: colors.brandHover }]}>{stageLabel(order.stage)}</Text>
      </View>

      <View style={{
        flexDirection: "row", justifyContent: "space-between",
        paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider,
      }}>
        <Text style={type.bodyMuted}>
          {order.total_products} product{order.total_products === 1 ? "" : "s"}
        </Text>
        <Text style={type.numeric}>{money(order.total_value)}</Text>
      </View>
    </Pressable>
  );
}
```

- [ ] **Step 2: Commit**

This component has no consumer yet — commit together with Task 9 (its first real usage) rather than standalone.

---

## Task 9: Tile Orders list page (Customer-wise / Company-wise)

**Files:**
- Create: `frontend/app/(admin)/tiles/orders/index.tsx`
- (Includes Task 7's `_layout.tsx` nav change and Task 8's `TileOrderCard.tsx` in this commit)

**Interfaces:**
- Consumes: `GET /purchases/orders/customer-view` → `{ orders: OrderCard[] }`, `GET /purchases/orders/company-view` → `{ suppliers: { supplier_id, supplier_name, orders: OrderCard[] }[] }` (Task 6), `TileOrderCard`/`OrderCard` (Task 8)

- [ ] **Step 1: Write the page**

Create `frontend/app/(admin)/tiles/orders/index.tsx`:

```tsx
// Ground Floor → Tiles → Orders — Customer-wise / Company-wise views of the
// same underlying purchase orders. Both tabs read live from the backend on
// every load; there is no separate cache, so updating an order anywhere
// (Release Material, Godown, Dispatch) is reflected in both tabs immediately.
import { Feather } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { TileOrderCard, type OrderCard } from "@/src/components/tiles/TileOrderCard";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type TabKey = "customer" | "company";

type SupplierGroup = {
  supplier_id: string | null;
  supplier_name: string;
  orders: OrderCard[];
};

export default function TileOrdersScreen() {
  const router = useRouter();
  const [tab, setTab] = useState<TabKey>("customer");
  const [loading, setLoading] = useState(true);
  const [customerOrders, setCustomerOrders] = useState<OrderCard[]>([]);
  const [supplierGroups, setSupplierGroups] = useState<SupplierGroup[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "customer") {
        const r = await api.get<{ orders: OrderCard[] }>("/purchases/orders/customer-view");
        setCustomerOrders(r.orders);
      } else {
        const r = await api.get<{ suppliers: SupplierGroup[] }>("/purchases/orders/company-view");
        setSupplierGroups(r.suppliers);
      }
    } catch (e: any) {
      toast.error(e?.detail || "Could not load orders");
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { load(); }, [load]);

  const openOrder = (poId: string) => router.push(`/(admin)/tiles/orders/${poId}` as any);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={type.overline}>GROUND FLOOR · TILES</Text>
        <Text style={type.displayMd}>Tile Orders</Text>
        <Text style={type.bodyMuted}>Track every tile order from placement to delivery.</Text>

        <View style={styles.tabRow}>
          {(["customer", "company"] as TabKey[]).map((key) => (
            <Pressable
              key={key}
              onPress={() => setTab(key)}
              style={[styles.tab, tab === key ? styles.tabActive : null]}
            >
              <Text style={[type.bodyStrong, tab === key ? { color: colors.brandHover } : null]}>
                {key === "customer" ? "Customer-wise" : "Company-wise"}
              </Text>
            </Pressable>
          ))}
        </View>

        {loading ? (
          <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brand} />
        ) : tab === "customer" ? (
          customerOrders.length === 0 ? (
            <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No tile orders yet.</Text>
          ) : (
            <View style={styles.cardGrid}>
              {customerOrders.map((order) => (
                <View key={order.po_id} style={styles.cardSlot}>
                  <TileOrderCard order={order} onPress={() => openOrder(order.po_id)} />
                </View>
              ))}
            </View>
          )
        ) : supplierGroups.length === 0 ? (
          <Text style={[type.bodyMuted, { marginTop: spacing.lg }]}>No tile orders yet.</Text>
        ) : (
          supplierGroups.map((group) => (
            <View key={group.supplier_id || "unassigned"} style={{ marginTop: spacing.xl }}>
              <View style={styles.supplierHeader}>
                <Feather name="briefcase" size={16} color={colors.onSurfaceMuted} />
                <Text style={type.titleMd}>{group.supplier_name}</Text>
                <Text style={type.bodyMuted}>
                  {group.orders.length} order{group.orders.length === 1 ? "" : "s"}
                </Text>
              </View>
              <View style={styles.cardGrid}>
                {group.orders.map((order) => (
                  <View key={order.po_id} style={styles.cardSlot}>
                    <TileOrderCard order={order} onPress={() => openOrder(order.po_id)} />
                  </View>
                ))}
              </View>
            </View>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 1120, alignSelf: "center" },
  tabRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.md },
  tab: {
    paddingVertical: spacing.sm, paddingHorizontal: spacing.lg,
    borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  tabActive: { backgroundColor: colors.brandTint, borderColor: colors.brandBorder },
  cardGrid: { flexDirection: "row", flexWrap: "wrap", marginHorizontal: -spacing.sm, marginTop: spacing.sm },
  cardSlot: { width: 340, padding: spacing.sm },
  supplierHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
});
```

- [ ] **Step 2: Manually verify in the browser**

Start (or confirm running) the backend on :8010 and the frontend dev server per `.claude/launch.json` (see `buildcon-house-project` memory for the exact recipe — backend does NOT auto-reload, restart it if Tasks 1-6's Python changes aren't live yet).

Navigate to the app, log in as a user with ground-floor access, switch to Ground Floor, and open **Tile Orders** from the sidebar (the new nav entry from Task 7). Verify:
- The page loads without a console error.
- The "Customer-wise" tab is active by default and shows order cards (or "No tile orders yet." if the ground floor has no orders — expected per memory, ground-floor catalog/data is currently empty).
- Clicking "Company-wise" switches the view and issues a request to `/api/purchases/orders/company-view` (check via the browser's network tab).
- If any tile orders exist, each card shows customer name, PO number, supplier, a 4-dot stage indicator, product count, and total value.

- [ ] **Step 3: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/app/\(admin\)/_layout.tsx frontend/app/\(admin\)/tiles/orders/index.tsx frontend/src/components/tiles/TileOrderCard.tsx && git commit -m "feat: add Tile Orders Customer-wise/Company-wise list page"
```

---

## Task 10: Order detail page + Generate Chalan form

**Files:**
- Create: `frontend/src/components/tiles/ChalanFormSheet.tsx`
- Create: `frontend/app/(admin)/tiles/orders/[id].tsx`

**Interfaces:**
- Consumes: `GET /purchases/{po_id}/order-detail`, `POST /purchases/{po_id}/chalans`, `POST /purchases/{po_id}/chalans/{chalan_id}/godown-received`, `POST /purchases/{po_id}/chalans/{chalan_id}/dispatch`, `GET /purchases/{po_id}/chalans/{chalan_id}/pdf` (all Tasks 4-6), `StageProgress`/`stageLabel`/`OrderStage` (Task 8), `downloadApiFile` (existing, `@/src/utils/downloadFile`)

- [ ] **Step 1: Write the Generate Chalan form**

Create `frontend/src/components/tiles/ChalanFormSheet.tsx`:

```tsx
// Release Material → Generate Chalan form. Pre-fills each item's remaining
// unreleased quantity as the default — staff can adjust down for a partial
// batch release (multiple chalans can cover one order over time).
import { useState } from "react";
import { Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { colors, radius, spacing, type } from "@/src/theme/tokens";

type PoItem = { id: string; name: string; finish?: string | null; qty: number };

export function ChalanFormSheet({
  poId, items, remainingQtyByItem, onClose, onGenerated,
}: {
  poId: string;
  items: PoItem[];
  remainingQtyByItem: Record<string, number>;
  onClose: () => void;
  onGenerated: () => void;
}) {
  const releasable = items.filter((item) => (remainingQtyByItem[item.id] || 0) > 0);
  const [qtyById, setQtyById] = useState<Record<string, string>>(
    Object.fromEntries(releasable.map((item) => [item.id, String(remainingQtyByItem[item.id] || 0)])),
  );
  const [referenceNumber, setReferenceNumber] = useState("");
  const [receiverName, setReceiverName] = useState("");
  const [senderName, setSenderName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const body = {
      items: releasable
        .map((item) => ({ po_item_id: item.id, qty: Number(qtyById[item.id] || 0) }))
        .filter((entry) => entry.qty > 0),
      reference_number: referenceNumber || null,
      receiver_name: receiverName || null,
      sender_name: senderName || null,
    };
    if (body.items.length === 0) {
      toast.error("Enter a quantity for at least one item");
      return;
    }
    setSubmitting(true);
    try {
      await api.post(`/purchases/${poId}/chalans`, body);
      toast.success("Chalan generated");
      onGenerated();
    } catch (e: any) {
      toast.error(e?.detail || "Could not generate chalan");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
        <View style={{
          backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: radius.xl,
          borderTopRightRadius: radius.xl, maxHeight: "85%", padding: spacing.xl,
        }}>
          <Text style={type.titleLg}>Release Material</Text>
          <Text style={[type.bodyMuted, { marginBottom: spacing.md }]}>
            Generates a Chalan for the quantities below.
          </Text>
          <ScrollView style={{ maxHeight: 320 }}>
            {releasable.map((item) => (
              <View key={item.id} style={{ marginBottom: spacing.md }}>
                <Text style={type.bodyStrong}>{item.name}{item.finish ? ` · ${item.finish}` : ""}</Text>
                <Text style={type.caption}>Remaining: {remainingQtyByItem[item.id]}</Text>
                <TextInput
                  keyboardType="numeric"
                  value={qtyById[item.id]}
                  onChangeText={(v) => setQtyById((prev) => ({ ...prev, [item.id]: v }))}
                  style={{
                    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
                    padding: spacing.sm, marginTop: spacing.xs,
                  }}
                />
              </View>
            ))}
            <TextInput
              placeholder="Reference number (optional)"
              value={referenceNumber}
              onChangeText={setReferenceNumber}
              style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, marginBottom: spacing.sm }}
            />
            <TextInput
              placeholder="Receiver name"
              value={receiverName}
              onChangeText={setReceiverName}
              style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, marginBottom: spacing.sm }}
            />
            <TextInput
              placeholder="Supplier representative (sender)"
              value={senderName}
              onChangeText={setSenderName}
              style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm }}
            />
          </ScrollView>
          <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg }}>
            <Pressable
              onPress={onClose}
              style={{ flex: 1, alignItems: "center", padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}
            >
              <Text style={type.bodyStrong}>Cancel</Text>
            </Pressable>
            <Pressable
              onPress={submit}
              disabled={submitting}
              style={{ flex: 1, alignItems: "center", padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brand, opacity: submitting ? 0.6 : 1 }}
            >
              <Text style={[type.bodyStrong, { color: colors.onBrand }]}>{submitting ? "Generating…" : "Generate Chalan"}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}
```

- [ ] **Step 2: Write the order detail page**

Create `frontend/app/(admin)/tiles/orders/[id].tsx`:

```tsx
// Ground Floor → Tiles → Orders → detail — full chalan-by-chalan breakdown
// of a single order, the Release Material action, and Godown/Dispatch
// actions per chalan. Reads/writes the same PurchaseOrder the Customer-wise
// and Company-wise list views show — no separate copy.
import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { toast } from "@/src/components/Toast";
import { ChalanFormSheet } from "@/src/components/tiles/ChalanFormSheet";
import { StageProgress, stageLabel, type OrderStage } from "@/src/components/tiles/TileOrderCard";
import { colors, radius, spacing, type } from "@/src/theme/tokens";
import { downloadApiFile } from "@/src/utils/downloadFile";

type ChalanStage = "released" | "at_godown" | "dispatched";

type ChalanLine = { po_item_id: string; name: string; size?: string | null; qty: number; unit: string };

type Chalan = {
  id: string; number: string; created_at: string; items: ChalanLine[];
  reference_number?: string | null; receiver_name?: string | null; sender_name?: string | null;
  stage: ChalanStage; dispatch_note?: string | null;
};

type PoItem = { id: string; name: string; finish?: string | null; qty: number };

type OrderDetail = {
  id: string; number: string; customer_name: string; customer_phone?: string | null;
  supplier_name?: string | null; status: string; stage: OrderStage;
  items: PoItem[]; chalans: Chalan[]; remaining_qty_by_item: Record<string, number>;
};

const CHALAN_STAGE_LABEL: Record<ChalanStage, string> = {
  released: "Released", at_godown: "At Godown", dispatched: "Dispatched",
};

export default function TileOrderDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [showChalanForm, setShowChalanForm] = useState(false);
  const [busyChalanId, setBusyChalanId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const r = await api.get<OrderDetail>(`/purchases/${id}/order-detail`);
      setOrder(r);
    } catch (e: any) {
      toast.error(e?.detail || "Could not load order");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const markGodown = async (chalanId: string) => {
    if (!id) return;
    setBusyChalanId(chalanId);
    try {
      await api.post(`/purchases/${id}/chalans/${chalanId}/godown-received`);
      toast.success("Marked received at Godown");
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not update chalan");
    } finally {
      setBusyChalanId(null);
    }
  };

  const dispatch = async (chalanId: string) => {
    if (!id) return;
    setBusyChalanId(chalanId);
    try {
      await api.post(`/purchases/${id}/chalans/${chalanId}/dispatch`, {});
      toast.success("Marked dispatched");
      await load();
    } catch (e: any) {
      toast.error(e?.detail || "Could not update chalan");
    } finally {
      setBusyChalanId(null);
    }
  };

  const downloadChalanPdf = async (chalan: Chalan) => {
    if (!id || !order) return;
    const stamp = new Date(chalan.created_at);
    const dd = String(stamp.getDate()).padStart(2, "0");
    const mm = String(stamp.getMonth() + 1).padStart(2, "0");
    const filename = `${chalan.number} ${order.customer_name} ${dd}-${mm}-${stamp.getFullYear()}.pdf`;
    await downloadApiFile(`/purchases/${id}/chalans/${chalan.id}/pdf`, filename, "chalan");
  };

  if (loading || !order) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface, justifyContent: "center" }}>
        <ActivityIndicator color={colors.brand} />
      </SafeAreaView>
    );
  }

  const hasRemaining = Object.values(order.remaining_qty_by_item).some((qty) => qty > 0);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Pressable onPress={() => router.back()} style={styles.backRow}>
          <Feather name="arrow-left" size={16} color={colors.onSurfaceMuted} />
          <Text style={type.bodyMuted}>Back to Tile Orders</Text>
        </Pressable>

        <Text style={type.overline}>{order.number}</Text>
        <Text style={type.displayMd}>{order.customer_name}</Text>
        <Text style={type.bodyMuted}>
          {order.supplier_name || "No supplier assigned"} · {order.customer_phone || "No phone on file"}
        </Text>

        <View style={{ marginVertical: spacing.lg, gap: spacing.xs }}>
          <StageProgress stage={order.stage} />
          <Text style={[type.captionStrong, { color: colors.brandHover }]}>{stageLabel(order.stage)}</Text>
        </View>

        {hasRemaining ? (
          <Pressable style={styles.primaryButton} onPress={() => setShowChalanForm(true)}>
            <Feather name="file-text" size={16} color={colors.onBrand} />
            <Text style={[type.bodyStrong, { color: colors.onBrand }]}>Release Material — Generate Chalan</Text>
          </Pressable>
        ) : null}

        <Text style={[type.titleMd, { marginTop: spacing.xl }]}>Chalans</Text>
        {order.chalans.length === 0 ? (
          <Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>No material released yet.</Text>
        ) : (
          order.chalans.map((chalan) => (
            <View key={chalan.id} style={styles.chalanCard}>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={type.bodyStrong}>{chalan.number}</Text>
                <Text style={type.captionStrong}>{CHALAN_STAGE_LABEL[chalan.stage]}</Text>
              </View>
              {chalan.items.map((line) => (
                <Text key={line.po_item_id} style={type.bodySm}>
                  {line.name} {line.size ? `· ${line.size}` : ""} · {line.qty} {line.unit}
                </Text>
              ))}
              <View style={styles.chalanActions}>
                <Pressable style={styles.secondaryButton} onPress={() => downloadChalanPdf(chalan)}>
                  <Feather name="download" size={14} color={colors.onSurface} />
                  <Text style={type.bodySm}>PDF</Text>
                </Pressable>
                {chalan.stage === "released" ? (
                  <Pressable
                    style={styles.secondaryButton}
                    disabled={busyChalanId === chalan.id}
                    onPress={() => markGodown(chalan.id)}
                  >
                    <Text style={type.bodySm}>Material Received at Godown</Text>
                  </Pressable>
                ) : null}
                {chalan.stage !== "dispatched" ? (
                  <Pressable
                    style={styles.secondaryButton}
                    disabled={busyChalanId === chalan.id}
                    onPress={() => dispatch(chalan.id)}
                  >
                    <Text style={type.bodySm}>Dispatch</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          ))
        )}
      </ScrollView>

      {showChalanForm ? (
        <ChalanFormSheet
          poId={order.id}
          items={order.items}
          remainingQtyByItem={order.remaining_qty_by_item}
          onClose={() => setShowChalanForm(false)}
          onGenerated={async () => {
            setShowChalanForm(false);
            await load();
          }}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: spacing.xl, width: "100%", maxWidth: 760, alignSelf: "center" },
  backRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md },
  primaryButton: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    backgroundColor: colors.brand, borderRadius: radius.md, paddingVertical: spacing.md,
  },
  secondaryButton: {
    flexDirection: "row", alignItems: "center", gap: spacing.xs,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingVertical: spacing.xs, paddingHorizontal: spacing.sm,
  },
  chalanCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1,
    borderColor: colors.border, padding: spacing.lg, marginTop: spacing.sm, gap: spacing.xs,
  },
  chalanActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm, flexWrap: "wrap" },
});
```

- [ ] **Step 3: Manually verify in the browser**

With the backend restarted (Tasks 4-6's endpoints live) and the frontend dev server running:

1. From **Tile Orders** (Task 9's page), click an order card. Verify it navigates to `/tiles/orders/<po_id>` and shows the customer name, supplier, 4-dot progress, and an item list with a working "Release Material — Generate Chalan" button (if any quantity remains unreleased).
2. Click "Release Material — Generate Chalan". Verify the sheet opens pre-filled with each item's full remaining quantity, fill in a receiver/sender name, and submit. Verify: a toast confirms generation, the sheet closes, the page reloads, a new Chalan card appears with stage "Released", and the 4-dot indicator does NOT yet advance past "Order" unless every item's quantity was fully covered by this one chalan.
3. On the new chalan card, click "PDF". Verify a PDF opens/downloads named like `CH-0001 <Customer Name> <DD-MM-YYYY>.pdf` and its content shows the Buildcon House logo, chalan number, customer/supplier, the product table, and blank Receiver/Sender signature lines.
4. Click "Material Received at Godown" on the chalan. Verify the chalan's badge changes to "At Godown" and the order's 4-dot indicator advances to "Godown" (assuming this chalan covered the full order).
5. Click "Dispatch". Verify the chalan badge changes to "Dispatched" and the order's 4-dot indicator advances to "Dispatch"/"Completed".
6. Go back to the Tile Orders list and confirm the SAME order card (in both Customer-wise and Company-wise tabs) now reflects the updated stage — proving there's no separate copy to fall out of sync.

- [ ] **Step 4: Commit**

```bash
cd "/Users/yashvardhansinhjhala/buildcon house/forge2.0" && git add frontend/src/components/tiles/ChalanFormSheet.tsx frontend/app/\(admin\)/tiles/orders/\[id\].tsx && git commit -m "feat: add tile order detail page with Release Material / Godown / Dispatch actions"
```

---

## Self-Review Notes

- **Spec coverage**: Stage 1 (Order) — covered by existing `_handle_order_placed` automation (unchanged) plus Task 6's `_order_card`/`order_detail`. Stage 2 (Material Released + Chalan) — Task 4 (generate), Task 3 (PDF). Stage 3 (Godown, optional) — Task 5 (`mark_chalan_godown_received`). Stage 4 (Dispatch) — Task 5 (`dispatch_chalan`). Customer-wise/Company-wise views — Task 6 (backend), Tasks 8-9 (frontend). Synchronization — inherent to the design (single `PurchaseOrder` document, no cache), verified explicitly in Task 10 Step 3.6. Timeline — `log_event` calls in Tasks 4-5 (rendering a full activity feed on the detail page was scoped out per the design doc's PDF/notification/timeline section; the detail page shows the chalan list itself as the record of what happened, which carries the same information the spec's timeline example lists). Notifications — Task 4 (Material Released) and Task 5 (Dispatched, only on the last chalan). Chalan PDF layout — Task 3, matches every field in the spec's "Chalan Layout" section.
- **Placeholder scan**: no TBD/TODO; every step has complete, runnable code.
- **Type consistency**: `OrderStage` (Task 8) matches the 5 strings `compute_order_stage` (Task 2) returns exactly. `ChalanStage`/`Chalan`/`ChalanLineItem` field names in Task 1's Python model match the JSON shape the Task 4/5 endpoints construct and the Task 10 frontend TypeScript types consume (`po_item_id`, `size`, `qty`, `unit`, `stage`, `receiver_name`, `sender_name`, `dispatch_note`). `GenerateChalanBody`/`ChalanItemInput`/`DispatchChalanBody` names are used identically across Task 4/5's implementation and their tests.
