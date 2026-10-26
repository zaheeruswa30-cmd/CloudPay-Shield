"""CloudPay Shield API entry point.

Run (from the backend folder, with the virtual environment active):
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import init_db
from routers import admin_routes, auth_routes, insight_routes, notification_routes, payroll_routes

logger = logging.getLogger("cloudpay")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup()
    yield


def startup() -> None:
    """Runs automatically when the API starts - no manual scripts needed.

    1. Create any missing tables (never drops or alters existing ones).
    2. If SEED_DEMO_DATA is on and the database has NO users, add fictional demo data.
       A database that already has users is left exactly as it is.
    """
    init_db()
    if settings.seed_demo_data:
        from seed import seed
        seed()


app = FastAPI(
    title="CloudPay Shield API",
    version="2.0.0",
    description="AI-assisted payroll security: explainable salary-change risk scoring, RBAC, MFA and hash-chained audit.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    # Return field-level messages without echoing submitted values (which may include passwords).
    errors = [
        {"field": ".".join(str(p) for p in err.get("loc", [])[1:]), "message": err.get("msg", "Invalid value")}
        for err in exc.errors()
    ]
    message = "; ".join(f"{e['field']}: {e['message']}" for e in errors) or "Invalid request."
    return JSONResponse(status_code=422, content={"detail": message, "errors": errors})


@app.exception_handler(Exception)
async def unhandled_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "cloudpay-shield", "version": app.version}


app.include_router(auth_routes.router)
app.include_router(payroll_routes.router)
app.include_router(insight_routes.router)
app.include_router(notification_routes.router)
app.include_router(admin_routes.router)
