"""API key generation. Only key_hash is ever persisted -- the raw key is
returned to the caller exactly once, at creation, and can never be
recovered afterward (matches the standard Stripe/GitHub-style PAT pattern)."""

import secrets

from app.services.hashing import sha256_hex

KEY_PREFIX_LENGTH = 12


def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, key_prefix, key_hash)."""
    raw_key = f"hb_live_{secrets.token_urlsafe(24)}"
    key_prefix = raw_key[:KEY_PREFIX_LENGTH]
    key_hash = sha256_hex(raw_key.encode())
    return raw_key, key_prefix, key_hash
