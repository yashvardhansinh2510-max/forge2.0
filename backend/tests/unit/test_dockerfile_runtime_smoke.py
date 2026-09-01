from pathlib import Path


def test_runtime_image_copies_catalog_pipeline_and_imports_server():
    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()

    assert "COPY catalog_pipeline ./catalog_pipeline" in dockerfile
    assert "python -c 'import server; assert server.app'" in dockerfile
    assert "ENVIRONMENT='development'" in dockerfile
