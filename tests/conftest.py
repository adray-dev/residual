"""Session-wide test setup.

Importing `data.repositories` loads `.env` (it is the one module that owns database
access, and it calls `load_dotenv` at import). Doing it here, once, before any test module
is imported, removes an order dependency that was quietly dangerous: modules that decide
`skipif(not os.environ.get("DATABASE_URL"))` at import time only saw the variable if some
*other* test module had already imported repositories.

The whole suite therefore passed with 0 skipped while `pytest tests/test_api_underwrite.py`
on its own silently skipped all 27 tests — green either way, and green for the wrong
reason in the second case.
"""
from __future__ import annotations

from data import repositories as repo  # noqa: F401  — imported for its .env side effect
