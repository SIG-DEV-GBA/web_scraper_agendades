"""Centralized external ID generation for event adapters."""
import hashlib


def make_external_id(prefix: str, *parts: str, hash_len: int = 12) -> str:
    """Generate a deterministic external_id from a prefix and parts.

    Args:
        prefix: Adapter prefix (e.g., "cnt", "nferias").
                The underscore separator is added automatically.
        *parts: String parts to hash. Each is stripped and lowercased.
        hash_len: Length of the MD5 hex digest (default 12).

    Returns:
        String in format "{prefix}_{md5_hash[:hash_len]}"
    """
    raw = "_".join(str(p).strip().lower() for p in parts)
    return f"{prefix}_{hashlib.md5(raw.encode()).hexdigest()[:hash_len]}"
