from services.media_snapshot_recovery import plan_snapshot_media_restore


def test_plan_restores_only_exact_id_matched_changed_pointers():
    current = [
        {"id": "changed", "bucket": "forge-products", "storage_key": "new.webp", "sha1": "new", "width": 1600, "height": 1000},
        {"id": "same", "bucket": "forge-products", "storage_key": "same.webp", "sha1": "same", "width": 1600, "height": 1000},
        {"id": "new-after-snapshot", "bucket": "forge-products", "storage_key": "later.webp"},
    ]
    snapshot = [
        {"id": "changed", "bucket": "forge-products", "storage_key": "original.webp", "sha1": "original", "width": 600, "height": 900},
        {"id": "same", "bucket": "forge-products", "storage_key": "same.webp", "sha1": "same", "width": 1600, "height": 1000},
    ]

    plan = plan_snapshot_media_restore(current, snapshot)

    assert [item["media_id"] for item in plan] == ["changed"]
    assert plan[0]["before"]["storage_key"] == "new.webp"
    assert plan[0]["after"]["storage_key"] == "original.webp"


def test_plan_rejects_snapshot_rows_without_a_restorable_pointer():
    assert plan_snapshot_media_restore(
        [{"id": "m1", "storage_key": "current.webp"}],
        [{"id": "m1", "storage_key": "", "bucket": "forge-products"}],
    ) == []


def test_plan_does_not_overwrite_an_unrelated_later_edit():
    assert plan_snapshot_media_restore(
        [{"id": "m1", "bucket": "forge-products", "storage_key": "later.webp", "width": 1200, "height": 800}],
        [{"id": "m1", "bucket": "forge-products", "storage_key": "old.webp", "width": 600, "height": 900}],
    ) == []
