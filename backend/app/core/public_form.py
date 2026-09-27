"""Upgrade 01G-A - Public Employee Form: inti keamanan & aturan field (tanpa HTTP).

Prinsip:
- Token link & token sesi = acak 256-bit (`secrets.token_urlsafe(32)`); DB hanya menyimpan SHA-256.
  Token mentah tidak pernah disimpan, di-log, atau dimasukkan ke audit (hanya `token_hint` 4 karakter).
- Verifikasi identitas hanya membandingkan dengan karyawan milik link (tidak ada lookup global).
- Rate limit disimpan di database (konsisten lintas proses): per-link (`employee_public_links`)
  + per-IP (`public_rate_limits`, kunci = hash IP). Lockout selalu sementara.
- Whitelist field: hanya field employee-editable yang diterima; field HR-only ditolak.
- Draft/submission TIDAK pernah menulis master karyawan (apply = scope 01H).
"""
import hashlib
import hmac
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa

from . import field_validators as V
from .db import get_engine, get_table, new_id, now

# ------------------------------------------------------------------ konstanta
LINK_DEFAULT_DAYS, LINK_MIN_DAYS, LINK_MAX_DAYS = 7, 1, 30
SESSION_ABSOLUTE = timedelta(hours=2)
SESSION_IDLE = timedelta(minutes=30)
SESSION_TOUCH_EVERY = timedelta(seconds=60)
LINK_MAX_FAILS, LINK_LOCK = 5, timedelta(minutes=15)
IP_MAX_FAILS, IP_WINDOW, IP_LOCK = 20, timedelta(minutes=15), timedelta(minutes=15)

ACTIVE, EXPIRED, REVOKED, SUBMITTED = "ACTIVE", "EXPIRED", "REVOKED", "SUBMITTED"
DRAFT, PENDING = "DRAFT", "PENDING_HR_VERIFICATION"
# Upgrade 01H - keputusan HR. REVISION_REQUESTED = tetap terbuka (baris sama, dapat diedit karyawan);
# APPROVED / REJECTED = final (open_slot dilepas -> karyawan dapat membuat pengajuan baru).
REVISION, APPROVED, REJECTED = "REVISION_REQUESTED", "APPROVED", "REJECTED"
OPEN_SUBMISSION_STATUSES = (DRAFT, PENDING, REVISION)
EDITABLE_SUBMISSION_STATUSES = (DRAFT, REVISION)
FINAL_SUBMISSION_STATUSES = (APPROVED, REJECTED)
SOURCE = "PUBLIC_EMPLOYEE_FORM"
MODE_IDENTITY = "IDENTITY_3F"   # jalur OPSIONAL/EXCEPTION: undangan (link unik) dari HR + verifikasi 3 faktor
MODE_PORTAL = "PORTAL_3F"       # jalur UTAMA: portal publik per tenant (kode perusahaan) + verifikasi 3 faktor
# Portal: kunci sementara per target (tenant + Nomor Karyawan yang dicoba) - berlaku sama untuk nomor yang ada/tidak ada.
TARGET_MAX_FAILS, TARGET_WINDOW, TARGET_LOCK = 5, timedelta(minutes=15), timedelta(minutes=15)
COMPANY_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{2,20}$")  # = pola kode tenant existing (platform.py), immutable

MSG_VERIFY_FAILED = "Data verifikasi belum sesuai. Silakan periksa kembali data yang Anda masukkan."
MSG_LINK_INVALID = "Link tidak valid atau sudah tidak berlaku. Silakan hubungi HR perusahaan Anda."
MSG_PORTAL_INVALID = "Portal pembaruan data tidak tersedia. Silakan hubungi HR perusahaan Anda."
MSG_TOO_MANY = "Terlalu banyak percobaan. Silakan coba lagi nanti."
MSG_SESSION_INVALID = "Sesi formulir telah berakhir. Silakan buka kembali link dan verifikasi ulang."
MSG_SUBMITTED = "Data Anda telah dikirim dan sedang menunggu verifikasi HR."

PUBLIC_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp"}
PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
PUBLIC_MAX_MB = 10
MAX_FILES_PER_SUBMISSION, MAX_FILES_PER_TYPE = 20, 3
MAX_FAMILY_OPS = 20
PHOTO_CODE = "PHOTO"


