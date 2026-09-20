"""Cloudflare R2 object storage client (S3 compatible, via boto3).

Files are NEVER stored on the app container - they go to object storage, while
the metadata (source of truth) lives in MariaDB. Paths are namespaced per tenant:
    {R2_PREFIX}/companies/{company_id}/documents/{uuid}.{ext}

Required environment variables (set them in Coolify -> Backend -> Environment):
    R2_ACCOUNT_ID         Cloudflare account id
    R2_ACCESS_KEY_ID      R2 API token access key
    R2_SECRET_ACCESS_KEY  R2 API token secret
    R2_BUCKET_NAME        bucket name
    R2_ENDPOINT_URL       optional, default https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com
    R2_PUBLIC_BASE_URL    optional, e.g. https://pub-xxxx.r2.dev (public bucket URL)
"""
import logging
from typing import Optional, Tuple

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings

logger = logging.getLogger(__name__)

APP_NAME = settings.R2_PREFIX or "hris-payroll"

_client = None

MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
    "webp": "image/webp", "pdf": "application/pdf", "csv": "text/csv", "txt": "text/plain",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class StorageError(RuntimeError):
    pass


def storage_configured() -> bool:
    return bool(settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_BUCKET_NAME
                and (settings.R2_ENDPOINT_URL or settings.R2_ACCOUNT_ID))


def _endpoint() -> str:
    if settings.R2_ENDPOINT_URL:
        return settings.R2_ENDPOINT_URL.rstrip("/")
    return f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"


def init_storage(force: bool = False):
    """Create (and cache) the S3 client. Raises StorageError if env is incomplete."""
    global _client
    if _client is not None and not force:
        return _client
    if not storage_configured():
        missing = [
            name for name in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
            if not getattr(settings, name)
        ]
        if not (settings.R2_ENDPOINT_URL or settings.R2_ACCOUNT_ID):
            missing.append("R2_ACCOUNT_ID")
        raise StorageError("Konfigurasi R2 belum lengkap: " + ", ".join(missing))
    _client = boto3.client(
        "s3",
        endpoint_url=_endpoint(),
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name=settings.R2_REGION or "auto",
        config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )
    return _client


def check_storage() -> bool:
    """Light connectivity check used at startup (HEAD bucket)."""
    client = init_storage()
    try:
        client.head_bucket(Bucket=settings.R2_BUCKET_NAME)
        return True
    except (ClientError, BotoCoreError) as exc:
        raise StorageError(f"Bucket R2 '{settings.R2_BUCKET_NAME}' tidak dapat diakses: {exc}") from exc


def object_path(company_id: str, file_id: str, ext: Optional[str]) -> str:
    suffix = f".{ext}" if ext else ""
    return f"{APP_NAME}/companies/{company_id}/documents/{file_id}{suffix}"


def guess_mime(ext: Optional[str], fallback: Optional[str] = None) -> str:
    if fallback:
        return fallback
    return MIME_TYPES.get((ext or "").lower(), "application/octet-stream")


def put_object(path: str, data: bytes, content_type: str) -> dict:
    client = init_storage()
    try:
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME, Key=path, Body=data, ContentType=content_type
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("Gagal upload ke R2 (%s): %s", path, exc)
        raise StorageError(f"Gagal menyimpan berkas ke object storage: {exc}") from exc
    return {"path": path, "size": len(data), "content_type": content_type, "bucket": settings.R2_BUCKET_NAME}


def get_object(path: str) -> Tuple[bytes, str]:
    client = init_storage()
    try:
        resp = client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=path)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            raise StorageError("Berkas tidak ditemukan di object storage.") from exc
        raise StorageError(f"Gagal mengambil berkas dari object storage: {exc}") from exc
    except BotoCoreError as exc:
        raise StorageError(f"Gagal mengambil berkas dari object storage: {exc}") from exc
    body = resp["Body"].read()
    return body, resp.get("ContentType") or "application/octet-stream"


def delete_object(path: str) -> None:
    client = init_storage()
    try:
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=path)
    except (ClientError, BotoCoreError) as exc:
        logger.warning("Gagal menghapus objek R2 (%s): %s", path, exc)


def presigned_url(path: str, expires: int = 900) -> str:
    client = init_storage()
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": settings.R2_BUCKET_NAME, "Key": path}, ExpiresIn=expires
    )


def public_url(path: str) -> Optional[str]:
    """Direct URL if the bucket is exposed publicly (R2_PUBLIC_BASE_URL), else None."""
    if not settings.R2_PUBLIC_BASE_URL:
        return None
    return f"{settings.R2_PUBLIC_BASE_URL}/{path.lstrip('/')}"
