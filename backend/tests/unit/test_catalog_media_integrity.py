from services.catalog_media_integrity import find_media_integrity_issues


def test_detects_and_describes_stale_product_family_key_without_guessing():
    products = [{"id": "p1", "brand_id": "axor", "floor_id": "first-floor", "family_key": "axor:starck"}]
    media = [{"id": "m1", "product_id": "p1", "brand_id": "axor", "floor_id": "first-floor", "family_key": "axor:misc"}]

    assert find_media_integrity_issues(products, media) == [{
        "media_id": "m1", "kind": "foreign_product_family", "product_id": "p1",
        "expected_family_key": "axor:starck", "actual_family_key": "axor:misc",
    }]


def test_reports_orphan_and_identityless_media_rows():
    issues = find_media_integrity_issues([], [
        {"id": "orphan", "product_id": "gone"},
        {"id": "identityless"},
        {"id": "family-orphan", "brand_id": "b", "floor_id": "f", "family_key": "gone"},
    ])

    assert {issue["kind"] for issue in issues} == {"orphan_product", "identityless", "orphan_family"}