# ------------------------------------------------------------------ waktu
def utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ token
def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str, kind: str = "link") -> str:
    return hashlib.sha256(f"kk-pef:{kind}:{token}".encode()).hexdigest()


def token_hint(token: str) -> str:
    return token[-4:]


def ip_key(ip: Optional[str]) -> str:
    return hashlib.sha256(f"kk-pef:ip:{ip or 'unknown'}".encode()).hexdigest()


def target_key(company_id: str, employee_number: Any) -> str:
    """Kunci rate-limit portal: tenant + Nomor Karyawan ternormalisasi (hash; nilai mentah tidak disimpan)."""
    return hashlib.sha256(f"kk-pef:target:{company_id}:{norm_employee_number(employee_number)}".encode()).hexdigest()


def norm_company_code(code: Any) -> Optional[str]:
    s = str(code or "").strip()
    return s.upper() if COMPANY_CODE_RE.fullmatch(s) else None


def portal_path(company_code: str) -> str:
    """Path halaman portal (frontend 01G-B) - kode tenant publik & immutable, bukan ID internal."""
    return f"/public/{company_code}/update-data"


def link_effective_status(link: Dict[str, Any], at: Optional[datetime] = None) -> str:
    st = link.get("status")
    if st == ACTIVE and utc(link.get("expires_at")) and utc(link["expires_at"]) <= (at or now()):
        return EXPIRED
    return st


# ------------------------------------------------------------------ normalisasi verifikasi
def norm_employee_number(v: Any) -> str:
    return re.sub(r"\s+", "", str(v or "")).casefold()


