"""Authentication and authorization primitives (D-04, D-08).

``PUBLIC_ROUTES`` is the explicit allowlist of routes that need no principal. Every other
route must declare a permission.
"""

from __future__ import annotations

PUBLIC_ROUTES: frozenset[str] = frozenset({"/healthz"})
