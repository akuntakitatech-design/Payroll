import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  CalendarOff,
  CheckCircle2,
  Clock,
  Crosshair,
  Loader2,
  LogIn,
  LogOut,
  MapPin,
  Navigation,
  PencilLine,
  RefreshCw,
  Timer,
  UserX,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, TableCard, FilterSelect } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import ToneBadge from "@/components/time/ToneBadge";
import ApprovalTimeline from "@/components/time/ApprovalTimeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  clockInZone,
  currentPeriodKey,
  dayLabel,
  minutesToLabel,
  periodOptions,
  timeInZone,
} from "@/lib/timeCatalog";
import { useAuth } from "@/lib/auth";

const CORRECTION_TYPES = [
  { value: "missing_check_in", label: "Lupa Absen Masuk" },
  { value: "missing_check_out", label: "Lupa Absen Pulang" },
  { value: "wrong_time", label: "Waktu Salah" },
];

const GPS_FAILED_MESSAGE =
  "Lokasi belum dapat diperoleh. Aktifkan izin lokasi pada perangkat/browser lalu coba kembali.";

/** Ambil koordinat perangkat. Tidak ada fallback IP: tanpa GPS tidak ada absensi. */
const getPosition = () =>
  new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new Error("Perangkat atau peramban Anda tidak mendukung pengambilan lokasi (GPS)."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          location_captured_at: new Date(pos.timestamp).toISOString(),
        }),
      (err) => {
        const messages = {
          1: GPS_FAILED_MESSAGE,
          2: GPS_FAILED_MESSAGE,
          3: "Waktu pengambilan lokasi habis. Pindah ke area dengan sinyal lebih baik lalu coba kembali.",
        };
        reject(new Error(messages[err?.code] || GPS_FAILED_MESSAGE));
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
    );
  });

const newRequestId = () => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const InfoItem = ({ label, value, sub, icon: Icon, testId }) => (
  <div className="flex items-start gap-2.5 rounded-lg border border-border bg-background/60 p-3">
    {Icon && (
      <span className="mt-0.5 rounded-md border border-border bg-muted p-1.5 text-muted-foreground">
        <Icon className="h-4 w-4" strokeWidth={1.75} />
      </span>
    )}
    <div className="min-w-0 flex-1">
      <p className="text-[12px] text-muted-foreground">{label}</p>
      <p className="break-words text-sm font-semibold leading-snug text-foreground" data-testid={testId}>
        {value ?? "-"}
      </p>
      {sub && <p className="line-clamp-2 text-[12px] leading-snug text-muted-foreground">{sub}</p>}
    </div>
  </div>
);