def norm_digits(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def norm_date(v: Any) -> str:
    s = str(v or "").strip()
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    try:
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return ""


def verification_gaps(emp: Dict[str, Any]) -> List[str]:
    """Data master yang dibutuhkan agar karyawan dapat memakai verifikasi 3 faktor (untuk HR)."""
    gaps = []
    if not norm_employee_number(emp.get("employee_number")):
        gaps.append("Nomor Karyawan")
    if not re.fullmatch(r"\d{16}", norm_digits(emp.get("nik"))):
        gaps.append("NIK KTP (16 digit)")
    if not norm_date(emp.get("birth_date")) or not V.date_ok(emp.get("birth_date")):
        gaps.append("Tanggal Lahir")
    return gaps


def identity_matches(emp: Dict[str, Any], employee_number: Any, nik: Any, birth_date: Any) -> bool:
    """Bandingkan ketiga faktor tanpa short-circuit (constant-time per faktor)."""
    pairs = [
        (norm_employee_number(emp.get("employee_number")), norm_employee_number(employee_number)),
        (norm_digits(emp.get("nik")), norm_digits(nik)),
        (norm_date(emp.get("birth_date")), norm_date(birth_date)),
    ]
    ok = True
    for expected, given in pairs:
        ok = hmac.compare_digest(expected.encode(), given.encode()) and bool(expected) and ok
    return ok


# ------------------------------------------------------------------ rate limit (DB, atomik)
async def rate_locked(key: str) -> bool:
    t = get_table("public_rate_limits")
    async with get_engine().connect() as conn:
        row = (await conn.execute(sa.select(t.c.locked_until).where(t.c.key_hash == key))).first()
    return bool(row and row[0] and utc(row[0]) > now())


async def record_failure(key: str, scope: str, max_fails: int, window: timedelta, lock: timedelta) -> Tuple[int, bool]:
    """Counter gagal atomik (upsert) di `public_rate_limits`; kunci sementara saat mencapai batas.
    -> (fail_count dalam jendela, baru_terkunci)."""
    ts = naive(now())
    params = {"id": new_id(), "k": key, "scope": scope, "now": ts, "win": naive(now() - window),
              "max": max_fails, "lock": naive(now() + lock)}
    sql = sa.text(
        "INSERT INTO public_rate_limits (id, key_hash, scope, fail_count, window_start, locked_until, status, created_at, updated_at)"
        " VALUES (:id, :k, :scope, 1, :now, NULL, 'active', :now, :now)"
        " ON DUPLICATE KEY UPDATE"
        "  window_start = IF(window_start < :win, :now, window_start),"
        "  fail_count = IF(window_start = :now, 1, fail_count + 1),"
        "  locked_until = IF(fail_count >= :max, :lock, locked_until),"
        "  updated_at = :now")
    async with get_engine().begin() as conn:
        await conn.execute(sql, params)
        count = (await conn.execute(sa.text("SELECT fail_count FROM public_rate_limits WHERE key_hash = :k"), {"k": key})).scalar() or 0
    return int(count), int(count) == max_fails


async def rate_reset(key: str) -> None:
    """Setelah verifikasi berhasil: counter target direset (bukan counter IP)."""
    async with get_engine().begin() as conn:
        await conn.execute(sa.text("DELETE FROM public_rate_limits WHERE key_hash = :k AND scope = 'verify_target'"), {"k": key})


async def ip_locked(ip: Optional[str]) -> bool:
    return await rate_locked(ip_key(ip))


async def record_ip_failure(ip: Optional[str]) -> None:
    await record_failure(ip_key(ip), "verify_ip", IP_MAX_FAILS, IP_WINDOW, IP_LOCK)


async def link_release_expired_lock(link_id: str) -> None:
    ts = naive(now())
    async with get_engine().begin() as conn:
        await conn.execute(sa.text(
            "UPDATE employee_public_links SET failed_attempts = 0, locked_until = NULL, updated_at = :now"
            " WHERE id = :id AND locked_until IS NOT NULL AND locked_until <= :now"), {"id": link_id, "now": ts})


async def record_link_failure(link_id: str) -> Tuple[int, bool]:
    """Naikkan counter gagal secara atomik; kunci sementara bila mencapai batas. -> (attempts, locked_now)."""
    ts = naive(now())
    async with get_engine().begin() as conn:
        await conn.execute(sa.text(
            "UPDATE employee_public_links SET failed_attempts = COALESCE(failed_attempts, 0) + 1,"
            " total_failed_attempts = COALESCE(total_failed_attempts, 0) + 1, last_failed_at = :now, updated_at = :now"
            " WHERE id = :id"), {"id": link_id, "now": ts})
        res = await conn.execute(sa.text(
            "UPDATE employee_public_links SET locked_until = :lock WHERE id = :id AND failed_attempts >= :max"
            " AND (locked_until IS NULL OR locked_until <= :now)"),
            {"id": link_id, "lock": naive(now() + LINK_LOCK), "max": LINK_MAX_FAILS, "now": ts})
        attempts = (await conn.execute(sa.text("SELECT failed_attempts FROM employee_public_links WHERE id = :id"),
                                       {"id": link_id})).scalar() or 0
    return int(attempts), res.rowcount > 0


# ------------------------------------------------------------------ lookup link/sesi (lintas tenant, via hash unik)
async def find_link_by(column: str, value: str) -> Optional[Dict[str, Any]]:
    t = get_table("employee_public_links")
    async with get_engine().connect() as conn:
        row = (await conn.execute(sa.select(t).where(t.c[column] == value).limit(1))).first()
    if not row:
        return None
    data = dict(row._mapping)
    data.pop("extra", None)
    return data


# ------------------------------------------------------------------ whitelist field
GENDER_KEYS = ("male", "female")
MARITAL_KEYS = ("single", "married", "divorced")

# key -> (section, label, validator, sensitive, identity)
EDITABLE_FIELDS: Dict[str, Tuple[str, str, Optional[str], bool, bool]] = {
    "full_name": ("personal", "Nama lengkap (sesuai KTP)", "name", False, True),
    "nik": ("personal", "NIK KTP", "nik", True, True),
    "gender": ("personal", "Jenis kelamin", "enum:gender", False, False),
    "birth_place": ("personal", "Tempat lahir", "text", False, False),
    "birth_date": ("personal", "Tanggal lahir", "date", False, True),
    "marital_status": ("personal", "Status pernikahan", "enum:marital", False, False),
    "religion": ("personal", "Agama", "enum:religion", False, False),
    "education": ("personal", "Pendidikan terakhir", "enum:education", False, False),
    "phone": ("contact", "No. HP", "phone", False, False),
    "email": ("contact", "Email pribadi", "email", False, False),
    "address": ("contact", "Alamat sesuai KTP", "longtext", False, False),
    "city": ("contact", "Kota / Kabupaten", "text", False, False),
    "province": ("contact", "Provinsi", "text", False, False),
    "postal_code": ("contact", "Kode pos", "postal", False, False),
    "domicile_address": ("contact", "Alamat domisili", "longtext", False, False),
    "emergency_contact_name": ("contact", "Nama kontak darurat", "name", False, False),
    "emergency_contact_phone": ("contact", "No. HP kontak darurat", "phone", False, False),
    "bank_name": ("bank_tax", "Nama bank", "text", False, False),
    "bank_account_number": ("bank_tax", "Nomor rekening", "bank_account", True, False),
    "bank_account_name": ("bank_tax", "Nama pemilik rekening", "name", False, False),
    "npwp": ("bank_tax", "NPWP", "npwp", True, False),
    "bpjs_kesehatan_number": ("bpjs", "No. BPJS Kesehatan", "bpjs", True, False),
    "bpjs_tk_number": ("bpjs", "No. BPJS Ketenagakerjaan", "bpjs", True, False),
}
SENSITIVE_FIELDS = {k for k, v in EDITABLE_FIELDS.items() if v[3]}
IDENTITY_FIELDS = {k for k, v in EDITABLE_FIELDS.items() if v[4]}
DIGIT_FIELDS = {"nik", "npwp", "bank_account_number", "bpjs_kesehatan_number", "bpjs_tk_number", "postal_code"}
SECTIONS = [("personal", "Data Pribadi"), ("contact", "Kontak & Alamat"), ("family", "Keluarga"),
            ("bank_tax", "Bank & Pajak"), ("bpjs", "BPJS"), ("documents", "Dokumen")]
FAMILY_EDITABLE = ("relationship", "full_name", "nik", "birth_place", "birth_date", "gender",
                   "occupation", "is_emergency_contact", "phone")


def normalize_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip()
    if not s:
        return None
    if key in DIGIT_FIELDS:
        return norm_digits(s)
    if key in ("gender", "marital_status", "religion", "education"):
        return s.lower()
    if key == "email":
        return s.lower()
    if key == "birth_date":
        return norm_date(s) or s
    return s


def validate_field(key: str, value: Any, enums: Dict[str, List[str]]) -> Optional[str]:
    """Kembalikan pesan error (Bahasa Indonesia) atau None. Nilai sudah dinormalisasi & tidak kosong."""
    validator = EDITABLE_FIELDS[key][2]
    s = str(value)
    if validator == "name":
        return None if 2 <= len(s) <= 255 else "Minimal 2 karakter, maksimal 255 karakter."
    if validator == "text":
        return None if len(s) <= 255 else "Maksimal 255 karakter."
    if validator == "longtext":
        return None if len(s) <= 1000 else "Maksimal 1000 karakter."
    if validator == "postal":
        return None if re.fullmatch(r"\d{5}", s) else "Kode pos harus 5 digit angka."
    if validator == "nik":
        return None if V.digits_ok("nik", s) else "NIK harus 16 digit angka."
    if validator == "npwp":
        return None if V.digits_ok("npwp", s) else "NPWP harus 15 atau 16 digit angka."
    if validator == "bank_account":
        return None if V.digits_ok("bank_account", s) else "Nomor rekening harus 5-30 digit angka."
    if validator == "bpjs":
        return None if V.digits_ok("bpjs", s) else "Nomor BPJS harus 8-20 digit angka."
    if validator == "phone":
        return None if V.phone_ok(s) else "Nomor HP tidak valid (8-15 digit, boleh diawali +)."
    if validator == "email":
        return None if V.email_ok(s) and len(s) <= 255 else "Format email tidak valid."
    if validator == "date":
        if not V.date_ok(s):
            return "Tanggal tidak valid (format YYYY-MM-DD, tidak boleh di masa depan)."
        return None if s >= "1930-01-01" else "Tanggal tidak valid."
    if validator and validator.startswith("enum:"):
        allowed = enums.get(validator[5:], [])
        return None if s in allowed else "Pilihan tidak dikenal."
    return None
