"""State machine Rekrutmen.

Semua transisi status kandidat WAJIB lewat modul ini (server-side).
Frontend hanya menampilkan tombol; keputusan sah/tidaknya ada di sini.

Tahap A hanya mengaktifkan: draft -> screening -> screening_passed | screening_failed.
Status tahap berikutnya sudah didaftarkan di katalog agar label konsisten,
tetapi belum memiliki transisi aktif (fail-closed).
"""
from typing import Dict, List, Optional, Set

from fastapi import HTTPException, status

# key -> (label_id, tone) ; tone dipakai frontend untuk badge
STAGES: Dict[str, Dict[str, str]] = {
    "draft": {"label": "Draft", "tone": "neutral"},
    "screening": {"label": "Screening", "tone": "info"},
    "screening_passed": {"label": "Lolos Screening", "tone": "success"},
    "screening_failed": {"label": "Tidak Lolos", "tone": "danger"},
    # --- disiapkan untuk tahap berikutnya (belum ada transisi aktif) ---
    "interview_scheduled": {"label": "Interview Dijadwalkan", "tone": "info"},
    "interview_done": {"label": "Interview Selesai", "tone": "info"},
    "awaiting_approval": {"label": "Menunggu Approval", "tone": "warning"},
    "approved": {"label": "Disetujui", "tone": "success"},
    "rejected": {"label": "Ditolak", "tone": "danger"},
    "offering": {"label": "Offering", "tone": "info"},
    "offering_accepted": {"label": "Offering Diterima", "tone": "success"},
    "offering_declined": {"label": "Offering Ditolak", "tone": "danger"},
    "hired": {"label": "Menjadi Karyawan", "tone": "success"},
}

# Transisi yang AKTIF (Tahap A + Tahap B). `hired` menyusul pada Tahap C.
TRANSITIONS: Dict[str, Set[str]] = {
    "draft": {"screening"},
    "screening": {"screening_passed", "screening_failed"},
    "screening_passed": {"interview_scheduled"},
    "screening_failed": set(),
    # interview: kembali ke screening_passed bila semua interview dibatalkan
    "interview_scheduled": {"interview_done", "screening_passed"},
    "interview_done": {"interview_scheduled", "awaiting_approval"},
    "awaiting_approval": {"approved", "rejected"},
    "approved": {"offering"},
    "rejected": set(),  # final pada Tahap B (resubmit = backlog)
    "offering": {"offering_accepted", "offering_declined", "approved"},  # approved = offering dibatalkan
    "offering_accepted": set(),  # -> hired pada Tahap C
    "offering_declined": {"offering"},  # offering versi baru dikirim
}

# Transisi yang hanya boleh terjadi lewat endpoint proses (bukan /status manual),
# karena membutuhkan data pendukung dan pengecekan integritas.
ENDPOINT_ONLY: Set[str] = {
    "screening_passed", "screening_failed",
    "interview_scheduled", "interview_done", "awaiting_approval", "approved", "rejected",
    "offering", "offering_accepted", "offering_declined",
}

# Status pipeline yang dianggap "kandidat aktif" (masih berjalan).
ACTIVE_STAGES: List[str] = [
    "draft", "screening", "screening_passed", "interview_scheduled", "interview_done",
    "awaiting_approval", "approved", "offering", "offering_accepted",
]
# Status akhir (tidak bisa lanjut).
TERMINAL_STAGES: List[str] = ["screening_failed", "rejected", "hired"]

# ------------------------------------------------------------------ interview
# Tahap interview boleh dijadwalkan pada status berikut.
INTERVIEW_ALLOWED_STAGES: Set[str] = {"screening_passed", "interview_scheduled", "interview_done"}
INTERVIEW_TYPES = [
    {"key": "hr", "label": "Interview HR"},
    {"key": "user", "label": "Interview User"},
    {"key": "manager", "label": "Interview Manager"},
    {"key": "technical", "label": "Interview Teknis"},
    {"key": "final", "label": "Interview Final"},
    {"key": "other", "label": "Lainnya"},
]
INTERVIEW_MODES = [{"key": "onsite", "label": "Tatap muka"}, {"key": "online", "label": "Online"}]
INTERVIEW_STATUSES = {
    "scheduled": {"label": "Terjadwal", "tone": "info"},
    "completed": {"label": "Selesai", "tone": "success"},
    "cancelled": {"label": "Dibatalkan", "tone": "neutral"},
}
INTERVIEW_RESULTS = {
    "passed": {"label": "Lolos", "tone": "success"},
    "considered": {"label": "Dipertimbangkan", "tone": "warning"},
    "failed": {"label": "Tidak Lolos", "tone": "danger"},
}
INTERVIEW_RECOMMENDATIONS = {
    "hire": "Rekomendasi diterima",
    "consider": "Dipertimbangkan",
    "no_hire": "Tidak direkomendasikan",
}

