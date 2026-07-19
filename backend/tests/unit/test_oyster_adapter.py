from catalog_pipeline.adapters.oyster import normalize_finish, sku_for, family_key_for, category_from_filename


def test_normalize_finish_covers_all_known_supplier_variants():
    cases = {
        "CROME": "Chrome", "CHROME": "Chrome", "CEROME": "Chrome", "CEOME": "Chrome",
        "MAAT BLACK": "Matt Black", "MAAT BALCK": "Matt Black",
        "MATE BLACK": "Matt Black", "MATT BLACK": "Matt Black",
        "BRUSHED GOLD": "Brushed Gold", "Brushed\xa0GOLD": "Brushed Gold",
        "ROSE GOLD": "Rose Gold", "ROSE GOLD ": "Rose Gold",
        "BRUSHED ROSE GOLD": "Brushed Rose Gold", "BRUSHE ROSE GLOD": "Brushed Rose Gold",
        "Brushed ROSE\xa0GOLD": "Brushed Rose Gold",
        "BRUSHED GUN METAL": "Brushed Gun Metal", "Brushed GUN METAL": "Brushed Gun Metal",
        "GUN METAL": "Gun Metal",
    }
    for raw, expected_label in cases.items():
        label, code, note = normalize_finish(raw)
        assert label == expected_label, f"{raw!r} -> {label!r}, expected {expected_label!r}"
        assert code and code.isupper()


def test_normalize_finish_repairs_corrupted_merged_cell_values():
    # Two real cells in the source files literally contain "CROME+B3:E16" /
    # "CROME+B3:L44" — a corrupted merged-cell artifact. The finish name is
    # recoverable (everything before the "+"); flag it via the returned note.
    label, code, note = normalize_finish("CROME+B3:E16")
    assert label == "Chrome"
    assert code == "CR"
    assert note and "repaired" in note.lower()


def test_normalize_finish_flags_unrecognized_values_for_manual_review():
    label, code, note = normalize_finish("SOME NEW TYPO NOBODY HAS SEEN")
    assert label is None
    assert code is None
    assert note and "manual review" in note.lower()


def test_category_from_filename_matches_all_four_real_source_files():
    assert category_from_filename("OYSTER BODY JET.xlsx") == ("Body Jet", "BODYJET")
    assert category_from_filename("OYSTER SHOWER.xlsx") == ("Shower", "SHOWER")
    assert category_from_filename("OYSTER SPOUT&HS&ANGLE W& TIGGER.xlsx") == (
        "Outlet / Hand Shower / Angle Valve", "OUTLETHSANGLE",
    )
    assert category_from_filename("OYSTER BESIN MIXER.xlsx") == ("Basin Mixer", "BASINMIXER")


def test_category_from_filename_raises_on_unknown_file():
    import pytest
    with pytest.raises(ValueError):
        category_from_filename("some_unrelated_file.xlsx")


def test_sku_and_family_key_are_deterministic_across_calls():
    # Idempotency requirement: re-running the import must regenerate the
    # SAME sku/family_key for the same inputs, so orchestrator.import_accepted
    # updates the existing product instead of creating a duplicate.
    sku1 = sku_for("BODYJET", "Brook CP Fittings WAVE JET", "CR")
    sku2 = sku_for("BODYJET", "Brook CP Fittings WAVE JET", "CR")
    assert sku1 == sku2 == "OYSTER-BODYJET-BROOKCPFITTINGSWAVEJET-CR"

    fk1 = family_key_for("body-jet", "Brook CP Fittings WAVE JET")
    fk2 = family_key_for("body-jet", "Brook CP Fittings WAVE JET")
    assert fk1 == fk2 == "oyster:body-jet:brook-cp-fittings-wave-jet"


def test_sku_differs_by_finish_within_same_family():
    sku_chrome = sku_for("BODYJET", "Wave Jet", "CR")
    sku_black = sku_for("BODYJET", "Wave Jet", "MB")
    assert sku_chrome != sku_black


