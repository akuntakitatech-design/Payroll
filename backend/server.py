import logging
import os

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.db import close_db, ensure_indexes, get_db, warm_pool
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
    recruitment,
    recruitment_pipeline,
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


@app.get("/", include_in_schema=False)
async def root_plain():
    """Root 200 untuk health check default platform (Coolify/Traefik)."""
    return {"service": "HRIS & Payroll SaaS API", "status": "ok", "docs": "/docs", "health": "/api/health"}


@api.get("/system/mode")
async def system_mode():
    """Info mode operasi + status koneksi eksternal (dipakai banner di UI)."""
    from app.core.storage import storage_configured

    return {
        "environment": os.environ.get("APP_ENV", "production"),
        "read_only": bool(settings.READ_ONLY),
        "database": "mariadb",
        "storage": "cloudflare-r2" if storage_configured() else "not-configured",
        "auto_seed": os.environ.get("AUTO_SEED", "true").lower() == "true",
        "message": (
            "Terhubung ke database & storage PRODUKSI dalam mode HANYA-BACA. "
            "Data yang tampil adalah data asli; semua perubahan dinonaktifkan."
        ) if settings.READ_ONLY else "Mode baca-tulis penuh.",
    }


@api.get("/health")
async def health():
    try:
        await get_db().command("ping")
        return {"status": "healthy", "database": "mariadb:connected", "read_only": bool(settings.READ_ONLY)}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "unavailable", "message": "Koneksi database belum tersedia. Hubungi administrator."},
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
api.include_router(recruitment.router)
api.include_router(recruitment_pipeline.router)
api.include_router(settings_mail.router)

app.include_router(api)


@app.middleware("http")
async def protect_production_preview(request: Request, call_next):
    """Blokir efek samping sebelum router, termasuk email dan perubahan sandi."""
    safe_auth = {
        "/api/auth/login", "/api/auth/refresh",
        "/api/auth/switch-company", "/api/auth/logout",
    }
    path = request.url.path.rstrip("/")
    if (
        settings.READ_ONLY
        and request.method not in {"GET", "HEAD", "OPTIONS"}
        and not (request.method == "POST" and path in safe_auth)
    ):
        return JSONResponse(status_code=423, content={
            "detail": "Mode HANYA-BACA aktif: perubahan data, unggah berkas, perubahan kata sandi, dan pengiriman email dinonaktifkan untuk melindungi produksi."
        })
    return await call_next(request)


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


async def _wait_for_database() -> None:
    """Tunggu MariaDB siap (container DB biasanya start lebih lambat dari backend)."""
    import asyncio
    from urllib.parse import urlsplit

    attempts = int(os.environ.get("DB_CONNECT_RETRIES", "30"))
    delay = float(os.environ.get("DB_CONNECT_RETRY_DELAY", "2"))
    parts = urlsplit(settings.DATABASE_URL)
    target = f"{parts.hostname}:{parts.port or 3306}{parts.path}"
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await get_db().command("ping")
            logger.info("Terhubung ke MariaDB %s", target)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "MariaDB %s belum siap (percobaan %s/%s): %s", target, attempt, attempts, str(exc)[:200]
            )
            await asyncio.sleep(delay)
    raise RuntimeError(
        f"Tidak dapat terhubung ke MariaDB {target} setelah {attempts} percobaan. "
        "Periksa DATABASE_URL / DB_HOST dan pastikan backend berada di network yang sama dengan database."
    ) from last_exc


@app.on_event("startup")
async def on_startup():
    await _wait_for_database()
    await ensure_indexes()
    logger.info("Skema MariaDB & indeks siap.")

    # Panaskan kolam koneksi. Penting saat database berada jauh: tanpa ini,
    # permintaan pertama harus membuka puluhan koneksi sekaligus (~1,5 detik
    # masing-masing) sehingga halaman terasa menggantung.
    try:
        await warm_pool()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Pemanasan kolam koneksi dilewati: %s", exc)
    try:
        from app.core.storage import check_storage

        check_storage()
        logger.info("Object storage (Cloudflare R2) siap.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Object storage belum siap: %s", exc)

    if settings.READ_ONLY:
        logger.warning(
            "=== MODE HANYA-BACA AKTIF === Database & R2 PRODUKSI terhubung. "
            "Seed data, penjadwal pengingat, dan semua operasi tulis dinonaktifkan."
        )
    elif os.environ.get("ENABLE_SCHEDULER", "true").lower() == "true":
        try:
            from app.core.scheduler import start_scheduler

            start_scheduler()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Penjadwal pengingat belum siap: %s", exc)

    if not settings.READ_ONLY and os.environ.get("AUTO_SEED", "true").lower() == "true":
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
