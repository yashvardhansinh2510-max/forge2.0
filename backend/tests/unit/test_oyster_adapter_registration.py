def test_oyster_adapter_is_registered():
    from catalog_pipeline.adapters import get_adapter
    from catalog_pipeline.adapters.oyster import OysterAdapter
    assert isinstance(get_adapter("oyster"), OysterAdapter)
    assert isinstance(get_adapter("Oyster"), OysterAdapter)  # registry lookup is case-insensitive


def test_oyster_is_in_supported_brands_for_http_upload():
    from routes.catalog_import_routes import SUPPORTED_BRANDS
    assert "Oyster" in SUPPORTED_BRANDS
