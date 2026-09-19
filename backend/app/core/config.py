import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]  # /app/backend
load_dotenv(ROOT_DIR / ".env")


class Settings:
    MONGO_URL: str = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    DB_NAME: str = os.environ.get("DB_NAME", "hris_db")
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")

    JWT_SECRET: str = os.environ.get("JWT_SECRET", "change-me-in-production-hris-secret")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "14"))

    UPLOAD_DIR: Path = ROOT_DIR / "uploads"
    MAX_UPLOAD_MB: int = int(os.environ.get("MAX_UPLOAD_MB", "15"))

    LOGIN_MAX_ATTEMPTS: int = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "8"))
    LOGIN_LOCK_MINUTES: int = int(os.environ.get("LOGIN_LOCK_MINUTES", "10"))


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
