"""Clerk JWT → PostgreSQL RLS tenant isolation middleware.

This is the security-critical bridge between Clerk auth and database RLS.
Every authenticated request extracts org_id from the Clerk JWT and sets it
as the PostgreSQL session variable for Row-Level Security filtering.

Flow:
  1. Request arrives with Authorization: Bearer <clerk_jwt>
  2. Middleware validates JWT signature via Clerk JWKS
  3. Extracts org_id from JWT claims
  4. Sets `app.current_company_id` on the DB connection via SET LOCAL
  5. All subsequent queries are filtered by RLS automatically
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
import httpx

from app.core.config import settings

security = HTTPBearer()

# Cache JWKS keys in memory (refreshed on 401)
_jwks_cache: dict | None = None


class AuthContext(BaseModel):
    """Authenticated user context extracted from Clerk JWT."""

    user_id: str
    org_id: str
    org_role: str | None = None
    email: str | None = None


async def _get_jwks() -> dict:
    """Fetch Clerk JWKS (JSON Web Key Set) for JWT verification."""
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(settings.clerk_jwks_url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def _invalidate_jwks_cache() -> None:
    global _jwks_cache
    _jwks_cache = None


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthContext:
    """Validate Clerk JWT and extract tenant context.

    Raises 401 if token is invalid or missing org_id.
    """
    token = credentials.credentials

    try:
        jwks = await _get_jwks()
        # Decode header to find the right key
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        rsa_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = key
                break

        if rsa_key is None:
            # Key not found — maybe rotated. Refresh cache and retry once.
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

    # Extract org context — required for tenant isolation
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization context. User must belong to an organization.",
        )

    return AuthContext(
        user_id=payload.get("sub", ""),
        org_id=org_id,
        org_role=payload.get("org_role"),
        email=payload.get("email"),
    )


async def get_company_id(auth: AuthContext = Depends(get_auth_context)) -> str:
    """Convenience dependency that returns just the company_id (org_id) for RLS."""
    return auth.org_id
