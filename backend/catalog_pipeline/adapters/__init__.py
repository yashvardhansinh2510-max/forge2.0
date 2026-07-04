"""Adapter registry — pick the right adapter for a brand."""
from .grohe import GroheAdapter
from .geberit import GeberitAdapter
from .vitra import VitraAdapter
from .hansgrohe import HansgroheAdapter

REGISTRY = {
    "grohe": GroheAdapter,
    "geberit": GeberitAdapter,
    "vitra": VitraAdapter,
    # Hansgrohe (with AXOR merged as an internal collection).
    "hansgrohe": HansgroheAdapter,
    # AXOR routed to Hansgrohe adapter — same file format, brand folded.
    "axor": HansgroheAdapter,
}


def get_adapter(brand: str):
    key = (brand or "").strip().lower()
    if key not in REGISTRY:
        raise ValueError(f"No adapter for brand '{brand}'. Available: {sorted(REGISTRY)}")
    return REGISTRY[key]()
