"""Shared analytics layer for the Executive Operating System.

One canonical filter builder, one comparison engine, one cache, one metric
registry. Every workspace consumes these; no workspace reimplements a KPI.
See docs/superpowers/specs/2026-08-01-executive-operating-system-design.md.
"""
