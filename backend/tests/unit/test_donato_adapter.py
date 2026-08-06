from pathlib import Path

from catalog_pipeline.adapters.donato import DonatoAdapter
from catalog_pipeline.certifier import validate


SOURCE = Path(__file__).resolve().parents[2] / "temp" / "donato_source_files" / "DONATO 2026.xlsx"


def test_donato_source_extracts_all_rows_and_images():
    rows, report = DonatoAdapter().extract(SOURCE.read_bytes(), SOURCE.name)

    assert len(rows) == 128
    assert report.parsed_rows == 128
    assert report.images_found == 128
    assert report.images_mapped == 128
    assert not report.warnings
    assert all(row.brand == "Donato" for row in rows)
    assert all(row.category == "Tiles" for row in rows)
    assert all(row.images for row in rows)


def test_donato_skus_are_unique_and_deterministic():
    adapter = DonatoAdapter()
    first, _ = adapter.extract(SOURCE.read_bytes(), SOURCE.name)
    second, _ = adapter.extract(SOURCE.read_bytes(), SOURCE.name)

    first_skus = [row.sku for row in first]
    second_skus = [row.sku for row in second]
    assert first_skus == second_skus
    assert len(first_skus) == len(set(first_skus))
    assert all(sku.startswith("DONATO-") for sku in first_skus)


def test_donato_rows_certify_without_manual_review():
    rows, _ = DonatoAdapter().extract(SOURCE.read_bytes(), SOURCE.name)
    validated, cert = validate(rows)

    assert cert.total_products == 128
    assert cert.duplicates_sku == 0
    assert cert.missing_images == 0
    assert all(row.status == "accepted" or row.confidence >= 0.85 for row in validated)
