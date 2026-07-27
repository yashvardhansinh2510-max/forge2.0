"""_referrer_fields denormalizes a referrer's name at write time from an
already-fetched Referrer doc — mirrors how customer_name is resolved from
the fetched customer doc elsewhere on this router, never trusted from the
client directly."""
from routes.quotation_routes import _referrer_fields


def test_no_referrer_doc_clears_all_three_fields():
    assert _referrer_fields("architect", None) == {
        "referrer_type": None, "referrer_id": None, "referrer_name": None,
    }


def test_referrer_doc_present_denormalizes_name():
    doc = {"id": "r1", "name": "Rakesh Sharma Architects"}
    assert _referrer_fields("architect", doc) == {
        "referrer_type": "architect", "referrer_id": "r1", "referrer_name": "Rakesh Sharma Architects",
    }


def test_referrer_doc_present_but_type_missing_still_denormalizes():
    # Defensive: even if the caller forgot to send referrer_type, a resolved
    # doc still means "there IS a referrer" — better to keep the name/id
    # than silently drop them.
    doc = {"id": "r2", "name": "Studio Verve"}
    result = _referrer_fields(None, doc)
    assert result["referrer_id"] == "r2"
    assert result["referrer_name"] == "Studio Verve"
