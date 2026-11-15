import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router
from app.core.config import settings
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.rate_limit import limiter

logging.basicConfig(level=logging.INFO if settings.is_production else logging.DEBUG)

app = FastAPI(
    title="WorkforceOS API",
    description="Cloud-native workforce & recruitment operations platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# --- Security & rate limiting ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# --- Observability: exposes /metrics for Prometheus scraping ---
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# --- Routes ---
app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Liveness/readiness probe target for load balancers and ECS/K8s."""
    return {"status": "ok"}
