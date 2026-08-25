"""Media storage factory. Reads validated settings and returns the configured driver."""
from __future__ import annotations
from functools import lru_cache

from settings import settings

from .base import MediaStorage
from .supabase_driver import SupabaseStorageDriver


@lru_cache(maxsize=1)
def get_media_storage() -> MediaStorage:
    driver = settings.media_storage_driver
    if driver == "supabase":
        return SupabaseStorageDriver()
    raise RuntimeError(f"Unknown MEDIA_STORAGE_DRIVER={driver!r}. Supported: supabase")


def public_bucket() -> str:
    return settings.supabase_public_bucket


def private_bucket() -> str:
    return settings.supabase_private_bucket
