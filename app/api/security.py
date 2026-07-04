"""Bearer-token guard for the API routes.

Local-first threat model: the engine binds to 127.0.0.1, but any webpage in
the browser can still POST to localhost — the token proves the caller is the
extension/dashboard. Unset token = auth disabled (bare local development).
"""

import secrets
from typing import Annotated

from fastapi import Header, HTTPException

from app.core.config import get_settings


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().api_token
    if expected is None:
        return
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API token")
