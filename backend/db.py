"""MongoDB connection + helpers. Central place so routes don't reconnect."""
from motor.motor_asyncio import AsyncIOMotorClient

from settings import settings

_client = AsyncIOMotorClient(settings.mongo_url)
client = _client
db = _client[settings.db_name]


def strip_id(doc: dict | None) -> dict | None:
    """Remove the internal Mongo _id from a doc so responses stay JSON-safe."""
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def strip_ids(docs: list[dict]) -> list[dict]:
    for d in docs:
        d.pop("_id", None)
    return docs
