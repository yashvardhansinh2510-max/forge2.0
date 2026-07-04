"""Adapter registry — pick the right adapter for a brand."""
from .grohe import GroheAdapter
from .geberit import GeberitAdapter
from .vitra import VitraAdapter

REGISTRY = {
    "grohe": GroheAdapter,
    "geberit": GeberitAdapter,
    "vitra": VitraAdapter,
    # Hansgrohe + Axor share Grohe's Hansgrohe-like format; use Grohe adapter as a starting
    # point until a dedicated file is available.
    "hansgrohe": GroheAdapter,
    "axor": GroheAdapter,
}


def get_adapter(brand: str):
    key = (brand or "").strip().lower()
    if key not in REGISTRY:
        raise ValueError(f"No adapter for brand '{brand}'. Available: {sorted(REGISTRY)}")
    return REGISTRY[key]()
