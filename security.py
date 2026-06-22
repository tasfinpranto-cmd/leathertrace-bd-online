from __future__ import annotations

import hashlib
import hmac
import os
import re

ITERATIONS = 210_000


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    validate_password(password)
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    checks = [r"[A-Z]", r"[a-z]", r"[0-9]", r"[^A-Za-z0-9]"]
    if not all(re.search(pattern, password) for pattern in checks):
        raise ValueError("Password must include upper-case, lower-case, number and symbol")
