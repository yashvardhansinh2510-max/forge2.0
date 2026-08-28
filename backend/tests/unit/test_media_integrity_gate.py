import io
from PIL import Image
from services.media_integrity_gate import inspect_media_bytes


def _png() -> bytes:
    buf = io.BytesIO(); Image.new("RGB", (2, 3), "white").save(buf, format="PNG"); return buf.getvalue()


def test_media_gate_accepts_matching_decodable_png():
    data = _png()
    import hashlib
    assert inspect_media_bytes({"size_bytes": len(data), "sha1": hashlib.sha1(data).hexdigest(), "mime": "image/png", "width": 2, "height": 3}, data) == []


def test_media_gate_reports_metadata_and_decode_failures():
    issues = inspect_media_bytes({"size_bytes": 1, "sha1": "bad", "mime": "image/jpeg"}, b"not image")
    assert {issue["kind"] for issue in issues} == {"size_mismatch", "hash_mismatch", "undecodable"}
