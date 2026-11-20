"""User authentication and authorization against the Keycloak ``cadence`` realm.

Every ``/api/v1`` route requires a bearer access token issued by the realm: verified
against the realm's public signing keys (fetched from ``OIDC_JWKS_URL`` and cached),
with the configured issuer (the public URL the browser used), the audience
``OIDC_AUDIENCE`` and an unexpired lifetime. Roles come from ``realm_access.roles``
with the hierarchy ``viewer`` ⊂ ``trader`` ⊂ ``admin`` expanded here as well, so
editing the composites in Keycloak cannot widen access by accident.

Reads (GET / HEAD) need ``viewer``; other methods need ``trader``; the Admin area and
the shared-asset routes (universe, watchlist, recommendation runs) need ``admin``. ``/health`` and the cron-triggered
routes (guarded by :func:`~cadence.api.cron_auth.require_valid_cron_token`) are
exempt. The authenticated user is kept on ``request.state.user`` and exposed to
routes via :func:`current_user` (the hook for later per-user data).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.dependencies.models import Dependant

from cadence.api.cron_auth import require_valid_cron_token
from cadence.config import settings

logger = logging.getLogger(__name__)

VIEWER = "viewer"
TRADER = "trader"
ADMIN = "admin"

#: What each role includes (the realm's composite roles, mirrored server-side).
_IMPLIED: dict[str, frozenset[str]] = {
    VIEWER: frozenset({VIEWER}),
    TRADER: frozenset({TRADER, VIEWER}),
    ADMIN: frozenset({ADMIN, TRADER, VIEWER}),
}

#: Mount prefix of the resource routers; rules below use templates without it.
API_PREFIX = "/api/v1"
#: Routes that change the shared asset data (universe and watchlist): admin only.
#: An asset recommendation run adds its results to the universe or the watchlist.
SHARED_ASSET_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/assets"),
        ("DELETE", "/assets/{asset_id}"),
        ("POST", "/assets/universe-evaluation/refresh"),
        ("POST", "/recommendations"),
    }
)
ADMIN_PREFIX = "/admin"
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class AuthUser:
    """The signed-in user: Keycloak subject (the stable id), name and effective roles."""

    sub: str
    username: str
    roles: frozenset[str]

    def has(self, role: str) -> bool:
        return role in self.roles


def expand_roles(raw: Any) -> frozenset[str]:
    """The effective roles for the realm roles in a token (unknown roles ignored)."""
    if not isinstance(raw, list):
        return frozenset()
    effective: set[str] = set()
    for role in raw:
        effective |= _IMPLIED.get(role, frozenset())
    return frozenset(effective)


def oidc_issuer() -> str:
    """The expected token issuer: ``OIDC_ISSUER`` or derived from the public URL."""
    if settings.OIDC_ISSUER:
        return settings.OIDC_ISSUER
    return f"{settings.CADENCE_PUBLIC_URL.rstrip('/')}/auth/realms/cadence"


_jwks_client: jwt.PyJWKClient | None = None


def jwks_client() -> jwt.PyJWKClient:
    """The cached signing-key client for the realm (keys refetched on an unknown kid)."""
    global _jwks_client
    if _jwks_client is None or _jwks_client.uri != settings.OIDC_JWKS_URL:
        _jwks_client = jwt.PyJWKClient(settings.OIDC_JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks_client


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def decode_token(token: str) -> AuthUser:
    """Validate an access token and return its user; raise 401 when it is not valid."""
    try:
        key = jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.OIDC_AUDIENCE,
            issuer=oidc_issuer(),
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWKClientError as exc:
        logger.warning("auth: signing keys unavailable or unknown key: %s", exc)
        raise _unauthorized("Invalid token") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid token") from exc
    access = claims.get("realm_access")
    roles = expand_roles(access.get("roles") if isinstance(access, dict) else None)
    return AuthUser(
        sub=str(claims["sub"]),
        username=str(claims.get("preferred_username") or claims["sub"]),
        roles=roles,
    )


def _depends_on(dependant: Dependant, target: Any) -> bool:
    return any(dep.call is target or _depends_on(dep, target) for dep in dependant.dependencies)


def route_template(path: str) -> str:
    """A route's path template without the ``/api/v1`` mount prefix.

    Depending on the FastAPI version, the matched route's path carries the mount prefix
    or only the router's own prefix; both normalise to the same template.
    """
    return path[len(API_PREFIX) :] if path.startswith(API_PREFIX + "/") else path


def required_role(method: str, path: str) -> str:
    """The role a request needs (``path`` is the route's path template)."""
    path = route_template(path)
    if path == ADMIN_PREFIX or path.startswith(ADMIN_PREFIX + "/"):
        return ADMIN
    if (method, path) in SHARED_ASSET_ROUTES:
        return ADMIN
    return VIEWER if method in _READ_METHODS else TRADER


def is_exempt(request: Request) -> bool:
    """Health and cron-token routes keep their own protection."""
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    if path == "/health":
        return True
    dependant = getattr(route, "dependant", None)
    return dependant is not None and _depends_on(dependant, require_valid_cron_token)


def authorize(request: Request) -> None:
    """App-wide dependency: authenticate the caller and check the route's role."""
    if not settings.AUTH_ENABLED or is_exempt(request):
        return
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Not authenticated")
    user = decode_token(token)
    request.state.user = user
    route = request.scope.get("route")
    role = required_role(request.method, getattr(route, "path", request.url.path))
    # Belt and braces: anything under the Admin area needs admin, whatever the template.
    if request.url.path.startswith(f"{API_PREFIX}{ADMIN_PREFIX}/"):
        role = ADMIN
    if not user.has(role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission for this action",
        )


def get_current_user(request: Request) -> AuthUser | None:
    """The signed-in user, or ``None`` when auth is disabled or the route is exempt."""
    user = getattr(request.state, "user", None)
    return user if isinstance(user, AuthUser) else None


#: Route dependency exposing the signed-in user (the hook for per-user data later).
current_user = Annotated[AuthUser | None, Depends(get_current_user)]
