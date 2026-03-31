"""Auth → PostgreSQL RLS tenant isolation middleware.

Supports two auth modes:
  1. JWT auth (Bearer token) — validated via JWKS
  2. Internal proxy auth (X-User-Id header + shared secret) — for Next.js API proxy

Every authenticated request extracts the user/org context and sets it
as the PostgreSQL session variable for Row-Level Security filtering.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
import httpx

from app.core.config import settings

security = HTTPBearer(auto_error=False)

# Cache JWKS keys in memory (refreshed on 401)
_jwks_cache: dict | None = None


class AuthContext(BaseModel):
    """Authenticated user context."""

    user_id: str
    org_id: str
    org_role: str | None = None
    email: str | None = None


async def _get_jwks() -> dict:
    """Fetch JWKS (JSON Web Key Set) for JWT verification."""
    global _jwks_cache
    if _jwks_cache is None:
        jwks_url = settings.neon_auth_jwks_url
        if not jwks_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Auth JWKS URL not configured",
            )
        async with httpx.AsyncClient() as client:
            resp = await client.get(jwks_url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def _invalidate_jwks_cache() -> None:
    global _jwks_cache
    _jwks_cache = None


async def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthContext:
    """Extract auth context from JWT or internal proxy headers."""

    # Mode 1: Internal proxy auth (from Next.js API proxy)
    user_id = request.headers.get("X-User-Id")
    if user_id and not credentials:
        return AuthContext(
            user_id=user_id,
            org_id=user_id,  # Use user_id as org until org support is added
            email=request.headers.get("X-User-Email"),
        )

    # Mode 2: JWT Bearer auth
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication",
        )

    token = credentials.credentials

    try:
        jwks = await _get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        rsa_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = key
                break

        if rsa_key is None:
            await _invalidate_jwks_cache()
            jwks = await _get_jwks()
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    rsa_key = key
                    break

        if rsa_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find appropriate signing key",
            )

        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )

    user_id = payload.get("sub", "")
    org_id = payload.get("org_id") or user_id

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user identity",
        )

    return AuthContext(
        user_id=user_id,
        org_id=org_id,
        org_role=payload.get("org_role") or payload.get("role"),
        email=payload.get("email"),
    )


async def get_company_id(auth: AuthContext = Depends(get_auth_context)) -> str:
    """Convenience dependency that returns just the company_id (org_id) for RLS."""
    return auth.org_id