# ------------------------------------------------------------------ approval
APPROVAL_DECISIONS = {
    "pending": {"label": "Menunggu", "tone": "warning"},
    "approved": {"label": "Disetujui", "tone": "success"},
    "rejected": {"label": "Ditolak", "tone": "danger"},
    "skipped": {"label": "Tidak diproses", "tone": "neutral"},
}
# Tipe approver yang dapat dipetakan ke pengguna pada konteks rekrutmen.
SUPPORTED_APPROVER_TYPES: Set[str] = {"role", "user", "position"}

# ------------------------------------------------------------------ offering
OFFERING_ALLOWED_STAGES: Set[str] = {"approved", "offering_declined"}
OFFER_STATUSES = {
    "draft": {"label": "Draft", "tone": "neutral"},
    "sent": {"label": "Terkirim", "tone": "info"},
    "accepted": {"label": "Diterima", "tone": "success"},
    "declined": {"label": "Ditolak", "tone": "danger"},
    "cancelled": {"label": "Dibatalkan", "tone": "neutral"},
}

# Kandidat yang boleh dihapus (soft-delete). Kandidat yang sedang/selesai proses
# screening dengan hasil lolos tidak boleh dihapus agar jejak seleksi tetap utuh.
DELETABLE_STAGES: Set[str] = {"draft", "screening_failed"}

SCREENING_RESULTS = {
    "passed": {"label": "Lolos", "to_stage": "screening_passed"},
    "failed": {"label": "Tidak Lolos", "to_stage": "screening_failed"},
}
SCREENING_RECOMMENDATIONS = {
    "recommended": "Direkomendasikan",
    "consider": "Dipertimbangkan",
    "not_recommended": "Tidak direkomendasikan",
}

SOURCES = [
    {"key": "manual", "label": "Input HR"},
    {"key": "referral", "label": "Referensi Internal"},
    {"key": "job_portal", "label": "Portal Lowongan"},
    {"key": "social_media", "label": "Media Sosial"},
    {"key": "campus", "label": "Kampus / Institusi"},
    {"key": "excel_import", "label": "Impor Excel"},
    {"key": "other", "label": "Lainnya"},
]


def stage_label(key: Optional[str]) -> str:
    return STAGES.get(key or "", {}).get("label", key or "-")


def stage_catalog() -> List[Dict[str, str]]:
    return [{"key": k, "label": v["label"], "tone": v["tone"]} for k, v in STAGES.items()]


def active_stage_catalog() -> List[Dict[str, str]]:
    """Status yang benar-benar dipakai (punya transisi terdefinisi) — untuk filter UI."""
    return [
        {"key": k, "label": STAGES[k]["label"], "tone": STAGES[k]["tone"]}
        for k in STAGES.keys()
        if k in TRANSITIONS
    ]


def allowed_next(current: Optional[str]) -> List[str]:
    return sorted(TRANSITIONS.get(current or "draft", set()))


def assert_transition(current: Optional[str], target: str, via_endpoint: bool = False) -> None:
    """Tolak transisi yang tidak sah. via_endpoint=True bila dipanggil dari
    endpoint khusus (screening) yang membawa data pendukung."""
    current = current or "draft"
    if target not in STAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Status '{target}' tidak dikenal.")
    if target not in TRANSITIONS.get(current, set()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Perubahan status dari '{stage_label(current)}' ke '{stage_label(target)}' tidak diizinkan.",
        )
    if not via_endpoint and target in ENDPOINT_ONLY:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Status '{stage_label(target)}' hanya dapat ditetapkan melalui proses screening "
            "(isi hasil, skor, dan catatan screening).",
        )


def assert_deletable(current: Optional[str]) -> None:
    current = current or "draft"
    if current not in DELETABLE_STAGES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Kandidat dengan status '{stage_label(current)}' tidak dapat dihapus agar jejak seleksi "
            "tetap utuh. Gunakan hasil screening 'Tidak Lolos' bila kandidat tidak dilanjutkan.",
        )
