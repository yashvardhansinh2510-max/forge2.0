#!/usr/bin/env python3
"""One-time backfill for the Tile Orders logistics redesign (see
docs/superpowers/specs/2026-07-29-tile-orders-logistics-redesign-design.md
§Migration). Creates a TileCustomerOrder for every pre-existing tiles
PurchaseOrder missing customer_order_id (grouped by quotation_id), and
converts each embedded old Chalan into a new TileDispatch + immutable
TileChalan + one synthetic fully-consumed TileReadyBatch.

Idempotent — a PurchaseOrder with customer_order_id already set is
skipped entirely, so re-running after a partial failure is safe. The Mongo
query below already excludes such POs, but the in-loop check is kept as a
defense-in-depth belt-and-braces guard (and is what makes the unit tests,
which use a hand-rolled fake collection that does not implement query
filtering, actually exercise idempotency).

Usage:
    cd backend && python scripts/backfill_tile_customer_orders.py           # apply
    cd backend && python scripts/backfill_tile_customer_orders.py --dry-run # report only, no writes
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from db import db
from models_tile_orders import (
    TileChalan, TileChalanItem, TileCustomerOrder, TileCustomerOrderBrand,
    TileCustomerOrderDashboardSummary, TileDispatch, TileDispatchLineConsumed, TileReadyBatch,
)
from services.sequence import next_number
from services.tile_order_status import rollup_status

_OLD_STAGE_TO_LOCATION = {"released": "Dispatched", "at_godown": "Godown", "dispatched": "Delivered"}


async def backfill(*, dry_run: bool) -> dict:
    customer_orders_created = 0
    chalans_migrated = 0

    pos = await db.purchase_orders.find(
        {"$or": [{"customer_order_id": {"$exists": False}}, {"customer_order_id": None}]}, {"_id": 0},
    ).to_list(50000)

    by_quotation: dict[str, list[dict]] = {}
    for po in pos:
        if po.get("customer_order_id"):
            continue  # already migrated — belt-and-braces, see module docstring
        quotation_id = po.get("quotation_id")
        if not quotation_id:
            continue
        by_quotation.setdefault(quotation_id, []).append(po)

    for quotation_id, group_pos in by_quotation.items():
        quotation = await db.quotations.find_one({"id": quotation_id}, {"_id": 0, "doc_type": 1})
        if not quotation or quotation.get("doc_type") not in ("tiles_selection", "tiles_quotation"):
            continue  # standard (sanitaryware) orders never get a TileCustomerOrder

        first_po = group_pos[0]
        year_str = first_po.get("created_at", "")[:4] or str(datetime.now(timezone.utc).year)
        # Number allocation is itself a write (db.counters $inc) — skip it in
        # dry-run so a report-only run never consumes a real TORD number.
        number = (
            "DRY-RUN-PREVIEW" if dry_run
            else await next_number("customer_order", f"TORD-{year_str}-", collection="customer_orders")
        )
        customer_order = TileCustomerOrder(
            number=number, quotation_id=quotation_id, quotation_number=first_po.get("quotation_number", ""),
            customer_id=first_po.get("customer_id", ""), customer_name=first_po.get("customer_name", ""),
            customer_phone="", delivery_name=first_po.get("customer_name", ""), delivery_phone="",
            delivery_address="", delivery_city="", delivery_pincode="", delivery_state="",
            floor_id=first_po.get("floor_id", "first-floor"), created_by="system-backfill",
            created_by_name="Backfill script", dashboard_summary=TileCustomerOrderDashboardSummary(),
        )

        total_products, total_boxes = 0, 0.0
        brands: list[TileCustomerOrderBrand] = []

        for po in group_pos:
            items = po.get("items", [])
            total_products += len(items)
            total_boxes += sum(float(i.get("qty") or 0) for i in items)

            for item in items:
                boxes_dispatched = 0.0
                location = "Pending"
                for old_chalan in po.get("chalans", []):
                    for line in old_chalan.get("items", []):
                        if line.get("po_item_id") != item["id"]:
                            continue
                        qty = float(line.get("qty") or 0)
                        boxes_dispatched += qty
                        location = _OLD_STAGE_TO_LOCATION.get(old_chalan.get("stage"), "Dispatched")

                        if not dry_run:
                            batch_number = await next_number("ready_batch", f"RB-{year_str}-", collection="ready_batches")
                            batch = TileReadyBatch(
                                batch_number=batch_number, purchase_order_id=po["id"], po_item_id=item["id"],
                                customer_order_id=customer_order.id, floor_id=po.get("floor_id", "first-floor"),
                                supplier_id=po.get("supplier_id"), supplier_name=po.get("supplier_name") or "Unassigned",
                                customer_id=po.get("customer_id"), customer_name=po.get("customer_name") or "",
                                tile_name=item.get("name", ""), qty=qty, remaining_qty=0,
                                created_by="system-backfill", created_by_name="Backfill script", auto_created=True,
                            )
                            await db.ready_batches.insert_one(batch.dict())

                            chalan = TileChalan(
                                number=old_chalan.get("number", ""), dispatch_id="", purchase_order_id=po["id"],
                                customer_order_id=customer_order.id, floor_id=po.get("floor_id", "first-floor"),
                                supplier_name=po.get("supplier_name") or "Unassigned", customer_name=po.get("customer_name") or "",
                                customer_phone="", delivery_address="", delivery_city="",
                                items=[TileChalanItem(po_item_id=item["id"], tile_name=item.get("name", ""), boxes=qty, quantity=qty)],
                                created_by=old_chalan.get("created_by", "system-backfill"),
                                created_by_name=old_chalan.get("created_by_name", "Backfill script"),
                                generated_at=old_chalan.get("created_at", datetime.now(timezone.utc).isoformat()),
                                generated_by_name=old_chalan.get("created_by_name", "Backfill script"),
                            )
                            dispatch = TileDispatch(
                                dispatch_number=await next_number("dispatch", f"DSP-{year_str}-", collection="dispatches"),
                                purchase_order_id=po["id"], customer_order_id=customer_order.id,
                                floor_id=po.get("floor_id", "first-floor"), supplier_id=po.get("supplier_id"),
                                supplier_name=po.get("supplier_name") or "Unassigned", customer_id=po.get("customer_id"),
                                customer_name=po.get("customer_name") or "",
                                ready_batches_consumed=[TileDispatchLineConsumed(ready_batch_id=batch.id, po_item_id=item["id"], qty=qty)],
                                destination_type="Customer", destination_name=po.get("customer_name") or "",
                                destination_address="", destination_city="",
                                dispatch_date=old_chalan.get("created_at", "")[:10], dispatch_time=old_chalan.get("created_at", "")[11:16],
                                created_by="system-backfill", created_by_name="Backfill script", chalan_id=chalan.id,
                            )
                            chalan.dispatch_id = dispatch.id
                            if old_chalan.get("stage") == "at_godown":
                                dispatch.godown_received_at = old_chalan.get("created_at")
                            await db.chalans.insert_one(chalan.dict())
                            await db.dispatches.insert_one(dispatch.dict())
                        chalans_migrated += 1

                item["boxes_ready"] = 0
                item["boxes_dispatched"] = boxes_dispatched
                item["boxes_pending"] = float(item.get("qty") or 0) - boxes_dispatched
                item["current_location"] = location
                item["overall_status"] = "Dispatched" if boxes_dispatched >= float(item.get("qty") or 0) and boxes_dispatched > 0 else ("Partially Dispatched" if boxes_dispatched > 0 else "Pending")

            po_status = rollup_status([i["overall_status"] for i in items])
            brands.append(TileCustomerOrderBrand(
                brand_id=po.get("brand_id"), brand_name=po.get("brand_name") or "Unassigned",
                supplier_id=po.get("supplier_id"), supplier_name=po.get("supplier_name") or "Unassigned",
                purchase_order_id=po["id"], status=po_status,
            ))
            if not dry_run:
                await db.purchase_orders.update_one({"id": po["id"]}, {"$set": {
                    "items": items, "customer_order_id": customer_order.id, "overall_status": po_status,
                    "dispatched_boxes": sum(i["boxes_dispatched"] for i in items),
                    "pending_boxes": sum(i["boxes_pending"] for i in items), "ready_boxes": 0,
                }})

        customer_order.brands = brands
        customer_order.total_products = total_products
        customer_order.total_boxes = total_boxes
        customer_order.overall_status = rollup_status([b.status for b in brands])
        customer_order.dashboard_summary = TileCustomerOrderDashboardSummary(
            completion_percentage=0, overall_status=customer_order.overall_status,
            supplier_statuses=[{"supplier_name": b.supplier_name, "status": b.status} for b in brands],
        )
        if not dry_run:
            await db.customer_orders.insert_one(customer_order.dict())
        customer_orders_created += 1

    return {"customer_orders_created": customer_orders_created, "chalans_migrated": chalans_migrated}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()
    result = await backfill(dry_run=args.dry_run)
    mode = "DRY RUN — " if args.dry_run else ""
    print(f"{mode}Created {result['customer_orders_created']} TileCustomerOrder(s), migrated {result['chalans_migrated']} old Chalan(s).")


if __name__ == "__main__":
    asyncio.run(main())
