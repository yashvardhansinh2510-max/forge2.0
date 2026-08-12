import io

from openpyxl import Workbook

from catalog_pipeline.adapters import get_adapter
from catalog_pipeline.adapters.renite import ReniteAdapter, family_key_for, sku_for
from catalog_pipeline.certifier import validate


def _workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["SR.", "PRODUCT NAME", "IMAGE", "PRODUCT SIZE", "FINISHES", "BOX IN PIS", "BOX SQFT", "RATE"])
    sheet.append([1, "DESTINA SMOKEY", None, "600X1200", "MATT", 2, 15.5, "85 PER SQFT"])
    sheet.append([2, "DESTINA SMOKEY", None, "600X1200", "MATT", 2, 15.5, "85 PER SQFT"])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_renite_rows_are_ground_floor_tile_shape_and_deterministic():
    rows, report = ReniteAdapter().extract(_workbook(), "RENITE 2026.xlsx")

    assert report.parsed_rows == 2
    assert [row.sku for row in rows] == ["RENITE-DESTINASMOKEY-600X1200-MT", "RENITE-DESTINASMOKEY-600X1200-MT-2"]
    assert all(row.brand == "Renite" and row.category == "Tiles" for row in rows)
    assert all(row.mrp == 85.0 and row.specs["sqft_per_box"] == 15.5 for row in rows)
    assert all("No image mapped" in row.issues[0] for row in rows)


def test_renite_family_sku_and_registry_are_stable():
    assert family_key_for("DESTINA SMOKEY") == "renite:destina-smokey"
    assert sku_for("DESTINA SMOKEY", "600X1200", "MT") == "RENITE-DESTINASMOKEY-600X1200-MT"
    assert isinstance(get_adapter("RENITE"), ReniteAdapter)


def test_renite_valid_rows_auto_accept_despite_missing_supplier_images():
    rows, _ = ReniteAdapter().extract(_workbook(), "RENITE 2026.xlsx")
    validated, cert = validate(rows)

    assert cert.duplicates_sku == 0
    assert cert.missing_images == 2
    assert all(row.confidence >= 0.85 for row in validated)
