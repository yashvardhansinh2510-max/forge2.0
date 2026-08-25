from catalog_pipeline.adapters.dimore import normalize_finish, parse_rate_per_sqft, sku_for, family_key_for
from catalog_pipeline.base import MISSING


def test_normalize_finish_covers_all_nine_observed_supplier_values():
    cases = {
        "LUMINOSO": "Luminoso", "OPACO NATURAL": "Opaco Natural", "SETADURA": "Setadura",
        "BALANCIO": "Balancio", "MATT": "Matt", "GRANULO NATURALE": "Granulo Naturale",
        "PIETRA NATURALE": "Pietra Naturale", "BRILLIO": "Brillio", "FIGURA": "Figura",
        "matt": "Matt",  # case-insensitive
        " LUMINOSO ": "Luminoso",  # whitespace-tolerant
    }
    for raw, expected_label in cases.items():
        label, code, note = normalize_finish(raw)
        assert label == expected_label, f"{raw!r} -> {label!r}, expected {expected_label!r}"
        assert code and code.isupper()
        assert note is None


def test_normalize_finish_flags_unrecognized_values_for_manual_review():
    label, code, note = normalize_finish("SOME NEW FINISH NOBODY HAS SEEN")
    assert label is None
    assert code is None
    assert note and "manual review" in note.lower()


def test_parse_rate_per_sqft_handles_the_real_source_format():
    assert parse_rate_per_sqft("360 PER SQFT") == (360.0, None)
    assert parse_rate_per_sqft("245 per sqft") == (245.0, None)
    assert parse_rate_per_sqft("1,250 PER SQFT") == (1250.0, None)


def test_parse_rate_per_sqft_flags_unrecognized_formats_without_crashing():
    value, note = parse_rate_per_sqft("TBD")
    assert value is None
    assert note and "RATE" in note


def test_sku_and_family_key_are_deterministic_across_calls():
    sku1 = sku_for("BARDIGLIO BIANCO", "1200X2400", "LU")
    sku2 = sku_for("BARDIGLIO BIANCO", "1200X2400", "LU")
    assert sku1 == sku2 == "DIMORE-BARDIGLIOBIANCO-1200X2400-LU"

    fk1 = family_key_for("BARDIGLIO BIANCO")
    fk2 = family_key_for("BARDIGLIO BIANCO")
    assert fk1 == fk2 == "dimore:bardiglio-bianco"


def test_sku_differs_by_size_and_finish_within_same_family():
    base = sku_for("BARDIGLIO BIANCO", "1200X2400", "LU")
    diff_finish = sku_for("BARDIGLIO BIANCO", "1200X2400", "ON")
    diff_size = sku_for("BARDIGLIO BIANCO", "1200X1800", "LU")
    assert len({base, diff_finish, diff_size}) == 3


import io

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

from catalog_pipeline.adapters.dimore import DimoreAdapter


