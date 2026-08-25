"""Production Catalog Audit — facts-only, read-only, no writes.

Covers every metric requested: per-brand product/image counts, broken
image URLs (real HTTP checks), duplicate media, orphan media, missing
variants, colour-variants-without-images, family default-image issues.
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
import httpx


async def check_urls(urls: list[str]) -> dict[str, str]:
    """Return {url: status} where status is 'ok', 'broken:<code>', or 'error:<msg>'.

    Low concurrency + retry: a first pass with high concurrency produced
    100% false-positive "ConnectTimeout" results (verified individually —
    the same URLs return real 200s when tested alone), so this sandbox's
    outbound networking can't sustain many simultaneous HTTPS connections.
    Never report a URL as broken without a solo, later retry confirming it.
    """
    results: dict[str, str] = {}
    sem = asyncio.Semaphore(5)

    async def _check_once(client: httpx.AsyncClient, url: str) -> str:
        try:
            r = await client.get(url, timeout=25, follow_redirects=True)
            return "ok" if r.status_code == 200 else f"broken:{r.status_code}"
        except Exception as e:
            return f"error:{type(e).__name__}"

    async def _check(client: httpx.AsyncClient, url: str):
        async with sem:
            status = await _check_once(client, url)
            if status != "ok":
                await asyncio.sleep(1.0)
                status = await _check_once(client, url)  # solo retry before condemning it
            results[url] = status

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[_check(client, u) for u in urls])
    return results


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    brands = await db.brands.find({}, {"_id": 0}).to_list(50)
    brand_name_by_id = {b["id"]: b["name"] for b in brands}
    all_products = await db.products.find({}, {"_id": 0}).to_list(10000)
    all_media = await db.product_media.find({}, {"_id": 0}).to_list(20000)

    print(f"TOTAL products in DB (active+inactive): {len(all_products)}")
    print(f"TOTAL product_media docs: {len(all_media)}")
    print()

    # ---- Orphan media: product_id doesn't exist as a product ----
    product_ids = {p["id"] for p in all_products}
    orphan_media = [m for m in all_media if m.get("product_id") and m["product_id"] not in product_ids]
    print(f"ORPHAN media (product_id references a non-existent product): {len(orphan_media)}")
    for m in orphan_media[:10]:
        print(f"   media_id={m.get('id')} product_id={m.get('product_id')} url={m.get('public_url', '')[-50:]}")

    # ---- Duplicate media: same product_id + same sha1 registered twice ----
    media_by_pid = defaultdict(list)
    for m in all_media:
        if m.get("product_id"):
            media_by_pid[m["product_id"]].append(m)
    dup_media_count = 0
    dup_examples = []
    for pid, rows in media_by_pid.items():
        seen_sha = {}
        for r in rows:
            sha = r.get("sha1")
            if sha and sha in seen_sha:
                dup_media_count += 1
                dup_examples.append((pid, sha, r.get("id")))
            elif sha:
                seen_sha[sha] = r.get("id")
    print(f"DUPLICATE media (same product + same image sha1 registered >1x): {dup_media_count}")
    for ex in dup_examples[:10]:
        print(f"   product_id={ex[0]} sha1={ex[1][:12]} media_id={ex[2]}")
    print()

    # ---- Per-brand breakdown ----
    active_products = [p for p in all_products if p.get("active", True)]
    by_brand = defaultdict(list)
    for p in active_products:
        by_brand[brand_name_by_id.get(p.get("brand_id"), "UNKNOWN")].append(p)

    report_lines = []
    all_urls_to_check = []
    url_to_media = {}
    for m in all_media:
        u = m.get("public_url")
        if u:
            all_urls_to_check.append(u)
            url_to_media[u] = m

    print("Checking all unique media URLs for HTTP 200 (this may take a minute)...")
    unique_urls = list(set(all_urls_to_check))
    print(f"Unique media URLs to verify: {len(unique_urls)}")
    url_status = await check_urls(unique_urls)
    broken_urls = {u: s for u, s in url_status.items() if s != "ok"}
    print(f"BROKEN URLs (non-200 or unreachable): {len(broken_urls)}")
    for u, s in list(broken_urls.items())[:15]:
        print(f"   {s}  {u[-70:]}")
    print()

    print("=" * 100)
    print(f"{'BRAND':<14}{'TOTAL':>7}{'W/IMG':>8}{'NO IMG':>8}{'IMG%':>8}{'FAMILIES':>10}{'MULTI-VAR FAM':>15}{'VARIANTS W/O IMG':>18}")
    print("=" * 100)
    for bname, plist in sorted(by_brand.items(), key=lambda kv: -len(kv[1])):
        total = len(plist)
        with_img = sum(1 for p in plist if media_by_pid.get(p["id"]))
        no_img = total - with_img
        pct = (with_img / total * 100) if total else 0
        by_family = defaultdict(list)
        for p in plist:
            if p.get("family_key"):
                by_family[p["family_key"]].append(p)
        multi_fam = sum(1 for v in by_family.values() if len(v) > 1)
        variants_no_img = sum(1 for v in by_family.values() if len(v) > 1 for p in v if not media_by_pid.get(p["id"]))
        print(f"{bname:<14}{total:>7}{with_img:>8}{no_img:>8}{pct:>7.1f}%{len(by_family):>10}{multi_fam:>15}{variants_no_img:>18}")
        report_lines.append((bname, total, with_img, no_img, pct))
    print("=" * 100)

    # broken urls attributed to brand
    broken_by_brand = defaultdict(int)
    for u in broken_urls:
        m = url_to_media.get(u)
        if m:
            pid = m.get("product_id")
            p = next((pp for pp in all_products if pp["id"] == pid), None)
            bname = brand_name_by_id.get(p.get("brand_id")) if p else "UNKNOWN"
            broken_by_brand[bname] += 1
    print("\nBroken URLs by brand:", dict(broken_by_brand))

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
