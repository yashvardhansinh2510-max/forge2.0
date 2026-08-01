"""create_payment must invalidate the analytics cache after it commits — the
same post-commit, swallow-and-log discipline domain_outbox.py already uses
for every other write that changes reported revenue."""
from __future__ import annotations

import ast
from pathlib import Path


def test_create_payment_calls_cache_bump_after_the_transaction_commits():
    source = Path("routes/payment_routes.py").read_text()
    tree = ast.parse(source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_payment")
    calls = [ast.dump(n) for n in ast.walk(func) if isinstance(n, ast.Call)]
    assert any('bump' in c and "'payments'" in c for c in calls), (
        "create_payment never calls cache.bump('payments') — Collections/Outstanding "
        "will silently serve a stale figure after a payment is recorded"
    )


def test_the_bump_call_is_not_nested_inside_the_transaction_try_block():
    """A bump for a transaction that then rolls back would be worse than a
    stale read — it must sit after the try/except at function indentation,
    the same rule Stage B's Task 8 (Phase 1) enforced for domain_outbox.py."""
    source = Path("routes/payment_routes.py").read_text()
    tree = ast.parse(source)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_payment")
    bump_call = next(
        n for n in ast.walk(func)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "bump"
    )
    try_blocks = [n for n in ast.walk(func) if isinstance(n, ast.Try)]
    # Check only the outermost (main transaction) try block, not nested ones or cache-error ones
    main_try_block = min(try_blocks, key=lambda b: b.lineno)
    block_lines = range(main_try_block.lineno, (main_try_block.end_lineno or main_try_block.lineno) + 1)
    assert bump_call.lineno not in block_lines, (
        "cache.bump appears to be called inside the payment-insert try/except — "
        "it must run only after commit succeeds"
    )
