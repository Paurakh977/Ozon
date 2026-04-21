"""
agent_auth.py — JWT verification + rate limiting for FastAPI agent

Flow:
  1. On WS connect, client sends {"type":"auth","token":"<jwt>"} or {"type":"auth"} (anon)
  2. We verify JWT against JWKS fetched from NestJS (cached, only re-fetched on kid mismatch)
  3. We apply rate limits: anon=3/min by IP, authenticated=60/min by user_id
  4. Returns (user_id | None, tier)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, cast

import httpx
from jose import jwt, jwk, JWTError
import redis.asyncio as aioredis

logger = logging.getLogger("agent_auth")

# ── Config (override via env vars in main.py before importing) ────────────────
JWKS_URL:      str   = ""   # e.g. "https://api.yourdomain.com/api/auth/jwks"
JWKS_FALLBACK_URLS: list[str] = []
JWKS_VERIFY_SSL: bool = True
JWT_ISSUER:    str   = ""   # must match issuer in auth.ts JWT config
JWT_AUDIENCE:  str   = ""   # must match audience in auth.ts JWT config
REDIS_URL:     str   = "redis://localhost:6379"

# Rate limit buckets
ANON_LIMIT:    int = 3    # prompts per window
AUTH_LIMIT:    int = 60
WINDOW_SECS:   int = 60

# WS auth handshake timeout (seconds)
AUTH_TIMEOUT:  float = 8.0

# Periodic JWKS refresh to pick up key removals/rotations proactively.
JWKS_CACHE_TTL_SECS: int = 300

# ── JWKS cache ────────────────────────────────────────────────────────────────
@dataclass
class JwksCache:
    keys:        dict        = field(default_factory=dict)  # kid → key object
    fetched_at:  float       = 0.0
    _lock:       asyncio.Lock = field(default_factory=asyncio.Lock)

_jwks_cache = JwksCache()


def _coerce_exp(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

async def _fetch_jwks() -> dict:
    """Fetch JWKS from NestJS and return kid→public_key mapping."""
    urls: list[str] = []
    if JWKS_URL:
        urls.append(JWKS_URL)
    for fallback in JWKS_FALLBACK_URLS:
        if fallback and fallback not in urls:
            urls.append(fallback)

    if not urls:
        raise RuntimeError("No JWKS URL configured")

    last_error: Optional[Exception] = None
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=5.0, verify=JWKS_VERIFY_SSL) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            keys = {}
            for k in data.get("keys", []):
                kid = k.get("kid")
                if kid:
                    keys[kid] = k   # raw JWK dict — jose can use it directly

            if keys:
                logger.info("JWKS fetched: %d key(s) from %s", len(keys), url)
                return keys

            logger.warning("JWKS endpoint %s returned no keys", url)
        except Exception as e:
            last_error = e
            logger.warning("JWKS fetch failed from %s: %s", url, e)

    raise RuntimeError(f"Failed to fetch JWKS from all configured URLs: {last_error}")

async def get_jwks(force_refresh: bool = False) -> dict:
    """Return cached JWKS, fetching only when needed."""
    async with _jwks_cache._lock:
        now = time.monotonic()
        is_stale = (
            bool(_jwks_cache.keys)
            and _jwks_cache.fetched_at > 0
            and (now - _jwks_cache.fetched_at) >= float(JWKS_CACHE_TTL_SECS)
        )

        if force_refresh or not _jwks_cache.keys or is_stale:
            try:
                _jwks_cache.keys = await _fetch_jwks()
                _jwks_cache.fetched_at = now
            except Exception:
                if _jwks_cache.keys:
                    logger.warning("JWKS refresh failed; using cached keys")
                else:
                    raise
    return _jwks_cache.keys

async def verify_jwt(token: str) -> Optional[dict]:
    """
    Verify a JWT using the JWKS from NestJS.
    Returns the payload dict on success, None on any failure.
    Auto-refreshes JWKS on kid mismatch (key rotation).
    """
    try:
        # Peek at the header to get kid without full verification
        from jose import jws
        header = jws.get_unverified_header(token)
        kid = header.get("kid")

        keys = await get_jwks()

        # If kid not in cache → maybe key was rotated, force refresh once
        if kid and kid not in keys:
            logger.info("kid %s not in cache — refreshing JWKS", kid)
            keys = await get_jwks(force_refresh=True)

        if not keys:
            logger.warning("JWKS is empty after refresh")
            return None

        # Try to verify with the matching key, fall back to all keys
        key_to_try = keys.get(kid) if kid else None
        candidates = [key_to_try] if key_to_try else list(keys.values())

        for raw_key in candidates:
            try:
                public_key = jwk.construct(raw_key)
                payload = jwt.decode(
                    token,
                    public_key,
                    algorithms=["ES256"],
                    issuer=JWT_ISSUER,
                    audience=JWT_AUDIENCE,
                    options={"verify_exp": True},
                )
                return payload
            except JWTError:
                continue

        logger.warning("JWT verification failed for all candidate keys")
        return None

    except Exception as e:
        logger.warning("JWT verification error: %s", e)
        return None


# ── Redis rate limiter ────────────────────────────────────────────────────────
_redis: Optional[aioredis.Redis] = None
_local_rl_lock = asyncio.Lock()
_local_rl: dict[str, list[float]] = {}

async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis

async def check_rate_limit(bucket_key: str, limit: int, window: int) -> tuple[bool, int]:
    """
    Sliding-window rate limiter using Redis sorted sets.
    Returns (allowed: bool, current_count: int).
    Atomic: uses a Lua script to prevent race conditions.
    """
    redis_client = cast(Any, await get_redis())

    lua_script = """
    local bucket = KEYS[1]
    local seqkey = KEYS[2]
    local now_ms = tonumber(ARGV[1])
    local window_ms = tonumber(ARGV[2])
    local cutoff = now_ms - window_ms

    redis.call('ZREMRANGEBYSCORE', bucket, '-inf', cutoff)

    local seq = redis.call('INCR', seqkey)
    local member = tostring(now_ms) .. '-' .. tostring(seq)
    redis.call('ZADD', bucket, now_ms, member)

    local current = redis.call('ZCARD', bucket)
    redis.call('PEXPIRE', bucket, window_ms)
    redis.call('PEXPIRE', seqkey, window_ms)

    return current
    """
    try:
        now_ms = int(time.time() * 1000)
        window_ms = int(window * 1000)
        count = await redis_client.eval(
            lua_script,
            2,
            bucket_key,
            f"{bucket_key}:seq",
            now_ms,
            window_ms,
        )
        count = int(count)
        return count <= limit, count
    except Exception as e:
        logger.error("Redis rate limit error: %s — using local fallback limiter", e)

    # Local in-process fallback limiter when Redis is unavailable.
    # This is not cross-instance, but it still prevents complete fail-open bypass.
    now = time.monotonic()
    async with _local_rl_lock:
        samples = _local_rl.get(bucket_key, [])
        cutoff = now - float(window)
        samples = [ts for ts in samples if ts > cutoff]
        samples.append(now)
        _local_rl[bucket_key] = samples
        current = len(samples)
        return current <= limit, current


# ── Auth handshake ────────────────────────────────────────────────────────────
@dataclass
class AuthResult:
    user_id:    Optional[str]
    email:      Optional[str]
    tier:       str              # "authenticated" | "anonymous"
    allowed:    bool
    reject_msg: Optional[str]   # set when allowed=False
    token_exp:  Optional[int] = None  # UNIX epoch seconds from JWT exp claim


async def perform_auth_handshake(
    websocket,
    client_ip: str,
) -> AuthResult:
    """
    Wait for the auth frame from the client, validate JWT if present,
    apply rate limiting, and return an AuthResult.

    Protocol (client sends this as the FIRST message after WS connect):
        {"type": "auth", "token": "<jwt>"}   ← authenticated user
        {"type": "auth"}                      ← anonymous user
    """
    import json

    user_id = None
    email   = None
    tier    = "anonymous"
    token_exp: Optional[int] = None

    # ── 1. Receive auth frame (with timeout) ─────────────────────────
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT)
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.warning("Non-object auth frame from %s, treating as anonymous", client_ip)
            data = {"type": "auth"}
    except asyncio.TimeoutError:
        logger.warning("Auth handshake timeout from %s", client_ip)
        data = {"type": "auth"}  # treat as anonymous
    except Exception as e:
        logger.warning("Auth frame parse error from %s: %s", client_ip, e)
        data = {"type": "auth"}

    if data.get("type") != "auth":
        # Client sent a non-auth frame first — treat as anonymous
        # (you could reject here instead if you want strict protocol)
        logger.warning("Non-auth first frame from %s, treating as anonymous", client_ip)

    token = data.get("token")

    # ── 2. Verify JWT if provided ─────────────────────────────────────
    if token:
        payload = await verify_jwt(token)
        if payload:
            user_id = payload.get("sub")
            email   = payload.get("email")
            tier    = "authenticated"
            token_exp = _coerce_exp(payload.get("exp"))
            logger.info("Authenticated user %s (%s) from %s", user_id, email, client_ip)
        else:
            logger.warning("Invalid JWT from %s — downgrading to anonymous", client_ip)
            # Invalid token → treat as anonymous (don't reject outright)
            # This handles expired tokens gracefully

    # ── 3. Handshake result only (no prompt quota consumed here) ────────────
    # Prompt rate limits are enforced in websocket message handling for each
    # user message, which avoids accidental lockouts from reconnect storms.
    return AuthResult(user_id, email, tier, allowed=True, reject_msg=None, token_exp=token_exp)
