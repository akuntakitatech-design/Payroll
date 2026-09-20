import logging
import os

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.db import close_db, ensure_indexes, get_db
from app.routers import (
    approvals,
    audit_logs,
    auth,
    certifications,
    companies,
    contracts,
    dashboard,
    documents,
    employees,
    master,
    payroll,
    policies,
    reminders,
    settings_mail,
    users,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("hris")

app = FastAPI(
    title="HRIS & Payroll SaaS API",
    description="Fondasi multi-perusahaan untuk HRIS & Payroll (Fase 1).",
    version="1.0.0",
)

api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "HRIS & Payroll SaaS", "status": "ok", "version": "1.0.0"}


@api.get("/health")
async def health():
    try:
        await get_db().command("ping")
        return {"status": "healthy", "database": "mariadb:connected"}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": str(exc)},
        )


api.include_router(auth.router)
api.include_router(companies.router)
api.include_router(master.router)
api.include_router(users.router)
api.include_router(approvals.router)
api.include_router(documents.router)
api.include_router(employees.router)
api.include_router(contracts.router)
api.include_router(certifications.router)
api.include_router(reminders.router)
api.include_router(policies.router)
api.include_router(audit_logs.router)
api.include_router(dashboard.router)
api.include_router(payroll.router)
api.include_router(settings_mail.router)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")] if settings.CORS_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """Descriptive validation messages in Bahasa Indonesia."""
    problems = []
    for err in exc.errors():
        field = " -> ".join(str(p) for p in err.get("loc", []) if p not in ("body", "query"))
        problems.append(f"{field or 'data'}: {err.get('msg')}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Data yang dikirim belum lengkap atau tidak sesuai. " + "; ".join(problems[:4]),
            "errors": problems,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    logger.info("Skema MariaDB & indeks siap.")
    try:
        from app.core.storage import check_storage

        check_storage()
        logger.info("Object storage (Cloudflare R2) siap.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Object storage belum siap: %s", exc)

    try:
        from app.core.scheduler import start_scheduler

        start_scheduler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Penjadwal pengingat belum siap: %s", exc)

    if os.environ.get("AUTO_SEED", "true").lower() == "true":
        try:
            from app.seed import run_seed

            result = await run_seed()
            logger.info("Seed data siap: %s", result["companies"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Seed data gagal: %s", exc)


@app.on_event("shutdown")
async def on_shutdown():
    try:
        from app.core.scheduler import stop_scheduler

        stop_scheduler()
    except Exception:  # noqa: BLE001
        pass
    await close_db()
