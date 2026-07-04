"""Media storage factory. Reads MEDIA_STORAGE_DRIVER and returns the right driver."""
from __future__ import annotations
import os
from functools import lru_cache

from .base import MediaStorage
from .supabase_driver import SupabaseStorageDriver


@lru_cache(maxsize=1)
def get_media_storage() -> MediaStorage:
    driver = os.environ.get("MEDIA_STORAGE_DRIVER", "supabase").lower()
    if driver == "supabase":
        return SupabaseStorageDriver()
    raise RuntimeError(f"Unknown MEDIA_STORAGE_DRIVER={driver!r}. Supported: supabase")


def public_bucket() -> str:
    return os.environ.get("SUPABASE_PUBLIC_BUCKET", "forge-products")


def private_bucket() -> str:
    return os.environ.get("SUPABASE_PRIVATE_BUCKET", "forge-private")
