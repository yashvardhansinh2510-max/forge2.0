"""Regression test: Ground Floor Tiles (Qutone, Dimore) products losing
their own image when swapping between products in the same family.

Root cause: `_canonical_sku_for_sha1` in `services/catalog_service.py` (and
its use inside `_apply_media`/`_primary_product_image`) treats any two
family siblings that share a byte-identical photo (same sha1) as a supplier
data-entry mistake, and hides the image on every sibling except the
lexicographically-lowest SKU. That heuristic is correct for sanitaryware
colour/finish variants (Vitra/Geberit/Grohe), where two differently-labelled
colours sharing one photo really is a mistake. It is WRONG for tiles: real
Qutone/Dimore supplier pricelists legitimately reuse one photograph across
several finish/size SKUs of the same design (confirmed live against the
production `buildcon_house` DB — e.g. Qutone family
`qutone:qflex:carrara-gold` has 6 SKUs, 2 finishes x 3 sizes, all sharing one
sha1). Applying the guard there suppressed every non-canonical SKU's own
(correctly product_id-linked) image, so swapping to another product in the
family showed no photo of its own and the UI fell back to a sibling's photo
labelled "Representative photo" — i.e. the image never appeared to update.

Fix: scope the dedup guard to non-ground-floor products only, so tiles keep
each SKU's own real photo while the original sanitaryware fix is preserved.
"""
from __future__ import annotations

from services.catalog_service import _build_snapshot, hydrate_product


def _product(pid: str, sku: str, family_key: str, floor_id: str, finish: str) -> dict:
    return {
        "id": pid, "sku": sku, "family_key": family_key, "floor_id": floor_id,
        "finish": finish, "colour": None, "brand_id": "b1", "category_id": "c1",
        "images": [], "variants": [],
    }


def _media(pid: str, sha1: str, floor_id: str, family_key: str | None = None) -> dict:
    return {
        "id": f"m-{pid}", "product_id": pid, "family_key": family_key, "brand_id": "b1",
        "floor_id": floor_id, "source_type": "supplier", "role": "gallery",
        "bucket": "forge-products", "storage_key": f"{pid}.jpg",
        "public_url": f"https://cdn.example/{pid}.jpg",
        "quality": "good", "sha1": sha1, "is_primary": True, "sort_order": 100,
    }


def test_ground_floor_tile_siblings_keep_their_own_shared_photo():
    """Two genuinely distinct tile SKUs (different finish) that legitimately
    share the same supplier photo must BOTH keep their own hero image —
    matching the real Qutone/Dimore data shape."""
    fam = "qutone:qflex:carrara-gold"
    p_matt = _product("p-matt", "SKU-MT", fam, "ground-floor", "Matt")
    p_glossy = _product("p-glossy", "SKU-GL", fam, "ground-floor", "Glossy")
    media = [
        _media("p-matt", "sha1-shared", "ground-floor"),
        _media("p-glossy", "sha1-shared", "ground-floor"),
    ]
    snapshot = _build_snapshot([p_matt, p_glossy], media, [], [], [])

    out_matt = hydrate_product(p_matt, snapshot)
    out_glossy = hydrate_product(p_glossy, snapshot)

    assert out_matt["hero_image_url"] == "https://cdn.example/p-matt.jpg"
    assert out_glossy["hero_image_url"] == "https://cdn.example/p-glossy.jpg", (
        "Non-canonical-SKU tile sibling lost its own image — swapping to it "
        "would show no photo of its own (the reported bug)."
    )


def test_ground_floor_tile_variants_are_hydrated_with_their_own_image():
    """The `variants[]` list (used for swatch/finish chips) must also show
    each NON-canonical sibling's own photo, not suppress it — this is what
    the finish-swatch row on the family/product page reads from."""
    fam = "qutone:qflex:carrara-gold"
    p_matt = _product("p-matt", "SKU-MT", fam, "ground-floor", "Matt")
    p_glossy = _product("p-glossy", "SKU-GL", fam, "ground-floor", "Glossy")
    media = [
        _media("p-matt", "sha1-shared", "ground-floor"),
        _media("p-glossy", "sha1-shared", "ground-floor"),
    ]
    snapshot = _build_snapshot([p_matt, p_glossy], media, [], [], [])

    # "SKU-GL" < "SKU-MT" lexicographically, so p_glossy is the canonical
    # owner and p_matt is the one whose image the old guard suppressed —
    # hydrate FROM the canonical product's perspective so the sibling chip
    # under test ("SKU-MT") actually exercises the suppressed path.
    out_glossy = hydrate_product(p_glossy, snapshot)
    variant = next(v for v in out_glossy["variants"] if v["sku"] == "SKU-MT")
    assert variant["image"] == "https://cdn.example/p-matt.jpg"


def test_first_floor_sanitaryware_duplicate_supplier_photo_is_still_rendered():
    """A variant's own media record must render even when its supplier file
    is byte-identical to a sibling. Suppressing it produces a false missing
    image and the ProductImage fallback icon."""
    fam = "vitra:csw:memoria"
    p_white = _product("p-white", "SKU-A-WHITE", fam, "first-floor", None)
    p_matt_white = _product("p-mattwhite", "SKU-B-MATTWHITE", fam, "first-floor", None)
    media = [
        _media("p-white", "sha1-dupe", "first-floor"),
        _media("p-mattwhite", "sha1-dupe", "first-floor"),
    ]
    snapshot = _build_snapshot([p_white, p_matt_white], media, [], [], [])

    out_white = hydrate_product(p_white, snapshot)
    out_matt_white = hydrate_product(p_matt_white, snapshot)

    assert out_white["hero_image_url"] == "https://cdn.example/p-white.jpg"
    assert out_matt_white["hero_image_url"] == "https://cdn.example/p-mattwhite.jpg"


def test_product_gallery_exposes_media_family_identity_to_renderers():
    """The UI must be able to reject a higher-quality image from another
    family when supplier metadata accidentally attaches it to this product."""
    fam = "geberit:omega:109.791"
    product = _product("p-omega", "109.791.00.1", fam, "first-floor", None)
    media = [_media("p-omega", "sha1-omega", "first-floor", family_key=fam)]
    snapshot = _build_snapshot([product], media, [], [], [])

    gallery = hydrate_product(product, snapshot)["gallery"]

    assert gallery[0]["family_key"] == fam
