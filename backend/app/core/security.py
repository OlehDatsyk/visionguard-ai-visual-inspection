"""Password hashing, access tokens and a small in-process rate limiter."""
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, status

from app.core.config import get_settings

_hasher = PasswordHasher()
# Verified when the e-mail is unknown, so response timing does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("visionguard-timing-equaliser")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: str, token_version: int) -> tuple[str, int]:
    settings = get_settings()
    ttl = settings.access_token_ttl_minutes * 60
    now = datetime.now(UTC)
    payload = {"sub": user_id, "ver": token_version, "iat": now, "exp": now + timedelta(seconds=ttl)}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), ttl


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, get_settings().secret_key, algorithms=[ALGORITHM], options={"require": ["sub", "exp", "ver"]}
        )
    except jwt.PyJWTError:
        return None


class RateLimiter:
    """Sliding-window limiter. State is per process, which suits the single-instance deployment."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = 60.0) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(window - (now - hits[0])) + 1
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many requests. Please wait and try again.",
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Behind a hosting proxy the first entry is the client. A client can spoof it, so this limit is only
    # a coarse control; login attempts are also limited per e-mail address in the login route.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and get_settings().environment == "production":
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
