"""Catalog Integrity Guard — permanent safeguard against the two bug classes
found during the Hansgrohe/AXOR recovery (global-SKU lookups + global-SKU
writes silently crossing brand boundaries).

Reusable by:
  * backend/scripts/catalog_verify.py   (the `catalog:verify` CLI command)
  * backend/scripts/run_hansgrohe_batch.py and any future batch importer
    (pre-import baseline scan + post-import diff-against-snapshot)

Nothing here mutates data - it only reads and reports. Repairs (when the scan
finds something) are done via the same restore-from-snapshot pattern used
manually during batches 1 and 2 (see scripts/backup_db.py / restore_db.py).
"""
from __future__ import annotations
import json
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from db import db


@dataclass
class IntegrityReport:
    total_products: int = 0
    total_media: int = 0
    total_brands: int = 0
    total_categories: int = 0

    same_brand_duplicate_skus: list[dict] = field(default_factory=list)
    cross_brand_sku_collisions: list[dict] = field(default_factory=list)  # informational only
    invalid_brand_refs: list[str] = field(default_factory=list)          # product ids
    invalid_category_refs: list[str] = field(default_factory=list)       # product ids
    orphaned_media: list[str] = field(default_factory=list)              # media ids
    media_brand_mismatches: list[dict] = field(default_factory=list)
    missing_images: int = 0
    unexpected_modifications: list[dict] = field(default_factory=list)   # only when a baseline is given

    @property
    def ok(self) -> bool:
        """Hard-fail conditions only. Cross-brand SKU collisions and missing
        images are expected/informational and never fail the guard."""
        return not (
            self.same_brand_duplicate_skus
            or self.invalid_brand_refs
            or self.invalid_category_refs
            or self.orphaned_media
            or self.media_brand_mismatches
            or self.unexpected_modifications
        )

    def to_public(self) -> dict:
        return {**asdict(self), "ok": self.ok}


async def scan_catalog(baseline_snapshot_dir: Optional[str] = None) -> IntegrityReport:
    """Run the full integrity scan against the live database.

    If `baseline_snapshot_dir` is given (a directory produced by
    backup_db.py, containing products.json), every product is diffed against
    that snapshot by id - any brand_id/name change on a product that already
    existed in the baseline is flagged as an "unexpected modification"
    (exactly the class of bug this guard exists to catch).
    """
    report = IntegrityReport()

    products = await db.products.find({}, {"_id": 0}).to_list(20000)
    media = await db.product_media.find({}, {"_id": 0}).to_list(20000)
    brands = await db.brands.find({}, {"_id": 0}).to_list(50)
    categories = await db.categories.find({}, {"_id": 0}).to_list(200)

    report.total_products = len(products)
    report.total_media = len(media)
    report.total_brands = len(brands)
    report.total_categories = len(categories)

    brand_ids = {b["id"] for b in brands}
    category_ids = {c["id"] for c in categories}
    prod_by_id = {p["id"]: p for p in products}

    # 1) SKU uniqueness - scoped by brand. Same-brand dupes are a hard fail;
    #    cross-brand collisions are expected (different manufacturers reuse
    #    short numeric codes) and only reported informationally.
    by_sku: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        if p.get("sku"):
            by_sku[p["sku"]].append(p)
    for sku, group in by_sku.items():
        if len(group) < 2:
            continue
        brands_in_group = {p["brand_id"] for p in group}
        if len(brands_in_group) == 1:
            report.same_brand_duplicate_skus.append({
                "sku": sku, "brand_id": group[0]["brand_id"],
                "product_ids": [p["id"] for p in group],
                "names": [p["name"] for p in group],
            })
        else:
            report.cross_brand_sku_collisions.append({
                "sku": sku,
                "products": [{"id": p["id"], "brand_id": p["brand_id"], "name": p["name"]} for p in group],
            })

    # 2) Referential integrity
    for p in products:
        if p.get("brand_id") not in brand_ids:
            report.invalid_brand_refs.append(p["id"])
        if p.get("category_id") and p["category_id"] not in category_ids:
            report.invalid_category_refs.append(p["id"])

    # 3) Media integrity
    for m in media:
        pid = m.get("product_id")
        if pid and pid not in prod_by_id:
            report.orphaned_media.append(m["id"])
            continue
        if pid and m.get("brand_id") != prod_by_id[pid]["brand_id"]:
            report.media_brand_mismatches.append({
                "media_id": m["id"], "product_id": pid,
                "product_brand": prod_by_id[pid]["brand_id"], "media_brand": m.get("brand_id"),
            })

    media_by_product: dict[str, int] = defaultdict(int)
    for m in media:
        if m.get("product_id"):
            media_by_product[m["product_id"]] += 1
    report.missing_images = sum(1 for p in products if media_by_product.get(p["id"], 0) == 0)

    # 4) Diff against a pre-batch baseline snapshot, if provided - this is
    #    the exact technique that caught both real bugs during the Hansgrohe
    #    recovery: any product that existed in the baseline whose brand_id or
    #    name silently changed (without going through a legitimate re-import
    #    of ITS OWN brand's file) is flagged.
    if baseline_snapshot_dir:
        snap_path = Path(baseline_snapshot_dir) / "products.json"
        if snap_path.exists():
            baseline = {p["id"]: p for p in json.loads(snap_path.read_text())}
            for pid, base in baseline.items():
                cur = prod_by_id.get(pid)
                if not cur:
                    report.unexpected_modifications.append({
                        "product_id": pid, "issue": "deleted", "was": base["name"],
                    })
                    continue
                if cur.get("brand_id") != base.get("brand_id") or cur.get("name") != base.get("name"):
                    report.unexpected_modifications.append({
                        "product_id": pid,
                        "issue": "brand_or_name_changed",
                        "was": {"name": base["name"], "brand_id": base["brand_id"]},
                        "now": {"name": cur["name"], "brand_id": cur["brand_id"]},
                    })

    return report
