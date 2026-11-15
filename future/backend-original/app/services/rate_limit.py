from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Keyed by client IP; swap get_remote_address for a user-id key func once auth
# is resolved earlier in the chain, if you want per-user rather than per-IP limits.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)
