"""Engine penomoran dokumen generik (Phase 2A CP1).

- Konfigurasi format per (company, sequence_key) di `document_sequence_configs` (configurable tenant).
- Counter per (company, sequence_key, period_key) di `document_sequence_counters`.
- Alokasi CONCURRENCY-SAFE dan ATOMIK dengan insert dokumen: `allocate_in_tx(tx, ...)` dipanggil DI DALAM transaksi
  pemanggil -> `SELECT ... FOR UPDATE` baris counter (dikunci sampai transaksi pemanggil commit/rollback), naikkan
  `next_value`, render nomor. Jika insert dokumen gagal, kenaikan counter ikut di-rollback (tidak ada gap).
  TIDAK memakai COUNT(*)+1.
- Counter tidak pernah mundur; nomor hasil render yang sudah terpakai (mis. bentrok dengan kode manual) dilewati.
- Unique index pada tabel dokumen tetap menjadi jaring pengaman terakhir.

Token format: {YYYY} {YY} {MM} {ROMAN_MM} {COMPANY} {CAT} {SEQ:n} (n = 3..9).
CP1 hanya memakai ASSET_CODE dengan default sederhana `AST-{SEQ:6}` (tidak bergantung kategori).
CP2 menambah seri BAST_HANDOVER / BAST_RETURN (reset tahunan); CP3 menambah BAST_EXISTING / ASSET_IMPORT dan
alokasi massal `allocate_many_in_tx` (satu kunci counter untuk ribuan nomor, tetap tanpa COUNT(*)+1).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import HTTPException, status

from .db import audit_fields, get_db, new_id, now

YEARLY, NEVER = "YEARLY", "NEVER"
SEQ_RE = re.compile(r"\{SEQ:(\d)\}")
TOKEN_RE = re.compile(r"\{[A-Z_]+(?::\d)?\}")
KNOWN_TOKENS = {"{YYYY}", "{YY}", "{MM}", "{ROMAN_MM}", "{COMPANY}", "{CAT}"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
MAX_SKIPS = 50

DEFAULTS: Dict[str, Dict[str, str]] = {
    "ASSET_CODE": {"label": "Kode Aset Otomatis", "format": "AST-{SEQ:6}", "reset_policy": NEVER},
    # Phase 2A CP2 - nomor sistem BAST (per company + tipe + tahun; reset tahunan; tidak pernah dipakai ulang).
    "BAST_HANDOVER": {"label": "Nomor BAST Penyerahan", "format": "BAST-AST/{YYYY}/{SEQ:6}", "reset_policy": YEARLY},
    "BAST_RETURN": {"label": "Nomor BAST Pengembalian", "format": "BAST-RTN/{YYYY}/{SEQ:6}", "reset_policy": YEARLY},
    # Phase 2A CP3 - dokumen Saldo Awal (Opening Existing Holding) + nomor batch impor aset.
    "BAST_EXISTING": {"label": "Nomor Dokumen Saldo Awal Aset", "format": "BAST-EXS/{YYYY}/{SEQ:6}", "reset_policy": YEARLY},
    "ASSET_IMPORT": {"label": "Nomor Batch Impor Aset", "format": "IMP-AST/{YYYY}/{SEQ:6}", "reset_policy": YEARLY},
}


def validate_format(fmt: str, reset_policy: str) -> None:
    fmt = (fmt or "").strip()
    if reset_policy not in (YEARLY, NEVER):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kebijakan reset tidak dikenal.")
    seqs = SEQ_RE.findall(fmt)
    if len(seqs) != 1 or not (3 <= int(seqs[0]) <= 9):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Format wajib memuat tepat satu {SEQ:n} (n = 3 sampai 9).")
    unknown = [t for t in TOKEN_RE.findall(fmt) if not t.startswith("{SEQ:") and t not in KNOWN_TOKENS]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Token tidak dikenal: {', '.join(unknown)}.")
    if reset_policy == YEARLY and "{YYYY}" not in fmt and "{YY}" not in fmt:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Reset tahunan wajib memuat {YYYY} atau {YY} agar nomor antar tahun tidak bentrok.")


def render(fmt: str, seq: int, when: date, company_code: str = "", cat: str = "") -> str:
    digits = int(SEQ_RE.search(fmt).group(1))
    out = (fmt.replace("{YYYY}", f"{when.year:04d}").replace("{YY}", f"{when.year % 100:02d}")
           .replace("{MM}", f"{when.month:02d}").replace("{ROMAN_MM}", ROMAN[when.month - 1])
           .replace("{COMPANY}", company_code or "").replace("{CAT}", cat or ""))
    return SEQ_RE.sub(str(seq).zfill(digits), out)


def period_key_for(cfg: Dict[str, Any], when: date, cat: str = "") -> str:
    period = str(when.year) if cfg.get("reset_policy") == YEARLY else "ALL"
    if "{CAT}" in (cfg.get("format") or ""):
        period = f"{period}:{cat or '-'}"
    return period


async def _insert_ignore_duplicate(collection: str, doc: Dict[str, Any]) -> None:
    try:
        await get_db()[collection].insert_one(dict(doc))
    except HTTPException as exc:  # 409 = baris sudah dibuat proses lain secara bersamaan
        if exc.status_code != status.HTTP_409_CONFLICT:
            raise


async def get_config(company_id: str, sequence_key: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
    """Konfigurasi aktif; dibuat dari DEFAULTS bila belum ada (idempoten, tidak menimpa konfigurasi tenant)."""
    db = get_db()
    flt = {"company_id": company_id, "sequence_key": sequence_key}
    row = await db.document_sequence_configs.find_one(flt, {"_id": 0})
    if row:
        return row
    d = DEFAULTS[sequence_key]
    await _insert_ignore_duplicate("document_sequence_configs", {
        "id": new_id(), "company_id": company_id, "status": "active", "sequence_key": sequence_key,
        "label": d["label"], "format": d["format"], "reset_policy": d["reset_policy"], "is_system": True,
        **audit_fields(actor_id, creating=True)})
    return await db.document_sequence_configs.find_one(flt, {"_id": 0})


async def prepare(company_id: str, sequence_key: str, *, when: Optional[date] = None, cat: str = "",
                  actor_id: Optional[str] = None) -> Dict[str, Any]:
    """Dipanggil SEBELUM transaksi: pastikan config + baris counter ada (insert idempoten, unique index menolak
    duplikat saat balapan). Mengembalikan konteks untuk `allocate_in_tx`."""
    cfg = await get_config(company_id, sequence_key, actor_id)
    when = when or date.today()
    period = period_key_for(cfg, when, cat)
    flt = {"company_id": company_id, "sequence_key": sequence_key, "period_key": period}
    if not await get_db().document_sequence_counters.count_documents(flt):
        await _insert_ignore_duplicate("document_sequence_counters", {
            "id": new_id(), "status": "active", "next_value": 1, **flt, **audit_fields(actor_id, creating=True)})
    return {"cfg": cfg, "when": when, "cat": cat, "flt": flt}


async def allocate_in_tx(tx, prepared: Dict[str, Any], *, company_code: str = "",
                         exists: Optional[Callable[[str], Awaitable[bool]]] = None) -> str:
    """Alokasi nomor DI DALAM transaksi pemanggil. Baris counter terkunci (FOR UPDATE) sampai transaksi selesai,
    sehingga dua alokasi paralel untuk counter yang sama selalu berurutan dan tidak pernah menghasilkan nomor sama.
    `exists(candidate)` -> True bila nomor sudah dipakai (dilewati, counter tetap maju)."""
    flt = prepared["flt"]
    row = await tx.select_one_for_update("document_sequence_counters", flt)
    if not row:
        raise HTTPException(status.HTTP_409_CONFLICT, "Counter penomoran belum siap. Silakan ulangi.")
    value = int(row.get("next_value") or 1)
    fmt = prepared["cfg"]["format"]
    for _ in range(MAX_SKIPS):
        candidate = render(fmt, value, prepared["when"], company_code, prepared["cat"])
        value += 1
        if not exists or not await exists(candidate):
            await tx.update("document_sequence_counters", {"id": row["id"], "company_id": flt["company_id"]},
                            {"next_value": value, "updated_at": now()})
            return candidate
    raise HTTPException(status.HTTP_409_CONFLICT, "Gagal membuat nomor otomatis yang unik. Periksa format penomoran.")


async def allocate_many_in_tx(tx, prepared: Dict[str, Any], count: int, *,
                              taken: Optional[Callable[[list], Awaitable[set]]] = None) -> list:
    """Alokasi `count` nomor berurutan DI DALAM transaksi pemanggil dengan SATU kunci baris counter (FOR UPDATE).
    `taken(candidates)` -> himpunan nomor yang sudah terpakai (dilewati; counter tetap maju). Rollback transaksi
    pemanggil ikut membatalkan kenaikan counter (tidak ada gap/nomor ganda)."""
    if count <= 0:
        return []
    flt = prepared["flt"]
    row = await tx.select_one_for_update("document_sequence_counters", flt)
    if not row:
        raise HTTPException(status.HTTP_409_CONFLICT, "Counter penomoran belum siap. Silakan ulangi.")
    value = int(row.get("next_value") or 1)
    fmt = prepared["cfg"]["format"]
    out: list = []
    skips = 0
    while len(out) < count:
        need = count - len(out)
        cands = [render(fmt, value + i, prepared["when"], "", prepared["cat"]) for i in range(need)]
        value += need
        used = await taken(cands) if taken else set()
        if used:
            skips += len(used)
            if skips > max(MAX_SKIPS, count):
                raise HTTPException(status.HTTP_409_CONFLICT, "Gagal membuat nomor otomatis yang unik. Periksa format penomoran.")
        out.extend(c for c in cands if c not in used)
    await tx.update("document_sequence_counters", {"id": row["id"], "company_id": flt["company_id"]},
                    {"next_value": value, "updated_at": now()})
    return out
