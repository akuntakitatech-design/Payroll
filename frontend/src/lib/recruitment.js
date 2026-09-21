// Katalog tampilan Rekrutmen. Sumber kebenaran status ada di backend
// (app/core/recruitment_workflow.py); file ini hanya memetakan tone -> kelas.

export const STAGE_TONE_CLASS = {
  neutral: "border-border bg-muted text-muted-foreground",
  info: "border-primary-border bg-primary-soft text-primary",
  success: "border-success-border bg-success-soft text-success",
  warning: "border-warning-border bg-warning-soft text-warning",
  danger: "border-danger-border bg-danger-soft text-danger",
};

// Fallback label bila catalog belum termuat (tetap konsisten dengan backend).
export const STAGE_LABELS = {
  draft: "Draft",
  screening: "Screening",
  screening_passed: "Lolos Screening",
  screening_failed: "Tidak Lolos",
  interview_scheduled: "Interview Dijadwalkan",
  interview_done: "Interview Selesai",
  awaiting_approval: "Menunggu Approval",
  approved: "Disetujui",
  rejected: "Ditolak",
  offering: "Offering",
  offering_accepted: "Offering Diterima",
  offering_declined: "Offering Ditolak",
  hired: "Menjadi Karyawan",
};

export const STAGE_TONES = {
  draft: "neutral",
  screening: "info",
  screening_passed: "success",
  screening_failed: "danger",
  interview_scheduled: "info",
  interview_done: "info",
  awaiting_approval: "warning",
  approved: "success",
  rejected: "danger",
  offering: "info",
  offering_accepted: "success",
  offering_declined: "danger",
  hired: "success",
};

export const HISTORY_ACTION_LABELS = {
  create: "Kandidat dibuat",
  status_change: "Status diubah",
  screening: "Screening diisi",
  delete: "Kandidat dihapus",
  interview_scheduled: "Interview dijadwalkan",
  interview_completed: "Interview selesai",
  interview_cancelled: "Interview dibatalkan",
  approval_submit: "Diajukan untuk approval",
  approval_approved: "Approval disetujui",
  approval_rejected: "Approval ditolak",
  offering_sent: "Offering dikirim",
  offering_accepted: "Offering diterima",
  offering_declined: "Offering ditolak",
  offering_cancelled: "Offering dibatalkan",
  candidate_converted: "Jadikan Karyawan",
};

/** Ubah nilai form (string) menjadi payload angka/kosong yang bersih. */
export const cleanPayload = (values, numericKeys = []) => {
  const numeric = new Set(numericKeys);
  const payload = {};
  Object.entries(values || {}).forEach(([k, v]) => {
    if (v === "" || v === null || v === undefined) return;
    if (numeric.has(k)) {
      const n = Number(v);
      if (!Number.isNaN(n)) payload[k] = n;
      return;
    }
    payload[k] = v;
  });
  return payload;
};

export const RECRUITMENT_ROUTES = {
  dashboard: "/modules/recruitment",
  candidates: "/modules/recruitment/candidates",
  candidate: (id) => `/modules/recruitment/candidates/${id}`,
};

export const numberOrUndefined = (v) => {
  if (v === "" || v === null || v === undefined) return undefined;
  const n = Number(v);
  return Number.isNaN(n) ? undefined : n;
};

/** Bersihkan nilai form -> payload API (hapus kosong, konversi angka). */
export const toCandidatePayload = (values) => {
  const numeric = new Set(["expected_salary", "graduation_year", "experience_years"]);
  const payload = {};
  Object.entries(values || {}).forEach(([k, v]) => {
    if (v === "" || v === null || v === undefined) return;
    payload[k] = numeric.has(k) ? numberOrUndefined(v) : v;
    if (payload[k] === undefined) delete payload[k];
  });
  return payload;
};
