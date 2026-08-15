from io import BytesIO

from PIL import Image

import services.media_service as media_service
from media_storage.base import StoredObject
from services.product_image_normalizer import PRODUCT_IMAGE_ASPECT_RATIO, normalize_product_image


def _image_bytes(size: tuple[int, int], *, fmt: str = "PNG", exif_orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, "red")
    out = BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[274] = exif_orientation
        kwargs["exif"] = exif
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def _size(data: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(data)) as image:
        return image.size


def test_portrait_image_is_centered_on_exact_landscape_canvas():
    data, mime = normalize_product_image(_image_bytes((60, 120)), "image/png")
    assert mime == "image/png"
    assert _size(data) == (192, 120)
    with Image.open(BytesIO(data)) as image:
        assert image.getpixel((0, 0)) == (255, 255, 255)
        assert image.getpixel((96, 60)) == (255, 0, 0)


def test_square_and_landscape_sources_become_16_by_10_without_crop():
    square, _ = normalize_product_image(_image_bytes((100, 100)), "image/png")
    landscape, _ = normalize_product_image(_image_bytes((320, 200)), "image/png")
    assert _size(square) == (160, 100)
    assert _size(landscape) == (320, 200)
    for data in (square, landscape):
        width, height = _size(data)
        assert width / height == PRODUCT_IMAGE_ASPECT_RATIO


def test_exif_orientation_is_applied_before_landscape_padding():
    data, mime = normalize_product_image(_image_bytes((60, 120), fmt="JPEG", exif_orientation=6), "image/jpeg")
    assert mime == "image/jpeg"
    assert _size(data) == (120, 75)


def test_gif_is_flattened_to_a_printable_landscape_png():
    data, mime = normalize_product_image(_image_bytes((50, 100), fmt="GIF"), "image/gif")
    assert mime == "image/png"
    assert _size(data) == (160, 100)


def test_non_image_media_is_not_modified():
    source = b"%PDF-1.4 sample"
    assert normalize_product_image(source, "application/pdf") == (source, "application/pdf")


def test_media_service_stores_normalized_bytes_and_dimensions(monkeypatch):
    class ProductMediaCollection:
        async def find_one(self, *_args, **_kwargs):
            return None

        async def insert_one(self, doc):
            self.inserted = doc

    class Db:
        product_media = ProductMediaCollection()

    uploaded = {}

    class Storage:
        async def upload(self, *, bucket, key, data, content_type):
            uploaded.update(bucket=bucket, key=key, data=data, content_type=content_type)
            return StoredObject(bucket, key, "https://example.test/image", len(data), content_type, "sha")

    async def no_log(**_kwargs):
        return None

    monkeypatch.setattr(media_service, "db", Db())
    monkeypatch.setattr(media_service, "get_media_storage", lambda: Storage())
    monkeypatch.setattr(media_service, "public_bucket", lambda: "products")
    monkeypatch.setattr(media_service, "log_event", no_log)

    import asyncio
    result = asyncio.run(media_service.upload_and_register(
        data=_image_bytes((50, 100)), mime="image/png", brand_slug="test", product_id="p1",
        floor_id="first-floor", source_type="manufacturer", role="gallery",
    ))

    assert _size(uploaded["data"]) == (160, 100)
    assert uploaded["content_type"] == "image/png"
    assert (result.width, result.height) == (160, 100)
