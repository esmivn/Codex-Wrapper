import asyncio
import time
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .auth import decode_token


security = HTTPBearer(auto_error=False)
_rate_lock = asyncio.Lock()
_rate_data = {}


async def verify_api_key(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> None:
    """Verify bearer token: accept PROXY_API_KEY or a valid JWT user token."""
    if not credentials:
        # No credentials and no PROXY_API_KEY configured → allow (open mode)
        if not settings.proxy_api_key:
            return
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    token = credentials.credentials
    # Accept if it matches the static PROXY_API_KEY
    if settings.proxy_api_key and token == settings.proxy_api_key:
        return
    # Accept if it's a valid JWT user token
    if decode_token(token):
        return
    # If PROXY_API_KEY is not set but a token was provided (could be JWT), still allow
    if not settings.proxy_api_key:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict[str, Any]:
    """Extract and validate user from JWT bearer token."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = decode_token(credentials.credentials)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Require the current user to have admin role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user


async def get_request_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Extract user_id from JWT token, or fall back to DEFAULT_USER_ID for API-key auth."""
    from .session_workspace import DEFAULT_USER_ID
    if credentials:
        user = decode_token(credentials.credentials)
        if user:
            return user["username"]
    return DEFAULT_USER_ID


async def rate_limiter(request: Request) -> None:
    """Simple in-memory rate limiter per IP address."""
    if settings.rate_limit_per_minute <= 0:
        return

    ip = request.client.host if request.client else "anonymous"
    now = time.time()
    window = 60
    async with _rate_lock:
        count, reset = _rate_data.get(ip, (0, now + window))
        if reset < now:
            count, reset = 0, now + window
        if count >= settings.rate_limit_per_minute:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        _rate_data[ip] = (count + 1, reset)
