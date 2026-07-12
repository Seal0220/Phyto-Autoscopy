from __future__ import annotations

import os
import re
import secrets
from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from threading import Lock
from time import monotonic
from typing import Mapping


class SecurityError(Exception):
    status_code = 400


class AuthenticationError(SecurityError):
    status_code = 401


class AuthorizationError(SecurityError):
    status_code = 403


class RateLimitError(SecurityError):
    status_code = 429


class SecurityConfigurationError(SecurityError):
    status_code = 503


@dataclass(frozen=True)
class Principal:
    actor: str
    role: str
    permissions: frozenset[str]


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset({"status:read", "cameras:read", "sessions:read"}),
    "operator": frozenset({"*"}),
    "admin": frozenset({"*"}),
}
_ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9_.@:-]{1,96}$")


def _configured_bff_token() -> str:
    token = os.environ.get("PHYTO_AUTOSCOPY_BFF_TOKEN", "").strip()
    if not token:
        raise SecurityConfigurationError("後端服務驗證尚未完成設定。")
    return token


def authenticate_bff_headers(headers: Mapping[str, str]) -> Principal:
    """Authenticate only the trusted Next.js server, never a localhost client."""
    supplied_token = headers.get("x-phyto-bff-token", "")
    if not supplied_token or not compare_digest(supplied_token, _configured_bff_token()):
        raise AuthenticationError("後端服務驗證失敗。")

    actor = headers.get("x-phyto-actor", "").strip()
    if not _ACTOR_PATTERN.fullmatch(actor):
        raise AuthenticationError("使用者身分驗證失敗。")

    role = headers.get("x-phyto-role", "").strip().lower()
    permissions = ROLE_PERMISSIONS.get(role)
    if permissions is None:
        raise AuthorizationError("找不到使用者角色。")
    return Principal(actor=actor, role=role, permissions=permissions)


def ensure_permission(principal: Principal, permission: str) -> None:
    if "*" not in principal.permissions and permission not in principal.permissions:
        raise AuthorizationError("目前的使用者角色沒有執行此操作的權限。")


def permission_for_http(method: str, path: str) -> str:
    normalized_method = method.upper()
    if normalized_method in {"GET", "HEAD"}:
        if path.startswith("/api/settings"):
            return "settings:read"
        if path.startswith("/api/sessions"):
            return "sessions:read"
        if path.startswith("/api/cameras"):
            return "cameras:read"
        return "status:read"
    if path.startswith("/api/settings"):
        return "settings:write"
    if path.startswith("/api/motor") or path.startswith("/api/cameras"):
        return "hardware:operate"
    if path.startswith("/api/experiments") or path.startswith("/api/capture"):
        return "experiment:operate"
    if path.startswith("/api/sessions"):
        return "sessions:manage"
    return "status:read"


def permission_for_websocket_action(action: str) -> str:
    if action in {"system.snapshot", "sessions.list"}:
        return "status:read"
    if action == "settings.get":
        return "settings:read"
    if action.startswith("camera.") or action.startswith("motor."):
        return "hardware:operate"
    if action.startswith("experiment.") or action.startswith("capture."):
        return "experiment:operate"
    raise AuthorizationError("不支援的即時操作。")


@dataclass(frozen=True)
class _Ticket:
    principal: Principal
    expires_at: float


class WebSocketTicketStore:
    """One-use, short-lived tickets keep the backend credential out of browsers."""

    def __init__(self) -> None:
        self._tickets: dict[str, _Ticket] = {}
        self._lock = Lock()

    @staticmethod
    def _key(ticket: str) -> str:
        return sha256(ticket.encode("utf-8")).hexdigest()

    def _purge_expired(self, now: float) -> None:
        self._tickets = {
            key: value for key, value in self._tickets.items() if value.expires_at > now
        }

    def issue(self, principal: Principal, ttl_seconds: int = 45) -> tuple[str, int]:
        ticket = secrets.token_urlsafe(32)
        now = monotonic()
        with self._lock:
            self._purge_expired(now)
            self._tickets[self._key(ticket)] = _Ticket(
                principal=principal,
                expires_at=now + ttl_seconds,
            )
        return ticket, ttl_seconds

    def consume(self, ticket: str | None) -> Principal:
        if not ticket:
            raise AuthenticationError("缺少即時連線票證。")
        now = monotonic()
        with self._lock:
            self._purge_expired(now)
            issued = self._tickets.pop(self._key(ticket), None)
        if issued is None:
            raise AuthenticationError("即時連線票證無效或已過期。")
        return issued.principal


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int = 60) -> None:
        now = monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise RateLimitError("操作過於頻繁，請稍後再試。")
            bucket.append(now)


websocket_tickets = WebSocketTicketStore()
rate_limiter = SlidingWindowRateLimiter()


def rate_limit_http(principal: Principal, method: str, path: str) -> None:
    is_write = method.upper() not in {"GET", "HEAD", "OPTIONS"}
    scope = "write" if is_write else "read"
    rate_limiter.check(
        f"http:{principal.actor}:{scope}:{path}",
        limit=30 if is_write else 240,
    )


def rate_limit_websocket(principal: Principal, scope: str) -> None:
    limit = 60 if scope == "command" else 12
    rate_limiter.check(f"ws:{principal.actor}:{scope}", limit=limit)


def get_request_principal(request: object) -> Principal:
    state = getattr(request, "state", None)
    principal = getattr(state, "principal", None)
    if not isinstance(principal, Principal):
        raise AuthenticationError("無法取得已驗證的使用者身分。")
    return principal
