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
