"""MongoDB connection + helpers. Central place so routes don't reconnect."""
from motor.motor_asyncio import AsyncIOMotorClient

from settings import settings

# A bounded pool prevents an overloaded application process from opening an
# unbounded number of Atlas sockets.  Explicit timeouts keep a transient Atlas
# outage from pinning request workers indefinitely; retryable reads/writes are
# safe here because application writes already use idempotency/unique guards.
_client = AsyncIOMotorClient(
    settings.mongo_url,
    maxPoolSize=settings.mongo_max_pool_size,
    minPoolSize=settings.mongo_min_pool_size,
    connectTimeoutMS=settings.mongo_connect_timeout_ms,
    serverSelectionTimeoutMS=settings.mongo_server_selection_timeout_ms,
    socketTimeoutMS=settings.mongo_socket_timeout_ms,
    waitQueueTimeoutMS=settings.mongo_wait_queue_timeout_ms,
    retryReads=True,
    retryWrites=True,
    appname="buildcon-house-api",
)
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
