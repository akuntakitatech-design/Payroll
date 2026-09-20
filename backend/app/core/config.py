import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]  # /app/backend
load_dotenv(ROOT_DIR / ".env")


def _build_database_url() -> str:
    """Resolve the MariaDB connection URL.

    Priority:
      1. DATABASE_URL  (mysql://user:pass@host:3306/dbname  or  mysql+asyncmy://...)
      2. DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME
         (also accepts the MARIADB_* names used by the official MariaDB image)
    """
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        if url.startswith("mysql://"):
            url = "mysql+asyncmy://" + url[len("mysql://"):]
        elif url.startswith("mariadb://"):
            url = "mysql+asyncmy://" + url[len("mariadb://"):]
        elif url.startswith("mysql+pymysql://"):
            url = "mysql+asyncmy://" + url[len("mysql+pymysql://"):]
    else:
        host = os.environ.get("DB_HOST") or os.environ.get("MARIADB_HOST") or "mariadb"
        port = os.environ.get("DB_PORT") or os.environ.get("MARIADB_PORT") or "3306"
        user = os.environ.get("DB_USER") or os.environ.get("MARIADB_USER") or "mariadb"
        password = os.environ.get("DB_PASSWORD") or os.environ.get("MARIADB_PASSWORD") or ""
        name = os.environ.get("DB_NAME") or os.environ.get("MARIADB_DATABASE") or "hris_payroll"
        url = f"mysql+asyncmy://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"
    if "charset=" not in url:
        url += ("&" if "?" in url else "?") + "charset=utf8mb4"
    return url


class Settings:
    DATABASE_URL: str = _build_database_url()
    DB_POOL_SIZE: int = int(os.environ.get("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.environ.get("DB_MAX_OVERFLOW", "20"))
    # Matikan bila database berada jauh (latensi tinggi) untuk menghemat
    # satu perjalanan jaringan pada setiap pengambilan koneksi.
    DB_POOL_PRE_PING: bool = (
        os.environ.get("DB_POOL_PRE_PING", "true") or ""
    ).strip().lower() in ("1", "true", "yes", "y", "ya")

    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")

    # ===== Mode hanya-baca (READ-ONLY) =====
    # Dipakai saat aplikasi ditunjuk ke DATABASE PRODUKSI dari lingkungan preview.
    # Semua operasi tulis (INSERT/UPDATE/DELETE) ke tabel bisnis diblokir,
    # dan upload/hapus objek di Cloudflare R2 juga diblokir.
    READ_ONLY: bool = (os.environ.get("READ_ONLY", "false") or "").strip().lower() in ("1", "true", "yes", "y", "ya")
    # Tabel yang tulisannya di-no-op (tidak error) agar alur login & audit tetap jalan.
    READ_ONLY_SILENT_TABLES: set = {"users", "audit_logs", "reminder_logs", "payslip_email_logs"}

    JWT_SECRET: str = os.environ.get("JWT_SECRET", "change-me-in-production-hris-secret")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "14"))

    UPLOAD_DIR: Path = Path(os.environ.get("UPLOAD_DIR") or (ROOT_DIR / "uploads"))
    MAX_UPLOAD_MB: int = int(os.environ.get("MAX_UPLOAD_MB", "15"))

    LOGIN_MAX_ATTEMPTS: int = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "8"))
    LOGIN_LOCK_MINUTES: int = int(os.environ.get("LOGIN_LOCK_MINUTES", "10"))

    # Cloudflare R2 (S3 compatible) object storage
    R2_ACCOUNT_ID: str = os.environ.get("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID: str = os.environ.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY: str = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME: str = os.environ.get("R2_BUCKET_NAME", "")
    R2_ENDPOINT_URL: str = os.environ.get("R2_ENDPOINT_URL", "")
    R2_REGION: str = os.environ.get("R2_REGION", "auto")
    R2_PREFIX: str = os.environ.get("R2_PREFIX", "hris-payroll")
    # URL publik bucket (r2.dev / custom domain), opsional - dipakai untuk tautan langsung ke berkas
    R2_PUBLIC_BASE_URL: str = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")


settings = Settings()
try:
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
