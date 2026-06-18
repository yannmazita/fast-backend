# src.common.dependencies
import hashlib

from fastapi import Request


def get_anonymous_fingerprint(request: Request) -> str:
    """Computes a weak anonymous deduplication hash."""
    raw = (
        f"{request.client.host if request.client else 'unknown'}"
        f"|{request.headers.get('user-agent', '')}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()
