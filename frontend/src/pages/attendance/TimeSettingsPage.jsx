import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarDays, Clock, Lock, LockOpen, Plus, Save, Trash2 } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, FilterSelect, TableCard } from "@/components/common/DataTable";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import FormDialog from "@/components/common/FormDialog";
import ToneBadge from "@/components/time/ToneBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import { asOptions, dayLabel, invalidateTimeCatalog, periodOptions, useTimeCatalog } from "@/lib/timeCatalog";
import { formatDateTime } from "@/lib/format";

const SHIFT_FIELDS = [
  { name: "code", label: "Kode Shift", required: true, placeholder: "SHIFT-P" },
  { name: "name", label: "Nama Shift", required: true, placeholder: "Shift Pagi" },
  { name: "start_time", label: "Jam Masuk", placeholder: "08:00" },
  { name: "end_time", label: "Jam Pulang", placeholder: "17:00", hint: "Jam pulang lebih kecil dari jam masuk berarti shift lintas hari." },
  { name: "break_start", label: "Mulai Istirahat", placeholder: "12:00" },
  { name: "break_end", label: "Selesai Istirahat", placeholder: "13:00" },
  { name: "late_tolerance_minutes", label: "Toleransi Terlambat (menit)", type: "number" },
  { name: "early_leave_tolerance_minutes", label: "Toleransi Pulang Cepat (menit)", type: "number" },
  { name: "is_day_off", label: "Tandai Hari OFF", type: "boolean" },
  { name: "sort_order", label: "Urutan Tampil", type: "number" },
  { name: "description", label: "Keterangan", type: "textarea", colSpan: 2 },
];

const LEAVE_TYPE_FIELDS = (categories) => [
  { name: "code", label: "Kode", required: true, placeholder: "CT-TAHUNAN" },
  { name: "name", label: "Nama Jenis Cuti", required: true, placeholder: "Cuti Tahunan" },
  { name: "category", label: "Kategori", type: "select", required: true, options: categories },
  { name: "default_quota_days", label: "Kuota Default (hari)", type: "number" },
  { name: "deduct_balance", label: "Mengurangi Saldo Cuti", type: "boolean" },
  { name: "is_paid", label: "Dibayar", type: "boolean" },
  { name: "attachment_required", label: "Wajib Lampiran", type: "boolean" },
  { name: "allow_half_day", label: "Boleh Setengah Hari", type: "boolean" },
  { name: "approval_required", label: "Wajib Persetujuan", type: "boolean" },
  { name: "minimum_notice_days", label: "Minimal Pengajuan (hari)", type: "number" },
  { name: "maximum_consecutive_days", label: "Maksimal Berurutan (hari)", type: "number" },
  { name: "sort_order", label: "Urutan Tampil", type: "number" },
  { name: "description", label: "Keterangan", type: "textarea", colSpan: 2 },
];