const MyAttendancePage = () => {
  const { can } = useAuth();
  const [today, setToday] = useState(null);
  const [loadingToday, setLoadingToday] = useState(true);
  const [period, setPeriod] = useState(currentPeriodKey());
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [busy, setBusy] = useState(false); // sedang kirim ke server
  const [locating, setLocating] = useState(false); // sedang ambil GPS
  const [approval, setApproval] = useState(null);

  // Jam berjalan berbasis waktu server (offset terhadap jam perangkat).
  const serverOffsetRef = useRef(0);
  const [now, setNow] = useState(() => new Date());

  const [geoDialog, setGeoDialog] = useState(null); // { mode, position, message, requestId }
  const [reasonCode, setReasonCode] = useState("");
  const [reasonText, setReasonText] = useState("");

  const [correctionOpen, setCorrectionOpen] = useState(false);
  const [correction, setCorrection] = useState({
    work_date: "",
    correction_type: "wrong_time",
    proposed_check_in_at: "",
    proposed_check_out_at: "",
    reason: "",
  });
  const [corrections, setCorrections] = useState([]);
  const [submittingCorrection, setSubmittingCorrection] = useState(false);

  const loadToday = useCallback(async () => {
    setLoadingToday(true);
    try {
      const { data } = await api.get("/attendance/me/today");
      setToday(data);
      if (data?.server_time) {
        const server = new Date(data.server_time).getTime();
        if (!Number.isNaN(server)) serverOffsetRef.current = server - Date.now();
      }
      if (data?.attendance?.id && data.attendance.location_approval_status !== "not_required") {
        try {
          const res = await api.get(`/attendance/${data.attendance.id}`);
          setApproval(res.data?.approval || null);
        } catch (e) {
          setApproval(null);
        }
      } else {
        setApproval(null);
      }
    } catch (error) {
      toast.error(errorMessage(error, "Status absensi hari ini tidak dapat dimuat."));
    } finally {
      setLoadingToday(false);
    }
  }, []);

  const loadHistory = useCallback(async (periodKey) => {
    setLoadingHistory(true);
    try {
      const { data } = await api.get("/attendance/me", { params: { period: periodKey } });
      setHistory(data?.items || []);
    } catch (error) {
      toast.error(errorMessage(error, "Riwayat absensi tidak dapat dimuat."));
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  const loadCorrections = useCallback(async () => {
    try {
      const { data } = await api.get("/attendance/corrections", { params: { mine: true } });
      setCorrections(data?.items || []);
    } catch (error) {
      setCorrections([]);
    }
  }, []);

  useEffect(() => {
    loadToday();
    loadCorrections();
  }, [loadToday, loadCorrections]);

  useEffect(() => {
    loadHistory(period);
  }, [loadHistory, period]);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date(Date.now() + serverOffsetRef.current)), 1000);
    return () => clearInterval(id);
  }, []);

  const tz = today?.timezone;

  const submitClock = async (mode, payload, requestId) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/attendance/${mode === "in" ? "check-in" : "check-out"}`, {
        ...payload,
        source: "web",
        client_request_id: requestId,
      });
      toast.success(data?.message || (mode === "in" ? "Absen Masuk tercatat." : "Absen Pulang tercatat."), {
        duration: 6000,
      });
      setGeoDialog(null);
      setReasonCode("");
      setReasonText("");
      await Promise.all([loadToday(), loadHistory(period)]);
    } catch (error) {
      const detail = error?.response?.data?.detail || "";
      const isOutside =
        error?.response?.status === 422 &&
        /radius|alasan|akurasi/i.test(String(detail)) &&
        payload?.latitude !== undefined &&
        !payload?.reason_code;
      if (isOutside) {
        // Di luar radius: transaksi TIDAK dibuang — minta alasan lalu kirim ulang dengan kunci yang sama.
        setGeoDialog({ mode, position: payload, message: String(detail), requestId });
      } else {
        toast.error(errorMessage(error, "Absensi tidak dapat diproses."), { duration: 8000 });
        if (error?.response?.status === 409) await loadToday();
      }
    } finally {
      setBusy(false);
    }
  };

  const clock = async (mode) => {
    if (busy || locating) return; // anti double-click
    const requestId = newRequestId();
    let payload = {};
    if (today?.gps_required) {
      setLocating(true);
      try {
        payload = await getPosition();
      } catch (error) {
        setLocating(false);
        toast.error(error.message, { duration: 8000 });
        return; // tanpa GPS -> tidak ada absensi palsu
      }
      setLocating(false);
    }
    await submitClock(mode, payload, requestId);
  };

  const submitWithReason = async () => {
    if (!reasonCode) {
      toast.error("Pilih alasan absensi di luar radius terlebih dahulu.");
      return;
    }
    if (reasonCode === "other" && reasonText.trim().length < 3) {
      toast.error("Keterangan wajib diisi bila memilih alasan Lainnya.");
      return;
    }
    await submitClock(
      geoDialog.mode,
      { ...geoDialog.position, reason_code: reasonCode, reason: reasonText.trim() || null },
      geoDialog.requestId
    );
  };

  const openCorrection = (row) => {
    setCorrection({
      work_date: row?.work_date || today?.work_date || "",
      correction_type: row?.check_in_at ? (row?.check_out_at ? "wrong_time" : "missing_check_out") : "missing_check_in",
      proposed_check_in_at: row?.check_in_at ? row.check_in_at.slice(0, 16) : "",
      proposed_check_out_at: row?.check_out_at ? row.check_out_at.slice(0, 16) : "",
      reason: "",
    });
    setCorrectionOpen(true);
  };

  const submitCorrection = async () => {
    if (!correction.work_date) {
      toast.error("Tanggal kerja wajib dipilih.");
      return;
    }
    if (correction.reason.trim().length < 3) {
      toast.error("Alasan koreksi wajib diisi minimal 3 karakter.");
      return;
    }
    setSubmittingCorrection(true);
    try {
      const toIso = (value) => (value ? new Date(value).toISOString() : null);
      await api.post("/attendance/corrections", {
        work_date: correction.work_date,
        correction_type: correction.correction_type,
        proposed_check_in_at: toIso(correction.proposed_check_in_at),
        proposed_check_out_at: toIso(correction.proposed_check_out_at),
        reason: correction.reason.trim(),
      });
      toast.success("Pengajuan koreksi absensi terkirim dan menunggu persetujuan.");
      setCorrectionOpen(false);
      await Promise.all([loadCorrections(), loadHistory(period)]);
    } catch (error) {
      toast.error(errorMessage(error, "Pengajuan koreksi tidak dapat dikirim."));
    } finally {
      setSubmittingCorrection(false);
    }
  };

  const att = today?.attendance;
  const status = today?.today_status;
  const complete = Boolean(att?.check_in_at && att?.check_out_at);
  const working = Boolean(today?.can_check_out);
  const canIn = Boolean(today?.can_check_in);
  const noSchedule = today && !today.has_schedule;
  const dayOff = Boolean(today?.is_day_off);
  const pendingLocation = att?.location_approval_status === "pending";
  const rejectedLocation = att?.location_approval_status === "rejected";

  const columns = useMemo(
    () => [
      {
        key: "work_date",
        header: "Tanggal",
        render: (row) => (
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-foreground">{dayLabel(row.work_date)}</p>
            <p className="text-[12px] text-muted-foreground sm:hidden">{row.shift_name || row.day_type_label || "-"}</p>
          </div>
        ),
      },
      {
        key: "shift",
        header: "Shift",
        hideOnMobile: true,
        render: (row) => row.shift_name || row.day_type_label || "-",
      },
      { key: "check_in", header: "Masuk", render: (row) => timeInZone(row.check_in_at, tz) },
      { key: "check_out", header: "Pulang", render: (row) => timeInZone(row.check_out_at, tz) },
      {
        key: "status",
        header: "Status",
        render: (row) => <ToneBadge tone={row.attendance_status_tone} label={row.attendance_status_label} />,
      },
      {
        key: "location",
        header: "Lokasi Kerja",
        hideOnMobile: true,
        render: (row) => row.work_location_name || "-",
      },
      {
        key: "work",
        header: "Jam Kerja",
        align: "right",
        hideOnMobile: true,
        render: (row) => minutesToLabel(row.actual_work_minutes),
      },
      {
        key: "actions",
        header: "",
        render: (row) =>
          can("attendance", "create") ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => openCorrection(row)}
              data-testid={`correction-open-${row.work_date}`}
            >
              <PencilLine className="mr-1.5 h-3.5 w-3.5" /> Koreksi
            </Button>
          ) : null,
      },
    ],
    [can, tz] // eslint-disable-line react-hooks/exhaustive-deps
  );

  if (loadingToday && !today) {
    return (
      <PageBody>
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </PageBody>
    );
  }

  if (today && today.linked === false) {
    return (
      <PageBody>
        <EmptyState
          icon={UserX}
          title="Akun Anda belum terhubung ke Data Karyawan"
          description={
            today.message ||
            "Hubungi HR agar akun pengguna Anda ditautkan ke Data Karyawan pada perusahaan aktif, lalu absensi mandiri dapat digunakan."
          }
          testId="my-attendance-not-linked"
        />
      </PageBody>
    );
  }

  const primaryLabel = locating ? "Mengambil lokasi…" : busy ? "Memproses…" : null;

  return (
    <PageBody>
      {/* ================= KARTU ABSENSI HARI INI ================= */}
      <Card data-testid="my-attendance-card" className="overflow-hidden">
        <CardHeader className="space-y-3 pb-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-[12px] font-medium uppercase tracking-wide text-muted-foreground">Hari ini</p>
              <h2 className="text-lg font-semibold text-foreground" data-testid="my-attendance-date">
                {dayLabel(today?.work_date)}
              </h2>
              <p className="text-[12px] text-muted-foreground">
                {today?.employee?.full_name}
                {today?.employee?.employee_number ? ` · ${today.employee.employee_number}` : ""}
              </p>
            </div>
            <div className="text-right">
              <p
                className="text-2xl font-semibold tabular-nums text-foreground"
                data-numeric="true"
                data-testid="my-attendance-clock"
              >
                {clockInZone(now, tz)}
              </p>
              <p className="text-[12px] text-muted-foreground">Waktu server · {tz || "-"}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] text-muted-foreground">Status hari ini</span>
            <ToneBadge
              tone={status?.tone || "neutral"}
              label={status?.label || "-"}
              className="text-[13px]"
              testId="my-attendance-status"
            />
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Jadwal & lokasi */}
          <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
            <InfoItem
              icon={Timer}
              label="Shift Hari Ini"
              value={dayOff ? "OFF" : today?.shift?.name || (noSchedule ? "Belum ada" : "-")}
              sub={
                today?.shift
                  ? `${today.shift.start_time || "-"} – ${today.shift.end_time || "-"}${
                      today.shift.is_overnight ? " (lintas hari)" : ""
                    }`
                  : today?.day_type_label
              }
              testId="my-shift-name"
            />
            <InfoItem
              icon={MapPin}
              label="Lokasi Kerja"
              value={today?.work_location?.name || "-"}
              sub={
                today?.location_policy_label
                  ? `${today.location_policy_label}${
                      today?.work_location?.radius_meter && today.location_policy !== "disabled"
                        ? ` · ${Math.round(today.work_location.radius_meter)} m`
                        : ""
                    }`
                  : undefined
              }
              testId="my-work-location"
            />
            <InfoItem
              icon={LogIn}
              label="Absen Masuk"
              value={timeInZone(att?.check_in_at, tz)}
              sub={att?.check_in_at ? att.check_in_geofence_label : undefined}
              testId="my-check-in-time"
            />
            <InfoItem
              icon={LogOut}
              label="Absen Pulang"
              value={timeInZone(att?.check_out_at, tz)}
              sub={att?.check_out_at ? att.check_out_geofence_label : undefined}
              testId="my-check-out-time"
            />
          </div>

          {/* Kondisi khusus */}
          {noSchedule && !dayOff && (
            <div
              className="flex items-start gap-2 rounded-md border border-warning-border bg-warning-soft px-3 py-2.5 text-[13px] text-warning"
              data-testid="my-attendance-no-schedule"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-semibold">Jadwal kerja belum tersedia.</p>
                <p className="opacity-90">
                  Hubungi HR untuk menetapkan jadwal kerja Anda. Hari ini tidak dihitung sebagai Alfa secara otomatis.
                </p>
              </div>
            </div>
          )}
          {dayOff && (
            <div
              className="flex items-start gap-2 rounded-md border border-border bg-muted px-3 py-2.5 text-[13px] text-muted-foreground"
              data-testid="my-attendance-day-off"
            >
              <CalendarOff className="mt-0.5 h-4 w-4 shrink-0" />
              <p>Hari ini adalah hari OFF Anda. Tidak ada absensi yang perlu dilakukan.</p>
            </div>
          )}
          {pendingLocation && (
            <div
              className="rounded-md border border-warning-border bg-warning-soft px-3 py-2.5 text-[13px] text-warning"
              data-testid="my-attendance-pending-location"
            >
              <p className="font-semibold">Menunggu Persetujuan Lokasi</p>
              <p className="opacity-90">
                {att.location_approval_for_label || "Absensi"} Anda berada di luar radius lokasi kerja
                {att.check_in_distance_meter != null && att.location_approval_for !== "check_out"
                  ? ` (jarak ${Math.round(att.check_in_distance_meter)} m)`
                  : att.check_out_distance_meter != null
                    ? ` (jarak ${Math.round(att.check_out_distance_meter)} m)`
                    : ""}
                . Alasan: {att.check_out_location_reason_label || att.location_reason_label || "-"}
                {att.check_out_location_reason || att.location_reason
                  ? ` — ${att.check_out_location_reason || att.location_reason}`
                  : ""}
                .
              </p>
            </div>
          )}
          {rejectedLocation && (
            <div
              className="rounded-md border border-danger-border bg-danger-soft px-3 py-2.5 text-[13px] text-danger"
              data-testid="my-attendance-rejected-location"
            >
              <p className="font-semibold">Lokasi Ditolak</p>
              <p className="opacity-90">
                Lokasi absensi Anda ditolak oleh penyetuju
                {att.location_decision_notes ? `: ${att.location_decision_notes}` : "."} Riwayat absensi tetap
                tersimpan; hubungi HR bila diperlukan koreksi.
              </p>
            </div>
          )}
          {approval?.steps?.length > 0 && (
            <ApprovalTimeline rows={approval.steps} testId="my-attendance-approval-timeline" />
          )}

          {/* Aksi utama — hanya yang relevan */}
          <div className="space-y-2" data-testid="my-attendance-actions">
            {canIn && (
              <Button
                size="lg"
                className="h-14 w-full text-base font-semibold shadow-sm sm:h-12 sm:w-auto sm:min-w-[16rem]"
                onClick={() => clock("in")}
                disabled={busy || locating}
                data-testid="check-in-button"
              >
                {busy || locating ? (
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                ) : (
                  <LogIn className="mr-2 h-5 w-5" />
                )}
                {primaryLabel || "Absen Masuk"}
              </Button>
            )}
            {working && (
              <Button
                size="lg"
                className="h-14 w-full text-base font-semibold shadow-sm sm:h-12 sm:w-auto sm:min-w-[16rem]"
                onClick={() => clock("out")}
                disabled={busy || locating}
                data-testid="check-out-button"
              >
                {busy || locating ? (
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                ) : (
                  <LogOut className="mr-2 h-5 w-5" />
                )}
                {primaryLabel || "Absen Pulang"}
              </Button>
            )}
            {complete && (
              <div
                className={cn(
                  "grid grid-cols-3 gap-2 rounded-lg border p-3",
                  rejectedLocation
                    ? "border-danger-border bg-danger-soft"
                    : pendingLocation
                      ? "border-warning-border bg-warning-soft"
                      : "border-success-border bg-success-soft"
                )}
                data-testid="my-attendance-summary"
              >
                <div
                  className={cn(
                    "col-span-3 flex items-center gap-2 text-[13px] font-semibold",
                    rejectedLocation ? "text-danger" : pendingLocation ? "text-warning" : "text-success"
                  )}
                >
                  {rejectedLocation ? (
                    <AlertTriangle className="h-4 w-4" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                  {rejectedLocation
                    ? "Absensi hari ini tercatat, namun lokasi ditolak"
                    : pendingLocation
                      ? "Absensi hari ini lengkap, menunggu persetujuan lokasi"
                      : "Absensi hari ini sudah lengkap"}
                </div>
                <div>
                  <p className="text-[12px] text-muted-foreground">Jam Kerja</p>
                  <p className="text-sm font-semibold text-foreground" data-numeric="true">
                    {minutesToLabel(att.actual_work_minutes)}
                  </p>
                </div>
                <div>
                  <p className="text-[12px] text-muted-foreground">Terlambat</p>
                  <p className="text-sm font-semibold text-foreground" data-numeric="true">
                    {minutesToLabel(att.late_minutes)}
                  </p>
                </div>
                <div>
                  <p className="text-[12px] text-muted-foreground">Pulang Cepat</p>
                  <p className="text-sm font-semibold text-foreground" data-numeric="true">
                    {minutesToLabel(att.early_leave_minutes)}
                  </p>
                </div>
              </div>
            )}
            {today?.gps_required && (canIn || working) && (
              <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                <Crosshair className="h-3.5 w-3.5" />
                Lokasi GPS akan diminta saat menekan tombol. Waktu absensi memakai waktu server.
              </p>
            )}
          </div>

          <Separator />

          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={loadToday} disabled={busy} data-testid="refresh-today">
              <RefreshCw className={cn("mr-2 h-4 w-4", loadingToday && "animate-spin")} /> Muat Ulang
            </Button>
            {can("attendance", "create") && (
              <Button variant="ghost" size="sm" onClick={() => openCorrection(att)} data-testid="open-correction-button">
                <PencilLine className="mr-2 h-4 w-4" /> Ajukan Koreksi
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ================= RIWAYAT ================= */}
      <div className="space-y-3">
        <SectionHeader
          title="Riwayat Absensi Saya"
          description="Hanya data kehadiran Anda sendiri pada periode terpilih."
          actions={
            <FilterSelect
              value={period}
              onChange={(v) => setPeriod(v || currentPeriodKey())}
              options={periodOptions()}
              allLabel="Periode"
              testId="my-history-period"
            />
          }
        />
        <TableCard>
          <DataTable
            columns={columns}
            rows={history}
            loading={loadingHistory}
            rowKey={(r) => r.id}
            testId="my-attendance-table"
            emptyProps={{
              icon: Clock,
              title: "Belum ada data absensi pada periode ini.",
              description: "Lakukan Absen Masuk pada hari kerja, atau pilih periode lain.",
            }}
          />
        </TableCard>
      </div>

      {corrections.length > 0 && (
        <div className="space-y-3">
          <SectionHeader title="Pengajuan Koreksi Saya" description="Status persetujuan koreksi absensi." />
          <div className="grid gap-3 lg:grid-cols-2">
            {corrections.slice(0, 6).map((row) => (
              <Card key={row.id} data-testid={`my-correction-${row.id}`}>
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                    {dayLabel(row.work_date)}
                    <ToneBadge tone={row.request_status_tone} label={row.request_status_label} />
                  </div>
                  <p className="text-[12px] text-muted-foreground">
                    {row.correction_type_label} · {row.reason}
                  </p>
                </CardHeader>
                <CardContent>
                  <ApprovalTimeline rows={row.approval?.steps || row.approval?.rows || []} testId={`correction-timeline-${row.id}`} />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* ================= DIALOG LUAR RADIUS ================= */}
      <Dialog open={!!geoDialog} onOpenChange={(open) => !open && !busy && setGeoDialog(null)}>
        <DialogContent className="bg-card sm:max-w-lg" data-testid="geofence-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-semibold">
              <Navigation className="h-4 w-4 text-warning" /> Anda berada di luar radius lokasi kerja.
            </DialogTitle>
            <DialogDescription className="leading-relaxed">
              {geoDialog?.message ||
                "Titik GPS Anda berada di luar radius lokasi kerja. Absensi tetap disimpan dan akan diproses melalui persetujuan."}{" "}
              Pilih alasan agar absensi dapat diproses melalui persetujuan atasan/HR.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-[13px] font-medium">
                Alasan <span className="text-destructive">*</span>
              </Label>
              <Select value={reasonCode} onValueChange={setReasonCode}>
                <SelectTrigger data-testid="geofence-reason-code" className="h-11">
                  <SelectValue placeholder="Pilih alasan…" />
                </SelectTrigger>
                <SelectContent>
                  {(today?.reason_codes || []).map((item) => (
                    <SelectItem key={item.key} value={item.key} data-testid={`geofence-reason-${item.key}`}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="geofence-reason" className="text-[13px] font-medium">
                Keterangan {reasonCode === "other" && <span className="text-destructive">*</span>}
              </Label>
              <Textarea
                id="geofence-reason"
                rows={3}
                value={reasonText}
                onChange={(e) => setReasonText(e.target.value)}
                placeholder={
                  reasonCode === "other"
                    ? "Wajib diisi: jelaskan alasan Anda berada di luar radius."
                    : "Opsional. Contoh: kunjungan pelanggan di Bekasi bersama tim penjualan."
                }
                data-testid="geofence-reason-text"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setGeoDialog(null)} disabled={busy} data-testid="geofence-cancel">
              Batal
            </Button>
            <Button onClick={submitWithReason} disabled={busy} data-testid="geofence-submit">
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Kirim untuk Persetujuan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ================= DIALOG KOREKSI ================= */}
      <Dialog open={correctionOpen} onOpenChange={setCorrectionOpen}>
        <DialogContent className="bg-card sm:max-w-xl" data-testid="correction-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Ajukan Koreksi Absensi</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Koreksi akan diproses melalui alur persetujuan dan hanya diterapkan setelah disetujui.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="correction-date" className="text-[13px] font-medium">
                Tanggal Kerja <span className="text-destructive">*</span>
              </Label>
              <Input
                id="correction-date"
                type="date"
                value={correction.work_date}
                onChange={(e) => setCorrection((s) => ({ ...s, work_date: e.target.value }))}
                data-testid="correction-work-date"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[13px] font-medium">Jenis Koreksi</Label>
              <Select
                value={correction.correction_type}
                onValueChange={(v) => setCorrection((s) => ({ ...s, correction_type: v }))}
              >
                <SelectTrigger data-testid="correction-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CORRECTION_TYPES.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="correction-in" className="text-[13px] font-medium">
                Usulan Jam Masuk
              </Label>
              <Input
                id="correction-in"
                type="datetime-local"
                value={correction.proposed_check_in_at}
                onChange={(e) => setCorrection((s) => ({ ...s, proposed_check_in_at: e.target.value }))}
                data-testid="correction-check-in"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="correction-out" className="text-[13px] font-medium">
                Usulan Jam Pulang
              </Label>
              <Input
                id="correction-out"
                type="datetime-local"
                value={correction.proposed_check_out_at}
                onChange={(e) => setCorrection((s) => ({ ...s, proposed_check_out_at: e.target.value }))}
                data-testid="correction-check-out"
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="correction-reason" className="text-[13px] font-medium">
                Alasan <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="correction-reason"
                rows={3}
                value={correction.reason}
                onChange={(e) => setCorrection((s) => ({ ...s, reason: e.target.value }))}
                placeholder="Contoh: lupa absen pulang karena rapat sampai malam."
                data-testid="correction-reason"
              />
            </div>
          </div>
          <Separator />
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setCorrectionOpen(false)}
              disabled={submittingCorrection}
              data-testid="correction-cancel"
            >
              Batal
            </Button>
            <Button onClick={submitCorrection} disabled={submittingCorrection} data-testid="correction-submit">
              Kirim Pengajuan
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default MyAttendancePage;
