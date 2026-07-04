"""MongoDB connection + helpers. Central place so routes don't reconnect."""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = _client[os.environ["DB_NAME"]]


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
