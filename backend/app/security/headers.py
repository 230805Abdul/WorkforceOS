"""HTTP security headers for API responses.

The API only ever returns JSON, so its Content-Security-Policy can forbid everything: even if an attacker managed to
get HTML into a response, the browser would refuse to run scripts, load resources or frame it.
The FRONTEND's policy (which must allow our own scripts and styles) lives in frontend/security-headers.js.
"""
from app.config import HSTS_MAX_AGE

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

# Swagger UI (/docs, development only) loads its JavaScript/CSS from a CDN and uses an inline script.
DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")

PERMISSIONS_POLICY = ("accelerometer=(), browsing-topics=(), camera=(), display-capture=(), geolocation=(), gyroscope=(), "
                      "magnetometer=(), microphone=(), payment=(), usb=()")

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def security_headers(path: str) -> list[tuple[bytes, bytes]]:
    headers = {
        "content-security-policy": DOCS_CSP if path.startswith(DOCS_PATHS) else API_CSP,
        "x-content-type-options": "nosniff",            # never guess a different content type (MIME sniffing)
        "x-frame-options": "DENY",                       # old browsers' version of frame-ancestors 'none'
        "referrer-policy": "no-referrer",                # don't leak our URLs to other sites
        "permissions-policy": PERMISSIONS_POLICY,        # no camera, microphone, location... for anyone
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",   # other sites can't embed/load our responses
    }
    if path.startswith("/api/"):
        headers["cache-control"] = "no-store"            # personal data must not sit in browser/proxy caches
    if HSTS_MAX_AGE > 0:
        headers["strict-transport-security"] = f"max-age={HSTS_MAX_AGE}; includeSubDomains"
    return [(k.encode(), v.encode()) for k, v in headers.items()]