import io
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

from catalog_pipeline.adapters.oyster import OysterAdapter
from catalog_pipeline.base import MISSING


def _tiny_png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (200, 200), color=(120, 120, 120)).save(buf, format="PNG")
    return buf.getvalue()


def _build_body_jet_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BODY JET"
    ws.append(["OYSTER BODY JET"])
    ws.append(["Sr.\nNo.", "finishes", "Product Discription", "Product Image", "MRP",
               "QTY", "MRP TOTAL", "DISCOUNT", None, "OFFER RATE", "TOTAL"])
    # One family ("Wave Jet"), two finishes — one WITH a discount/offer rate,
    # one WITHOUT (offer rate must fall back to MRP), one row has NO image.
    ws.append([1, "CROME", "Brook CP Fittings WAVE JET", None, 18500, None, 0, 50, 9250, 9250, 0])
    ws.append([2, "MAAT BALCK", "Brook CP Fittings WAVE JET", None, 19500, None, 0, None, 0, 19500, 0])
    # A second family with only one finish and no MRP (missing-data case).
    ws.append([3, "GUN METAL", "BROOK UP FITTINGS JET-X", None, None, None, 0, None, 0, 0, 0])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    # openpyxl doesn't easily re-embed a floating image keyed to a specific
    # cell through the public API after save+reload in one step here, so this
    # fixture builds the image via a second pass using openpyxl's own
    # add_image on row 3 (Sr.No.=1) only, leaving rows 4 and 5 imageless —
    # exactly mirroring the real Basin Mixer/Shower files' "a few rows have
    # no image" reality.
    wb2 = Workbook()
    ws2 = wb2.active
    ws2.title = "BODY JET"
    for row in ws.iter_rows(values_only=True):
        ws2.append(list(row))
    img = XLImage(io.BytesIO(_tiny_png_bytes()))
    img.anchor = "D3"  # row 3 = first data row (Sr.No.=1, CROME)
    ws2.add_image(img)
    out = io.BytesIO()
    wb2.save(out)
    return out.getvalue()


def test_extract_groups_variants_into_one_family_and_generates_stable_skus():
    data = _build_body_jet_workbook()
    adapter = OysterAdapter()
    rows, report = adapter.extract(data, "OYSTER BODY JET.xlsx")

    assert report.parsed_rows == 3
    wave_jet_rows = [r for r in rows if "WAVE JET" in (r.description or "")]
    assert len(wave_jet_rows) == 2
    assert wave_jet_rows[0].family_key == wave_jet_rows[1].family_key == "oyster:body-jet:brook-cp-fittings-wave-jet"
    assert {r.finish for r in wave_jet_rows} == {"Chrome", "Matt Black"}
    assert len({r.sku for r in wave_jet_rows}) == 2  # different finishes -> different SKUs

    chrome_row = next(r for r in wave_jet_rows if r.finish == "Chrome")
    assert chrome_row.sku == "OYSTER-BODYJET-BROOKCPFITTINGSWAVEJET-CR"
    assert chrome_row.mrp == 18500.0
    assert chrome_row.dealer_price == 9250.0
    assert chrome_row.images  # image anchored at D3

    matt_black_row = next(r for r in wave_jet_rows if r.finish == "Matt Black")
    assert matt_black_row.dealer_price == 19500.0  # no discount -> falls back to MRP
    assert not matt_black_row.images  # no image anchored on this row
    assert "No image mapped" in " ".join(matt_black_row.issues)

    jetx_row = next(r for r in rows if "JET-X" in (r.description or ""))
    assert jetx_row.mrp == MISSING
    assert "Missing MRP" in jetx_row.issues


def test_extract_returns_empty_with_warning_for_unmappable_filename():
    data = _build_body_jet_workbook()
    adapter = OysterAdapter()
    rows, report = adapter.extract(data, "totally_unrelated.xlsx")
    assert rows == []
    assert report.warnings
