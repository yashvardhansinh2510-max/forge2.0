"""Task 4: `floor_id` must be a REQUIRED field on every model that carries
it, not `str = "first-floor"`. A default silently misfiles a forgotten floor
under Sanitary; a required field turns the same mistake into a loud
construction error instead.

Two layers of protection:

1. `test_construction_without_floor_id_raises` — for each of the 16 classes
   named in the Task 4 brief, build the minimal set of its OTHER required
   fields, omit floor_id, and assert pydantic raises ValidationError
   specifically about the missing floor_id.

2. `test_no_model_field_defines_a_default_floor_id` — scans every BaseModel
   subclass actually defined in models.py / models_tile_orders.py (not just
   the 16 named today) for a `floor_id` field and asserts it is required.
   This is the guard the brief asks for: "so a future model added with a
   default fails here" — it does not depend on anyone remembering to extend
   the parametrize list above.

CustomerBase is deliberately NOT in either list: floor_id lives on
CustomerPublic (see models.py), not on CustomerBase — see the comment on
CustomerBase for why (CustomerCreate, the POST /customers request body,
inherits CustomerBase and the live frontend never sends floor_id in that
payload). CustomerPublic is covered instead.
"""
from __future__ import annotations

import inspect

import pydantic
import pytest
from pydantic import BaseModel

import models
import models_tile_orders

# Each entry: (class, kwargs for every OTHER required field — no floor_id).
CASES = [
    (
        models.CustomerPublic,
        dict(name="Test Customer"),
    ),
    (
        models.Brand,
        dict(name="Hansgrohe", slug="hansgrohe"),
    ),
    (
        models.Category,
        dict(name="Faucets", slug="faucets"),
    ),
    (
        models.Product,
        dict(name="Talis E", sku="HG-001", brand_id="b-1", category_id="c-1", mrp=100.0, price=90.0),
    ),
    (
        models.Quotation,
        dict(number="FQ-2026-0001", customer_id="c-1", customer_name="Test Customer",
             created_by="u-1", created_by_name="Sales Rep"),
    ),
    (
        models.Supplier,
        dict(name="Test Supplier"),
    ),
    (
        models.PurchaseOrder,
        dict(number="FPO-2026-0001", customer_id="c-1", customer_name="Test Customer",
             created_by="u-1", created_by_name="Purchase Rep"),
    ),
    (
        models.Payment,
        dict(customer_id="c-1", amount=100.0),
    ),
    (
        models.Followup,
        dict(customer_id="c-1", customer_name="Test Customer", due_at="2026-08-02T00:00:00+00:00"),
    ),
    (
        models.CatalogImportJob,
        dict(filename="import.xlsx", source_type="excel", created_by="u-1"),
    ),
    (
        models.ProductMedia,
        dict(bucket="product-media", storage_key="k/1.jpg", sha1="a" * 40),
    ),
    (
        models_tile_orders.TileCustomerOrder,
        dict(
            number="TORD-2026-0001", quotation_id="q-1", quotation_number="FQ-2026-0001",
            customer_id="c-1", customer_name="Test Customer", customer_phone="9999999999",
            delivery_name="Test Customer", delivery_phone="9999999999", delivery_address="123 Road",
            delivery_city="Rajkot", delivery_pincode="360005", delivery_state="Gujarat",
            created_by="u-1", created_by_name="Sales Rep",
            dashboard_summary=models_tile_orders.TileCustomerOrderDashboardSummary(),
        ),
    ),
    (
        models_tile_orders.TileReadyBatch,
        dict(
            batch_number="RB-2026-0001", purchase_order_id="po-1", po_item_id="item-1",
            customer_order_id="co-1", supplier_name="Qutone Rajkot", customer_id="c-1",
            customer_name="Test Customer", tile_name="Glossy Ivory 600x600", qty=8, remaining_qty=8,
            created_by="u-1", created_by_name="Warehouse Rep",
        ),
    ),
    (
        models_tile_orders.TileDispatch,
        dict(
            dispatch_number="DSP-2026-0001", purchase_order_id="po-1", customer_order_id="co-1",
            supplier_name="Qutone Rajkot", customer_id="c-1", customer_name="Test Customer",
            ready_batches_consumed=[], destination_type="Customer", destination_name="Test Customer",
            destination_address="123 Road", destination_city="Rajkot",
            dispatch_date="2026-07-29", dispatch_time="14:23",
            created_by="u-1", created_by_name="Warehouse Rep", chalan_id="ch-1",
        ),
    ),
    (
        models_tile_orders.TileChalan,
        dict(
            number="CH-0001", dispatch_id="d-1", purchase_order_id="po-1", customer_order_id="co-1",
            supplier_name="Qutone Rajkot", customer_name="Test Customer", customer_phone="9999999999",
            delivery_address="123 Road", delivery_city="Rajkot", items=[],
            created_by="u-1", created_by_name="Warehouse Rep",
            generated_at="2026-07-29T14:23:00+00:00", generated_by_name="Warehouse Rep",
        ),
    ),
    (
        models_tile_orders.TileMaterialMovement,
        dict(
            movement_type="release", purchase_order_id="po-1", customer_name="Test Customer",
            brand_name="Qutone", tile_name="Glossy Ivory 600x600", boxes=8.0,
            performed_by="u-1", performed_by_name="Warehouse Rep",
        ),
    ),
]

