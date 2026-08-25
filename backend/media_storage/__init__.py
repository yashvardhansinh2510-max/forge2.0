"""Media storage abstraction.

All application code MUST import from this package only. Concrete providers
(Supabase / Local / R2 / S3) live behind the `MediaStorage` interface so we
can swap providers without touching business logic.
"""
from .base import MediaStorage, StoredObject, StorageError
from .factory import get_media_storage

__all__ = ["MediaStorage", "StoredObject", "StorageError", "get_media_storage"]
