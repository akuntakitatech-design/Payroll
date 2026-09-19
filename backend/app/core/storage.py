"""Emergent Object Storage client.

Files are NEVER stored on the app pod - they go to object storage, while the
metadata (source of truth) lives in MongoDB. Paths are namespaced per tenant:
    hris-payroll/companies/{company_id}/documents/{uuid}.{ext}
"""
import logging
import os
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "hris-payroll"

_storage_key: Optional[str] = None

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


def init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    if not EMERGENT_KEY:
        raise StorageError("EMERGENT_LLM_KEY belum diatur pada environment backend.")
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def object_path(company_id: str, file_id: str, ext: Optional[str]) -> str:
    suffix = f".{ext}" if ext else ""
    return f"{APP_NAME}/companies/{company_id}/documents/{file_id}{suffix}"


def guess_mime(ext: Optional[str], fallback: Optional[str] = None) -> str:
    if fallback:
        return fallback
    return MIME_TYPES.get((ext or "").lower(), "application/octet-stream")


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    url = f"{STORAGE_URL}/objects/{path}"
    headers = {"X-Storage-Key": key, "Content-Type": content_type}
    resp = requests.put(url, headers=headers, data=data, timeout=120)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(
            url, headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=120
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> Tuple[bytes, str]:
    key = init_storage()
    url = f"{STORAGE_URL}/objects/{path}"
    resp = requests.get(url, headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(url, headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