CASE_IDS = [cls.__name__ for cls, _ in CASES]


@pytest.mark.parametrize("cls,kwargs", CASES, ids=CASE_IDS)
def test_construction_without_floor_id_raises(cls, kwargs):
    """floor_id omitted entirely -> ValidationError, not a silent
    "first-floor" default."""
    with pytest.raises(pydantic.ValidationError) as exc_info:
        cls(**kwargs)
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("floor_id",) for err in errors), (
        f"{cls.__name__} raised ValidationError but not for the missing "
        f"floor_id field — got: {errors}"
    )


@pytest.mark.parametrize("cls,kwargs", CASES, ids=CASE_IDS)
def test_construction_succeeds_with_floor_id(cls, kwargs):
    """Sanity check the CASES fixtures above are otherwise valid — every
    field OTHER than floor_id really is sufficient, so the ValidationError
    in the test above is caused by floor_id alone."""
    instance = cls(floor_id="first-floor", **kwargs)
    assert instance.floor_id == "first-floor"


def _model_classes_in(module) -> list[type[BaseModel]]:
    return [
        obj for _name, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, BaseModel) and obj.__module__ == module.__name__
    ]


def test_no_model_field_defines_a_default_floor_id():
    """Future-proofing: walk every model class actually defined in
    models.py / models_tile_orders.py (not just the 16 named above) and
    fail if any of them declares `floor_id` with a concrete string default
    (the "first-floor" bug shape) — catches a new model shipping
    `floor_id: str = "first-floor"` even if nobody remembers to add it to
    CASES above.

    Deliberately NOT flagged: `floor_id: Optional[str] = None` (ActivityEvent,
    Notification — pre-existing, outside the 16 named in the Task 4 brief).
    That is a different, already-reviewed pattern: an unstamped row is hidden
    from every floor-scoped reader rather than filed under Sanitary, which is
    the opposite failure mode from the one this task removes. Only a
    non-None string default reproduces the silent-misfile bug."""
    offenders = []
    for module in (models, models_tile_orders):
        for cls in _model_classes_in(module):
            field = cls.model_fields.get("floor_id")
            if field is None:
                continue
            if field.is_required():
                continue
            if isinstance(field.default, str):
                offenders.append(f"{module.__name__}.{cls.__name__} (default={field.default!r})")
    assert offenders == [], (
        "these models declare floor_id with a concrete string default, "
        f"silently misfiling a forgotten floor under Sanitary: {offenders}"
    )
