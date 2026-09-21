"""Verifikasi koneksi infrastruktur: MariaDB (produksi) + Cloudflare R2.

Jalankan: cd /app/backend && python verify_infra.py
"""
from __future__ import annotations

import asyncio
import sys
import traceback

from app.core.config import settings

results: list[tuple[str, bool, str]] = []


def rec(name: str, ok: bool, info: str = "") -> None:
    results.append((name, ok, info))
    print(("PASS  " if ok else "FAIL  ") + name + (f"  -> {info}" if info else ""))


async def check_mariadb() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    safe = settings.DATABASE_URL.split("@")[-1]
    print(f"\n--- MariaDB ({safe}) ---")
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=False)
    try:
        async with engine.connect() as conn:
            one = (await conn.execute(text("SELECT 1"))).scalar()
            rec("SELECT 1", one == 1, str(one))
            ver = (await conn.execute(text("SELECT VERSION()"))).scalar()
            rec("Versi server", bool(ver), str(ver))
            db = (await conn.execute(text("SELECT DATABASE()"))).scalar()
            rec("Database aktif", bool(db), str(db))
            rows = (await conn.execute(text("SHOW TABLES"))).fetchall()
            names = sorted(r[0] for r in rows)
            rec("Daftar tabel", True, f"{len(names)} tabel: {', '.join(names[:15])}{' ...' if len(names) > 15 else ''}")
            for tbl in ("users", "companies", "employees"):
                if tbl in names:
                    cnt = (await conn.execute(text(f"SELECT COUNT(*) FROM `{tbl}`"))).scalar()
                    rec(f"Jumlah baris {tbl}", True, str(cnt))
    except Exception as exc:  # noqa: BLE001
        rec("Koneksi MariaDB", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        await engine.dispose()


def check_r2() -> None:
    import boto3
    from botocore.config import Config

    print(f"\n--- Cloudflare R2 (bucket={settings.R2_BUCKET_NAME}) ---")
    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.R2_ENDPOINT_URL,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name=settings.R2_REGION or "auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        client.head_bucket(Bucket=settings.R2_BUCKET_NAME)
        rec("head_bucket", True, settings.R2_BUCKET_NAME)

        listing = client.list_objects_v2(
            Bucket=settings.R2_BUCKET_NAME, Prefix=settings.R2_PREFIX, MaxKeys=10
        )
        keys = [o["Key"] for o in listing.get("Contents", [])]
        rec("list_objects_v2", True, f"{listing.get('KeyCount', 0)} objek pada prefix '{settings.R2_PREFIX}' -> {keys[:5]}")

        key = f"{settings.R2_PREFIX}/_healthcheck/verify_infra.txt"
        client.put_object(Bucket=settings.R2_BUCKET_NAME, Key=key, Body=b"ok-from-emergent", ContentType="text/plain")
        rec("put_object", True, key)
        body = client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)["Body"].read()
        rec("get_object", body == b"ok-from-emergent", body.decode(errors="replace"))
        url = client.generate_presigned_url(
            "get_object", Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key}, ExpiresIn=300
        )
        rec("presigned_url", url.startswith("http"), url[:90] + "...")
        client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        rec("delete_object", True, key)
    except Exception as exc:  # noqa: BLE001
        rec("Koneksi R2", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()


async def main() -> int:
    await check_mariadb()
    check_r2()
    print("\n===== RINGKASAN =====")
    failed = [r for r in results if not r[1]]
    for name, ok, info in results:
        print(("PASS  " if ok else "FAIL  ") + name)
    print(f"\nTotal: {len(results)} pemeriksaan, {len(failed)} gagal")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