def _build_workbook(*, with_image_on_row2: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # This source has NO "SERIES NAME" column — unlike Qutone.
    ws.append(["SR.", "company NAME", "PRODUCT NAME", "IMAGE", "PRODUCT SIZE", "FINISHES", "BOX IN PIS", "BOX SQFT", "RATE"])
    ws.append([1, "DIMORE", "BARDIGLIO BIANCO", None, "1200X2400", "LUMINOSO", 1, 31, "360 PER SQFT"])
    ws.append([2, "DIMORE", "BARDIGLIO BIANCO", None, "1200X2400", "OPACO NATURAL", 1, 31, "360 PER SQFT"])
    ws.append([3, "DIMORE", "BARDIGLIO BIANCO", None, "1200X1800", "WEIRDFINISH", 2, 46.5, "300 PER SQFT"])
    ws.append([4, "DIMORE", "ROCCIA STELLAR", None, "1200X2400", "PIETRA NATURALE", 1, 31, "not a rate"])

    if with_image_on_row2:
        buf = io.BytesIO()
        PILImage.new("RGB", (199, 367), color=(200, 100, 50)).save(buf, format="JPEG")
        buf.seek(0)
        img = XLImage(buf)
        img.anchor = "D2"
        ws.add_image(img)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_extracts_all_rows_with_deterministic_sku():
    data = _build_workbook()
    rows, report = DimoreAdapter().extract(data, "DIMORE 2026.xlsx")
    assert report.parsed_rows == 4
    assert len(rows) == 4
    rows2, _ = DimoreAdapter().extract(data, "DIMORE 2026.xlsx")
    assert [r.sku for r in rows] == [r.sku for r in rows2]


def test_family_key_groups_same_product_across_finishes_and_sizes():
    data = _build_workbook()
    rows, _ = DimoreAdapter().extract(data, "DIMORE 2026.xlsx")
    bardiglio_rows = [r for r in rows if r.name.startswith("BARDIGLIO BIANCO")]
    assert len(bardiglio_rows) == 3
    assert len({r.family_key for r in bardiglio_rows}) == 1
    roccia = next(r for r in rows if r.name.startswith("ROCCIA STELLAR"))
    assert roccia.family_key != bardiglio_rows[0].family_key


def test_size_and_pricing_fields_map_correctly():
    data = _build_workbook()
    rows, _ = DimoreAdapter().extract(data, "DIMORE 2026.xlsx")
    r = rows[0]
    assert r.size == "1200X2400"
    assert r.mrp == 360.0
    assert r.dealer_price == 360.0
    assert r.specs["pcs_per_box"] == "1"
    assert r.specs["sqft_per_box"] == 31
    assert r.category == "Tiles"
    assert r.brand == "Dimore"
    assert r.series == MISSING  # this source has no SERIES NAME column


def test_unrecognized_finish_is_flagged_not_dropped():
    data = _build_workbook()
    rows, _ = DimoreAdapter().extract(data, "DIMORE 2026.xlsx")
    weird = next(r for r in rows if r.size == "1200X1800")
    assert weird.finish_code == MISSING
    assert any("needs manual review" in issue for issue in weird.issues)


def test_malformed_rate_is_flagged_and_priced_at_zero_not_dropped():
    data = _build_workbook()
    rows, _ = DimoreAdapter().extract(data, "DIMORE 2026.xlsx")
    roccia = next(r for r in rows if r.name.startswith("ROCCIA STELLAR"))
    assert roccia.mrp == 0.0
    assert any("RATE" in issue for issue in roccia.issues)
    assert roccia.specs.get("needs_pricing") is True


def test_row_without_embedded_image_is_flagged_missing():
    data = _build_workbook(with_image_on_row2=False)
    rows, report = DimoreAdapter().extract(data, "DIMORE 2026.xlsx")
    assert report.images_mapped == 0
    assert all(not r.images for r in rows)
    assert all(any("No image mapped" in issue for issue in r.issues) for r in rows)


def test_row_with_embedded_image_is_mapped_with_correct_dimensions():
    data = _build_workbook(with_image_on_row2=True)
    rows, report = DimoreAdapter().extract(data, "DIMORE 2026.xlsx")
    assert report.images_mapped == 1
    imaged = [r for r in rows if r.images]
    assert len(imaged) == 1
    assert imaged[0].image_meta[0]["width"] == 199
    assert imaged[0].image_meta[0]["height"] == 367


def test_dimore_is_registered_in_the_adapter_registry():
    from catalog_pipeline.adapters import get_adapter
    from catalog_pipeline.adapters.dimore import DimoreAdapter as _DA

    adapter = get_adapter("dimore")
    assert isinstance(adapter, _DA)


def test_dimore_case_insensitive_lookup():
    from catalog_pipeline.adapters import get_adapter

    assert get_adapter("Dimore").brand == "Dimore"
    assert get_adapter("DIMORE").brand == "Dimore"
