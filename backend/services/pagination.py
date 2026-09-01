"""Shared defensive bounds for public collection endpoints."""

MAX_PAGE_LIMIT = 100


def normalize_pagination(skip: int, limit: int, *, max_limit: int = MAX_PAGE_LIMIT) -> tuple[int, int]:
    """Reject offsets and page sizes that could create surprising or costly reads."""
    # Direct route invocation in unit tests/internal callers leaves FastAPI's
    # ``Query`` default object in place. HTTP requests always supply integers.
    skip = getattr(skip, "default", skip)
    limit = getattr(limit, "default", limit)
    if skip < 0:
        raise ValueError("skip must be greater than or equal to zero")
    if limit < 1:
        raise ValueError("limit must be greater than or equal to one")
    return skip, min(limit, max_limit)


def validate_pagination(skip: int, limit: int, *, max_limit: int = MAX_PAGE_LIMIT) -> None:
    """Compatibility wrapper for callers that only need validation."""
    normalize_pagination(skip, limit, max_limit=max_limit)
