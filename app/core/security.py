"""Security utilities: cryptographic token generation, hashing, and safe comparisons."""
import hashlib
import secrets
from typing import Tuple


def generate_consumer_token(prefix: str = "tok_live_") -> str:
    """Generates a high-entropy cryptographically secure permanent consumer API token."""
    random_part = secrets.token_hex(24)  # 48 hex chars (192 bits of entropy)
    return f"{prefix}{random_part}"


def hash_token(token: str) -> str:
    """Computes SHA-256 hash of a token string for safe persistence and lookup."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def timing_safe_compare(val1: str, val2: str) -> bool:
    """Performs constant-time comparison to prevent timing attacks."""
    if not val1 or not val2:
        return False
    return secrets.compare_digest(val1.strip(), val2.strip())
