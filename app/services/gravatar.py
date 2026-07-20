"""Gravatar avatar URLs from participant email addresses."""

import hashlib


def gravatar_url(email: str, size: int = 80, default: str = "identicon") -> str:
    """Return a Gravatar image URL; falls back to a generated identicon if none exists."""
    if not email or not email.strip():
        return f"https://www.gravatar.com/avatar/?d={default}&s={size}&r=g"
    digest = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={size}&d={default}&r=g"
