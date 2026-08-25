"""Import the SANIT DESIGN 2026 workbook into Ground Floor > Tiles.

The workbook stores product photos as drawing objects rather than cell values.
This importer maps each drawing's anchor row to the corresponding product row,
persists the source workbook as a private catalog asset, and uses the standard
catalog pipeline so product media is uploaded and registered consistently.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from auth import TILES_FLOOR_ID
from catalog_pipeline.integrity_guard import scan_catalog
from catalog_pipeline.orchestrator import _offload_row_images, import_accepted
from db import db
from media_storage.factory import get_media_storage, private_bucket
from models import CatalogImportJob


SOURCE_DEFAULT = Path(
    "/Users/yashvardhansinhjhala/Library/Containers/net.whatsapp.WhatsApp/Data/tmp/documents/"
    "5F9BAB70-CA50-41DF-90A5-8DF78A2ADB73/SANIT DESIGN 2026.xlsx"
)
BRAND = "SANIT"
CATEGORY = "Tiles"
NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def parse_rate(raw: str) -> float:
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", raw.replace(",", ""))
    if not match:
        raise ValueError(f"No numeric rate found in {raw!r}")
    return float(match.group())


def image_map(zf: zipfile.ZipFile) -> dict[int, tuple[str, bytes, str]]:
    rels = ET.fromstring(zf.read("xl/drawings/_rels/drawing1.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"].replace("../", "xl/")
        for rel in rels.findall("pr:Relationship", NS)
    }
    drawing = ET.fromstring(zf.read("xl/drawings/drawing1.xml"))
    mapped: dict[int, tuple[str, bytes, str]] = {}
    for anchor in drawing.findall("xdr:twoCellAnchor", NS):
        from_cell = anchor.find("xdr:from", NS)
        row = int(from_cell.find("xdr:row", NS).text) + 1  # Excel row number
        blip = anchor.find(".//a:blip", NS)
        target = rel_targets[blip.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"]]
        payload = zf.read(target)
        mime = "image/png" if target.lower().endswith(".png") else "image/jpeg"
        mapped[row] = (target.rsplit("/", 1)[-1], payload, mime)
    return mapped


def extract_rows(source: Path) -> tuple[list[dict], bytes, dict]:
    data = source.read_bytes()
    with zipfile.ZipFile(source) as zf:
        shared = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        strings = ["".join(si.itertext()).strip() for si in shared]
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        images = image_map(zf)
        rows: list[dict] = []
        for row in sheet.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
            row_num = int(row.attrib["r"])
            if row_num == 1:
                continue
            values: dict[str, str] = {}
            for cell in row.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                ref = cell.attrib["r"]
                col = re.sub(r"[0-9]", "", ref)
                value = cell.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                if value is None:
                    values[col] = ""
                elif cell.attrib.get("t") == "s":
                    values[col] = strings[int(value.text)]
                else:
                    values[col] = value.text or ""
            name = values.get("B", "").strip()
            if not name:
                continue
            price = parse_rate(values.get("E", ""))
            image = images.get(row_num)
            image_urls: list[str] = []
            image_meta: list[dict] = []
            if image:
                filename, payload, mime = image
                encoded = base64.b64encode(payload).decode("ascii")
                image_urls.append(f"data:{mime};base64,{encoded}")
                image_meta.append({"filename": filename, "source_row": row_num, "source_format": mime})
            sku = f"SANIT-2026-{int(values.get('A', row_num)):03d}"
            size = values.get("D", "").strip() or None
            family_key = slug(name)
            rows.append({
                "row_id": f"sanit-{row_num}",
                "sku": sku,
                "name": name,
                "category": CATEGORY,
                "mrp": price,
                "dealer_price": price,
                "size": size,
                "dimensions": size,
                "description": name,
                "family_key": family_key,
                "variant": name,
                "images": image_urls,
                "image_meta": image_meta,
                "image_quality": "acceptable" if image else "missing",
                "specs": {
                    "source_file": source.name,
                    "source_row": row_num,
                    "source_serial": values.get("A", "").strip(),
                    "supplier_rate_text": values.get("E", "").strip(),
                    "rate_unit": "pcs",
                    "source_image_filename": image[0] if image else None,
                },
                "tags": ["sanit", "tiles", "ground-floor", "2026-import"],
                "status": "accepted",
                "confidence": 1.0,
                "issues": [],
            })
        meta = {"rows": len(rows), "images": sum(bool(r["images"]) for r in rows), "source_sha1": hashlib.sha1(data).hexdigest()}
        return rows, data, meta


async def main(source: Path, dry_run: bool) -> None:
    if not source.is_file():
        raise SystemExit(f"Source workbook not found: {source}")
    rows, source_bytes, extraction = extract_rows(source)
    if len(rows) != 38 or extraction["images"] != 38:
        raise SystemExit(f"Expected 38 rows and 38 images, got {extraction}")
    print(json.dumps({"mode": "dry-run" if dry_run else "import", "extraction": extraction}, indent=2))
    if dry_run:
        return

    before = await scan_catalog()
    if not before.ok:
        raise SystemExit("Catalog integrity guard failed before import; no changes made.")
    owner = await db.users.find_one({"email": "owner@forge.app"}, {"id": 1, "_id": 0})
    owner_id = (owner or {}).get("id", "system")
    source_sha1 = extraction["source_sha1"]
    existing_job = await db.catalog_imports.find_one(
        {"supplier_name": BRAND, "filename": source.name, "floor_id": TILES_FLOOR_ID, "source_sha1": source_sha1},
        {"_id": 0, "id": 1, "status": 1},
    )
    if existing_job and existing_job.get("status") == "imported":
        print(json.dumps({"status": "already_imported", "job_id": existing_job["id"]}))
        return

    storage = get_media_storage()
    source_key = f"catalog-sources/ground-floor/sanit/{source_sha1}/{source.name}"
    source_asset = {
        "bucket": private_bucket(),
        "storage_key": source_key,
        "sha1": source_sha1,
        "size_bytes": len(source_bytes),
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if not await storage.exists(bucket=private_bucket(), key=source_key):
        stored = await storage.upload(bucket=private_bucket(), key=source_key, data=source_bytes,
                                      content_type=source_asset["content_type"], upsert=False,
                                      cache_control="private, max-age=0")
        source_asset.update({"sha1": stored.sha1, "size_bytes": stored.size_bytes})

    blob_map = await _offload_row_images(rows)
    job = CatalogImportJob(
        filename=source.name, source_type="excel", supplier_name=BRAND,
        total_rows=len(rows), accepted_rows=len(rows), rejected_rows=0,
        status="classified", rows=rows, created_by=owner_id, floor_id=TILES_FLOOR_ID,
    ).model_dump()
    job["source_sha1"] = source_sha1
    job["source_asset"] = source_asset
    job["extraction"] = extraction
    await db.catalog_imports.insert_one(job)
    job.pop("_id", None)
    result = await import_accepted(job, owner_id, blob_map=blob_map, floor_id=TILES_FLOOR_ID)
    if result["failed"] or result["skipped"]:
        await db.catalog_imports.update_one({"id": job["id"]}, {"$set": {"status": "failed", "error": json.dumps(result)}})
        raise SystemExit(f"Import incomplete: {json.dumps(result)}")
    await db.catalog_imports.update_one({"id": job["id"]}, {"$set": {"status": "imported", "accepted_rows": len(rows)}})

    brand = await db.brands.find_one({"name": BRAND, "floor_id": TILES_FLOOR_ID}, {"_id": 0})
    category = await db.categories.find_one({"name": CATEGORY, "floor_id": TILES_FLOOR_ID}, {"_id": 0})
    product_count = await db.products.count_documents({"brand_id": brand["id"], "category_id": category["id"], "floor_id": TILES_FLOOR_ID})
    media_count = await db.product_media.count_documents({"brand_id": brand["id"], "floor_id": TILES_FLOOR_ID, "source_type": "supplier"})
    first = await db.products.find_one({"brand_id": brand["id"], "floor_id": TILES_FLOOR_ID}, {"_id": 0, "name": 1, "sku": 1, "size": 1, "price": 1})
    leak = await db.products.count_documents({"brand_id": brand["id"], "floor_id": "first-floor"})
    print(json.dumps({"job_id": job["id"], "import_result": result, "brand": brand, "category": category,
                     "product_count": product_count, "supplier_media_count": media_count,
                     "first_product": first, "first_floor_leak_count": leak}, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.source, args.dry_run))