const TimeSettingsPage = () => {
  const { can } = useAuth();
  const { catalog, reload: reloadCatalog } = useTimeCatalog();
  const editable = can("attendance", "edit") || can("attendance", "create");

  const [shifts, setShifts] = useState([]);
  const [leaveTypes, setLeaveTypes] = useState([]);
  const [calendarDays, setCalendarDays] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [policies, setPolicies] = useState(null);
  const [loading, setLoading] = useState(true);
  const [year, setYear] = useState(new Date().getFullYear());

  const [dialog, setDialog] = useState(null); // { kind: 'shift'|'leave_type', row }
  const [values, setValues] = useState({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(null); // { kind, row }
  const [removing, setRemoving] = useState(false);

  const [calForm, setCalForm] = useState({ calendar_date: "", day_type: "national_holiday", name: "" });
  const [savingCal, setSavingCal] = useState(false);

  const [periodAction, setPeriodAction] = useState(null); // { mode, period_key }
  const [periodReason, setPeriodReason] = useState("");
  const [periodBusy, setPeriodBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, l, c, p, pol] = await Promise.all([
        api.get("/time/shifts"),
        api.get("/time/leave-types"),
        api.get("/time/calendar-days", { params: { year } }),
        api.get("/time/periods", { params: { year } }),
        api.get("/time/policies"),
      ]);
      setShifts(s.data?.items || []);
      setLeaveTypes(l.data?.items || []);
      setCalendarDays(c.data?.items || []);
      setPeriods(p.data?.items || []);
      setPolicies(pol.data);
    } catch (error) {
      toast.error(errorMessage(error, "Pengaturan Time Management tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [year]);

  useEffect(() => {
    load();
  }, [load]);

  const refreshCatalog = () => {
    invalidateTimeCatalog();
    reloadCatalog(true);
  };

  const openDialog = (kind, row) => {
    setDialog({ kind, row });
    if (kind === "shift") {
      setValues(
        row
          ? { ...row }
          : {
              code: "",
              name: "",
              late_tolerance_minutes: 0,
              early_leave_tolerance_minutes: 0,
              is_day_off: false,
              sort_order: 0,
            }
      );
    } else {
      setValues(
        row
          ? { ...row }
          : {
              code: "",
              name: "",
              category: "leave",
              deduct_balance: true,
              is_paid: true,
              attachment_required: false,
              approval_required: true,
              allow_half_day: true,
              minimum_notice_days: 0,
              default_quota_days: 0,
              sort_order: 0,
            }
      );
    }
  };

  const save = async () => {
    if (!dialog) return;
    const isShift = dialog.kind === "shift";
    const base = isShift ? "/time/shifts" : "/time/leave-types";
    const numeric = isShift
      ? ["late_tolerance_minutes", "early_leave_tolerance_minutes", "sort_order"]
      : ["minimum_notice_days", "maximum_consecutive_days", "default_quota_days", "sort_order"];
    const payload = { ...values };
    numeric.forEach((key) => {
      payload[key] = payload[key] === "" || payload[key] === null || payload[key] === undefined ? null : Number(payload[key]);
    });
    if (isShift) {
      ["late_tolerance_minutes", "early_leave_tolerance_minutes", "sort_order"].forEach((k) => {
        payload[k] = payload[k] ?? 0;
      });
    } else {
      payload.default_quota_days = payload.default_quota_days ?? 0;
      payload.minimum_notice_days = payload.minimum_notice_days ?? 0;
      payload.sort_order = payload.sort_order ?? 0;
    }
    setSaving(true);
    try {
      if (dialog.row) await api.put(`${base}/${dialog.row.id}`, payload);
      else await api.post(base, payload);
      toast.success(dialog.row ? "Perubahan tersimpan." : "Data berhasil ditambahkan.");
      setDialog(null);
      refreshCatalog();
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Data tidak dapat disimpan."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!deleting) return;
    const base =
      deleting.kind === "shift"
        ? "/time/shifts"
        : deleting.kind === "leave_type"
        ? "/time/leave-types"
        : "/time/calendar-days";
    setRemoving(true);
    try {
      await api.delete(`${base}/${deleting.row.id}`);
      toast.success("Data berhasil dihapus.");
      setDeleting(null);
      refreshCatalog();
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Data tidak dapat dihapus."), { duration: 9000 });
    } finally {
      setRemoving(false);
    }
  };

  const addCalendarDay = async () => {
    if (!calForm.calendar_date || !calForm.name.trim()) {
      toast.error("Tanggal dan Nama hari khusus wajib diisi.");
      return;
    }
    setSavingCal(true);
    try {
      await api.post("/time/calendar-days", { ...calForm, name: calForm.name.trim() });
      toast.success("Hari khusus ditambahkan ke kalender kerja.");
      setCalForm({ calendar_date: "", day_type: "national_holiday", name: "" });
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Hari khusus tidak dapat ditambahkan."), { duration: 9000 });
    } finally {
      setSavingCal(false);
    }
  };

  const savePolicies = async () => {
    setSaving(true);
    try {
      const { data } = await api.put("/time/policies", policies);
      setPolicies(data);
      toast.success("Kebijakan Time Management tersimpan.");
    } catch (error) {
      toast.error(errorMessage(error, "Kebijakan tidak dapat disimpan."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const runPeriodAction = async () => {
    if (!periodAction) return;
    if (periodAction.mode === "reopen" && periodReason.trim().length < 3) {
      toast.error("Alasan wajib diisi saat membuka kembali periode.");
      return;
    }
    setPeriodBusy(true);
    try {
      const { data } = await api.post(`/time/periods/${periodAction.mode === "close" ? "close" : "reopen"}`, {
        period_key: periodAction.period_key,
        reason: periodReason.trim() || null,
      });
      toast.success(
        periodAction.mode === "close"
          ? `Periode ${data?.period_label || periodAction.period_key} ditutup.`
          : `Periode ${data?.period_label || periodAction.period_key} dibuka kembali.`
      );
      if (data?.warning) toast.warning(data.warning, { duration: 9000 });
      setPeriodAction(null);
      setPeriodReason("");
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Status periode tidak dapat diubah."), { duration: 9000 });
    } finally {
      setPeriodBusy(false);
    }
  };

  const setPolicy = (group, key, value) =>
    setPolicies((s) => ({ ...s, [group]: { ...(s?.[group] || {}), [key]: value } }));

  return (
    <PageBody>
      <Tabs defaultValue="shifts">
        <TabsList data-testid="settings-tabs">
          <TabsTrigger value="shifts" data-testid="settings-tab-shifts">
            Shift
          </TabsTrigger>
          <TabsTrigger value="calendar" data-testid="settings-tab-calendar">
            Kalender Kerja
          </TabsTrigger>
          <TabsTrigger value="leave-types" data-testid="settings-tab-leave-types">
            Jenis Cuti
          </TabsTrigger>
          <TabsTrigger value="policies" data-testid="settings-tab-policies">
            Kebijakan
          </TabsTrigger>
          <TabsTrigger value="periods" data-testid="settings-tab-periods">
            Periode
          </TabsTrigger>
        </TabsList>

        {/* SHIFT */}
        <TabsContent value="shifts" className="mt-4 space-y-3">
          <SectionHeader
            title="Master Shift Kerja"
            description="Jam masuk, jam pulang, istirahat, dan toleransi keterlambatan."
            actions={
              editable ? (
                <Button onClick={() => openDialog("shift", null)} data-testid="shift-create-button">
                  <Plus className="mr-2 h-4 w-4" /> Tambah Shift
                </Button>
              ) : null
            }
          />
          <TableCard>
            <DataTable
              loading={loading}
              rows={shifts}
              testId="shifts-table"
              columns={[
                {
                  key: "name",
                  header: "Shift",
                  render: (r) => (
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-foreground">{r.name}</p>
                      <p className="text-[12px] text-muted-foreground">{r.code}</p>
                    </div>
                  ),
                },
                {
                  key: "window",
                  header: "Jam Kerja",
                  render: (r) =>
                    r.is_day_off ? "OFF" : `${r.start_time || "-"} - ${r.end_time || "-"}${r.is_overnight ? " (lintas hari)" : ""}`,
                },
                {
                  key: "break",
                  header: "Istirahat",
                  hideOnMobile: true,
                  render: (r) => (r.break_start ? `${r.break_start} - ${r.break_end}` : "-"),
                },
                { key: "late_tolerance_minutes", header: "Toleransi Telat", align: "right" },
                {
                  key: "status",
                  header: "Status",
                  render: (r) => (
                    <ToneBadge tone={r.status === "active" ? "success" : "neutral"} label={r.status === "active" ? "Aktif" : "Nonaktif"} />
                  ),
                },
                {
                  key: "actions",
                  header: "",
                  render: (r) =>
                    editable ? (
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openDialog("shift", r)} data-testid={`shift-edit-${r.id}`}>
                          Ubah
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setDeleting({ kind: "shift", row: r })}
                          data-testid={`shift-delete-${r.id}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ) : null,
                },
              ]}
              emptyProps={{ icon: Clock, title: "Belum ada shift kerja.", description: "Tambahkan shift agar jadwal kerja dapat dibuat." }}
            />
          </TableCard>
        </TabsContent>

        {/* KALENDER */}
        <TabsContent value="calendar" className="mt-4 space-y-3">
          <SectionHeader
            title="Kalender Kerja"
            description="Libur nasional, libur perusahaan, cuti bersama, dan hari kerja pengganti."
            actions={
              <FilterSelect
                value={String(year)}
                onChange={(v) => setYear(Number(v) || new Date().getFullYear())}
                options={[0, 1, 2].map((i) => {
                  const y = new Date().getFullYear() - 1 + i;
                  return { value: String(y), label: String(y) };
                })}
                allLabel="Tahun"
                testId="calendar-filter-year"
              />
            }
          />
          {editable && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Tambah Hari Khusus</CardTitle>
                <CardDescription>Hari OFF rutin diatur pada jadwal kerja, bukan di sini.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 sm:grid-cols-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="cal-date" className="text-[13px] font-medium">
                      Tanggal <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="cal-date"
                      type="date"
                      value={calForm.calendar_date}
                      onChange={(e) => setCalForm((s) => ({ ...s, calendar_date: e.target.value }))}
                      data-testid="calendar-date-input"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-[13px] font-medium">Jenis Hari</Label>
                    <Select value={calForm.day_type} onValueChange={(v) => setCalForm((s) => ({ ...s, day_type: v }))}>
                      <SelectTrigger data-testid="calendar-day-type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(catalog?.calendar_day_types || []).map((item) => (
                          <SelectItem key={item.key} value={item.key}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="cal-name" className="text-[13px] font-medium">
                      Nama <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="cal-name"
                      value={calForm.name}
                      onChange={(e) => setCalForm((s) => ({ ...s, name: e.target.value }))}
                      placeholder="Hari Kemerdekaan RI"
                      data-testid="calendar-name-input"
                    />
                  </div>
                  <div className="flex items-end">
                    <Button onClick={addCalendarDay} disabled={savingCal} className="w-full" data-testid="calendar-add-button">
                      <Plus className="mr-2 h-4 w-4" /> Tambah
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
          <TableCard>
            <DataTable
              loading={loading}
              rows={calendarDays}
              testId="calendar-table"
              columns={[
                { key: "calendar_date", header: "Tanggal", render: (r) => dayLabel(r.calendar_date) },
                { key: "name", header: "Nama" },
                { key: "day_type_label", header: "Jenis Hari", render: (r) => r.day_type_label || r.day_type },
                {
                  key: "actions",
                  header: "",
                  render: (r) =>
                    editable ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setDeleting({ kind: "calendar", row: r })}
                        data-testid={`calendar-delete-${r.id}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    ) : null,
                },
              ]}
              emptyProps={{
                icon: CalendarDays,
                title: "Belum ada hari khusus pada tahun ini.",
                description: "Tambahkan libur nasional dan cuti bersama agar perhitungan kehadiran akurat.",
              }}
            />
          </TableCard>
        </TabsContent>

        {/* JENIS CUTI */}
        <TabsContent value="leave-types" className="mt-4 space-y-3">
          <SectionHeader
            title="Jenis Cuti / Izin / Sakit"
            description="Configurable: pengurangan saldo, lampiran wajib, setengah hari, dan kuota default."
            actions={
              editable ? (
                <Button onClick={() => openDialog("leave_type", null)} data-testid="leave-type-create-button">
                  <Plus className="mr-2 h-4 w-4" /> Tambah Jenis
                </Button>
              ) : null
            }
          />
          <TableCard>
            <DataTable
              loading={loading}
              rows={leaveTypes}
              testId="leave-types-table"
              columns={[
                {
                  key: "name",
                  header: "Jenis",
                  render: (r) => (
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-foreground">{r.name}</p>
                      <p className="text-[12px] text-muted-foreground">
                        {r.code} · {r.category_label || r.category}
                      </p>
                    </div>
                  ),
                },
                { key: "default_quota_days", header: "Kuota", align: "right" },
                { key: "deduct_balance", header: "Kurangi Saldo", render: (r) => (r.deduct_balance ? "Ya" : "Tidak") },
                { key: "is_paid", header: "Dibayar", render: (r) => (r.is_paid ? "Ya" : "Tidak"), hideOnMobile: true },
                {
                  key: "attachment_required",
                  header: "Lampiran",
                  hideOnMobile: true,
                  render: (r) => (r.attachment_required ? "Wajib" : "Opsional"),
                },
                { key: "allow_half_day", header: "1/2 Hari", hideOnMobile: true, render: (r) => (r.allow_half_day ? "Boleh" : "Tidak") },
                {
                  key: "status",
                  header: "Status",
                  render: (r) => (
                    <ToneBadge tone={r.status === "active" ? "success" : "neutral"} label={r.status === "active" ? "Aktif" : "Nonaktif"} />
                  ),
                },
                {
                  key: "actions",
                  header: "",
                  render: (r) =>
                    editable ? (
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openDialog("leave_type", r)} data-testid={`leave-type-edit-${r.id}`}>
                          Ubah
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setDeleting({ kind: "leave_type", row: r })}
                          data-testid={`leave-type-delete-${r.id}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ) : null,
                },
              ]}
              emptyProps={{ title: "Belum ada jenis cuti.", description: "Tambahkan jenis cuti agar karyawan dapat mengajukan." }}
            />
          </TableCard>
        </TabsContent>

        {/* KEBIJAKAN */}
        <TabsContent value="policies" className="mt-4 space-y-3">
          <SectionHeader
            title="Kebijakan Time Management"
            description="Berlaku untuk seluruh perusahaan aktif."
            actions={
              can("attendance", "edit") ? (
                <Button onClick={savePolicies} disabled={saving || !policies} data-testid="policies-save-button">
                  <Save className="mr-2 h-4 w-4" /> Simpan Kebijakan
                </Button>
              ) : null
            }
          />
          {policies && (
            <div className="grid gap-3 lg:grid-cols-3">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Absensi</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-1.5">
                    <Label className="text-[13px] font-medium">Kebijakan Lokasi Default</Label>
                    <Select
                      value={policies.attendance?.default_geofence_policy || ""}
                      onValueChange={(v) => setPolicy("attendance", "default_geofence_policy", v)}
                    >
                      <SelectTrigger data-testid="policy-geofence">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(catalog?.geofence_policies || []).map((item) => (
                          <SelectItem key={item.key} value={item.key}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="policy-radius" className="text-[13px] font-medium">
                      Radius Default (meter)
                    </Label>
                    <Input
                      id="policy-radius"
                      type="number"
                      value={policies.attendance?.default_radius_meter ?? ""}
                      onChange={(e) => setPolicy("attendance", "default_radius_meter", Number(e.target.value))}
                      data-testid="policy-radius"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="policy-accuracy" className="text-[13px] font-medium">
                      Batas Akurasi GPS (meter)
                    </Label>
                    <Input
                      id="policy-accuracy"
                      type="number"
                      value={policies.attendance?.gps_accuracy_max_meter ?? ""}
                      onChange={(e) => setPolicy("attendance", "gps_accuracy_max_meter", Number(e.target.value))}
                      data-testid="policy-accuracy"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      id="policy-no-schedule"
                      checked={!!policies.attendance?.allow_check_in_without_schedule}
                      onCheckedChange={(v) => setPolicy("attendance", "allow_check_in_without_schedule", v)}
                      data-testid="policy-allow-without-schedule"
                    />
                    <Label htmlFor="policy-no-schedule" className="text-[13px]">
                      Izinkan absen tanpa jadwal
                    </Label>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Lembur</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {[
                    ["minimum_minutes", "Lembur Minimal (menit)"],
                    ["rounding_interval_minutes", "Pembulatan (menit)"],
                    ["max_minutes_per_day", "Maksimal per Hari (menit)"],
                  ].map(([key, label]) => (
                    <div key={key} className="space-y-1.5">
                      <Label htmlFor={`policy-${key}`} className="text-[13px] font-medium">
                        {label}
                      </Label>
                      <Input
                        id={`policy-${key}`}
                        type="number"
                        value={policies.overtime?.[key] ?? ""}
                        onChange={(e) => setPolicy("overtime", key, Number(e.target.value))}
                        data-testid={`policy-${key}`}
                      />
                    </div>
                  ))}
                  <div className="flex items-center gap-2">
                    <Switch
                      id="policy-pre-approval"
                      checked={!!policies.overtime?.pre_approval_required}
                      onCheckedChange={(v) => setPolicy("overtime", "pre_approval_required", v)}
                      data-testid="policy-pre-approval"
                    />
                    <Label htmlFor="policy-pre-approval" className="text-[13px]">
                      Wajib persetujuan sebelum lembur
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      id="policy-retroactive"
                      checked={!!policies.overtime?.retroactive_allowed}
                      onCheckedChange={(v) => setPolicy("overtime", "retroactive_allowed", v)}
                      data-testid="policy-retroactive"
                    />
                    <Label htmlFor="policy-retroactive" className="text-[13px]">
                      Boleh diajukan setelah tanggal lembur
                    </Label>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Cuti</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="policy-backdate" className="text-[13px] font-medium">
                      Maksimal Pengajuan Mundur (hari)
                    </Label>
                    <Input
                      id="policy-backdate"
                      type="number"
                      value={policies.leave?.max_backdate_days ?? ""}
                      onChange={(e) => setPolicy("leave", "max_backdate_days", Number(e.target.value))}
                      data-testid="policy-backdate"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="policy-attachment-mb" className="text-[13px] font-medium">
                      Ukuran Lampiran Maksimal (MB)
                    </Label>
                    <Input
                      id="policy-attachment-mb"
                      type="number"
                      value={policies.leave?.attachment_max_mb ?? ""}
                      onChange={(e) => setPolicy("leave", "attachment_max_mb", Number(e.target.value))}
                      data-testid="policy-attachment-mb"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      id="policy-holiday"
                      checked={!!policies.leave?.count_holiday_as_leave}
                      onCheckedChange={(v) => setPolicy("leave", "count_holiday_as_leave", v)}
                      data-testid="policy-count-holiday"
                    />
                    <Label htmlFor="policy-holiday" className="text-[13px]">
                      Hitung hari libur sebagai cuti
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch
                      id="policy-dayoff"
                      checked={!!policies.leave?.count_day_off_as_leave}
                      onCheckedChange={(v) => setPolicy("leave", "count_day_off_as_leave", v)}
                      data-testid="policy-count-dayoff"
                    />
                    <Label htmlFor="policy-dayoff" className="text-[13px]">
                      Hitung hari OFF sebagai cuti
                    </Label>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* PERIODE */}
        <TabsContent value="periods" className="mt-4 space-y-3">
          <SectionHeader
            title="Tutup / Buka Kembali Periode"
            description="Saat periode ditutup, seluruh perubahan absensi, cuti, dan lembur pada periode itu ditolak."
          />
          {can("attendance", "approve") && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Tutup Periode</CardTitle>
                <CardDescription>Lakukan setelah rekap kehadiran diperiksa dan siap dipakai payroll.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-end gap-3">
                  <FilterSelect
                    label="Periode"
                    value={periodAction?.period_key || ""}
                    onChange={(v) => setPeriodAction(v ? { mode: "close", period_key: v } : null)}
                    options={periodOptions()}
                    allLabel="Pilih periode"
                    testId="period-select"
                  />
                  <Button
                    onClick={() => periodAction?.period_key && setPeriodAction({ ...periodAction, mode: "close" })}
                    disabled={!periodAction?.period_key}
                    data-testid="period-close-button"
                  >
                    <Lock className="mr-2 h-4 w-4" /> Tutup Periode
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
          <TableCard>
            <DataTable
              loading={loading}
              rows={periods}
              testId="periods-table"
              columns={[
                { key: "period_label", header: "Periode" },
                {
                  key: "status",
                  header: "Status",
                  render: (r) => <ToneBadge tone={r.period_status_tone} label={r.period_status_label} />,
                },
                {
                  key: "closed",
                  header: "Ditutup Oleh",
                  hideOnMobile: true,
                  render: (r) => (r.closed_at ? `${r.closed_by_name || "-"} · ${formatDateTime(r.closed_at)}` : "-"),
                },
                {
                  key: "reopened",
                  header: "Dibuka Kembali",
                  hideOnMobile: true,
                  render: (r) => (r.reopened_at ? `${r.reopened_by_name || "-"} · ${formatDateTime(r.reopened_at)}` : "-"),
                },
                {
                  key: "actions",
                  header: "",
                  render: (r) =>
                    can("attendance", "approve") ? (
                      r.period_status === "closed" ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setPeriodAction({ mode: "reopen", period_key: r.period_key })}
                          data-testid={`period-reopen-${r.period_key}`}
                        >
                          <LockOpen className="mr-1.5 h-3.5 w-3.5" /> Buka Kembali
                        </Button>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setPeriodAction({ mode: "close", period_key: r.period_key })}
                          data-testid={`period-close-${r.period_key}`}
                        >
                          <Lock className="mr-1.5 h-3.5 w-3.5" /> Tutup
                        </Button>
                      )
                    ) : null,
                },
              ]}
              emptyProps={{
                title: "Belum ada periode yang pernah ditutup.",
                description: "Semua periode berstatus terbuka sehingga data masih dapat diubah.",
              }}
            />
          </TableCard>
        </TabsContent>
      </Tabs>

      {/* Dialog shift / jenis cuti */}
      <FormDialog
        open={!!dialog}
        onOpenChange={(open) => !open && setDialog(null)}
        title={
          dialog?.kind === "shift"
            ? dialog?.row
              ? "Ubah Shift Kerja"
              : "Tambah Shift Kerja"
            : dialog?.row
            ? "Ubah Jenis Cuti"
            : "Tambah Jenis Cuti"
        }
        description={
          dialog?.kind === "shift"
            ? "Jam pulang lebih kecil dari jam masuk otomatis dianggap shift lintas hari."
            : "Pengaturan ini menentukan validasi saat karyawan mengajukan."
        }
        fields={dialog?.kind === "shift" ? SHIFT_FIELDS : LEAVE_TYPE_FIELDS(asOptions(catalog?.leave_categories))}
        values={values}
        onChange={(name, value) => setValues((s) => ({ ...s, [name]: value }))}
        onSubmit={save}
        submitting={saving}
        wide
      />

      {/* Konfirmasi hapus */}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Hapus data ini?"
        description={`${deleting?.row?.name || ""} akan dihapus. Data yang sudah dipakai transaksi tidak dapat dihapus.`}
        confirmLabel="Hapus"
        destructive
        loading={removing}
        onConfirm={remove}
      />

      {/* Tutup / buka kembali periode */}
      <Dialog
        open={!!periodAction?.mode && !!periodAction?.period_key}
        onOpenChange={(open) => {
          if (!open) {
            setPeriodAction(null);
            setPeriodReason("");
          }
        }}
      >
        <DialogContent className="bg-card sm:max-w-lg" data-testid="period-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">
              {periodAction?.mode === "close" ? "Tutup Periode" : "Buka Kembali Periode"}
            </DialogTitle>
            <DialogDescription className="leading-relaxed">
              {periodAction?.mode === "close"
                ? `Semua perubahan absensi, cuti, dan lembur pada periode ${periodAction?.period_key} akan ditolak setelah ditutup.`
                : `Periode ${periodAction?.period_key} akan dibuka kembali. Alasan wajib diisi dan tercatat pada audit log.`}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="period-reason" className="text-[13px] font-medium">
              {periodAction?.mode === "close" ? "Catatan" : "Alasan"}
              {periodAction?.mode === "reopen" && <span className="ml-0.5 text-destructive">*</span>}
            </Label>
            <Textarea
              id="period-reason"
              rows={3}
              value={periodReason}
              onChange={(e) => setPeriodReason(e.target.value)}
              placeholder={
                periodAction?.mode === "close"
                  ? "Contoh: rekap kehadiran September sudah diverifikasi."
                  : "Contoh: ada koreksi absensi yang disetujui setelah periode ditutup."
              }
              data-testid="period-reason"
            />
          </div>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setPeriodAction(null);
                setPeriodReason("");
              }}
              disabled={periodBusy}
              data-testid="period-cancel"
            >
              Batal
            </Button>
            <Button onClick={runPeriodAction} disabled={periodBusy} data-testid="period-confirm">
              {periodAction?.mode === "close" ? "Tutup Periode" : "Buka Kembali"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default TimeSettingsPage;
