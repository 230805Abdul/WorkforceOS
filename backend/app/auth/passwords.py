"""Password hashing (Argon2id) and the password policy.

Hashing: argon2-cffi's PasswordHasher = Argon2id with the RFC 9106 "low memory" profile (64 MiB, 3 passes, 4 lanes)
and a random salt per password. The resulting string contains the algorithm, parameters and salt, e.g.
    $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
so the parameters can be raised later: needs_rehash() tells us when a stored hash should be upgraded at next sign-in.

Policy (NIST SP 800-63B style: length over complexity rules):
  * 12 to 128 characters
  * not one of the most common passwords
  * must not contain your e-mail name or your full name
"""
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import PASSWORD_HASH_PROFILE

MIN_LENGTH = 12
MAX_LENGTH = 128

_hasher = (
    PasswordHasher()  # library defaults = recommended profile
    if PASSWORD_HASH_PROFILE == "standard"  # nosec B105 # hash-profile name, not a password
    else PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)  # tests only; refused in production by config.py
)

# Used when the e-mail is unknown, so a failed sign-in takes as long for unknown accounts as for known ones
# (otherwise response time would reveal which e-mails have accounts).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

COMMON_PASSWORDS = {
    "123456789012", "1234567890123", "password1234", "password12345", "passwordpassword", "qwertyuiopas",
    "qwerty123456", "123qweasdzxc", "1q2w3e4r5t6y", "iloveyou1234", "letmein12345", "welcome12345", "admin1234567",
    "administrator", "changeme1234", "abc123456789", "aaaaaaaaaaaa", "111111111111", "000000000000",
    "workforceos12", "workforceos123", "workforceos2026", "password@123", "p@ssw0rd1234", "qwertyqwerty",
    "monkeymonkey", "dragondragon", "football1234", "baseball1234", "sunshine1234", "princess1234", "superman1234",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Constant-effort check. A missing hash (invited user, no password yet) never matches."""
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def policy_problem(password: str, *, email: str = "", full_name: str = "") -> str | None:
    """Return a user-facing reason why the password is not acceptable, or None if it is fine."""
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters"
    if len(password) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters"
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or len(set(lowered)) <= 2:
        return "This password is too common. Choose something harder to guess"
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in lowered:
        return "Don't use your e-mail address in your password"
    for part in full_name.lower().split():
        if len(part) >= 4 and part in lowered:
            return "Don't use your name in your password"
    return None


POLICY_TEXT = (f"{MIN_LENGTH}–{MAX_LENGTH} characters. Not a common password, and not containing your name or e-mail. "
               "A few unrelated words make a strong, memorable password.")


def new_token() -> str:
    """A random, URL-safe secret (256 bits) for session cookies and reset links."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """Tokens are stored hashed. SHA-256 is right here (not Argon2): the token is already 256 random bits."""
    return hashlib.sha256(token.encode()).hexdigest()
