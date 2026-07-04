"""Forge catalog ingestion framework.

Reusable pipeline: Extract → Normalize → Detect variants/families → Classify →
Extract images → Validate → Certify → Import.

Brand-specific behaviour lives in adapters (grohe.py, geberit.py, vitra.py).
Adding a new supplier is one file — no changes to the framework needed.
"""
