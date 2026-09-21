import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { CalendarRange, Plus, Trash2 } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, FilterSelect, TableCard } from "@/components/common/DataTable";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ToneBadge from "@/components/time/ToneBadge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
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
import { useAttendanceScope } from "@/lib/attendanceScope";
import { asOptions, currentPeriodKey, dayLabel, monthBounds, periodOptions, useTimeCatalog } from "@/lib/timeCatalog";

const WEEKDAYS = [
  { value: 1, label: "Sen" },
  { value: 2, label: "Sel" },
  { value: 3, label: "Rab" },
  { value: 4, label: "Kam" },
  { value: 5, label: "Jum" },
  { value: 6, label: "Sab" },
  { value: 7, label: "Min" },
];

const SchedulesPage = () => {
  const { can: canRaw } = useAuth();
  const { hrScope } = useAttendanceScope();
  // Karyawan self-service hanya membaca jadwalnya sendiri (tidak membuat/menghapus jadwal).
  const can = (resource, action) => (action === "view" ? canRaw(resource, action) : hrScope && canRaw(resource, action));
  const { catalog } = useTimeCatalog();
  const [period, setPeriod] = useState(currentPeriodKey());
  const [shiftFilter, setShiftFilter] = useState("");
  const [employeeFilter, setEmployeeFilter] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [employees, setEmployees] = useState([]);
  const [deleting, setDeleting] = useState(null);
  const [removing, setRemoving] = useState(false);

  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    employee_ids: [],
    date_from: "",
    date_to: "",
    shift_id: "",
    work_location_id: "",
    is_day_off: false,
    weekdays: [1, 2, 3, 4, 5],
    overwrite_existing: false,
    notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    const { dateFrom, dateTo } = monthBounds(period);
    try {
      const { data } = await api.get("/schedules", {
        params: {
          date_from: dateFrom,
          date_to: dateTo,
          shift_id: shiftFilter || undefined,
          employee_id: employeeFilter || undefined,
        },
      });
      setRows(data?.items || []);
    } catch (error) {
      toast.error(errorMessage(error, "Jadwal kerja tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [period, shiftFilter, employeeFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .get("/employees", { params: { limit: 200, status: "active" } })
      .then(({ data }) => setEmployees(data?.items || []))
      .catch(() => setEmployees([]));
  }, []);

  const openDialog = () => {
    const { dateFrom, dateTo } = monthBounds(period);
    setForm({
      employee_ids: [],
      date_from: dateFrom,
      date_to: dateTo,
      shift_id: "",
      work_location_id: "",
      is_day_off: false,
      weekdays: [1, 2, 3, 4, 5],
      overwrite_existing: false,
      notes: "",
    });
    setOpen(true);
  };

  const submit = async () => {
    if (!form.employee_ids.length) {
      toast.error("Pilih minimal satu karyawan.");
      return;
    }
    if (!form.date_from || !form.date_to) {
      toast.error("Tanggal Mulai dan Tanggal Selesai wajib diisi.");
      return;
    }
    if (!form.is_day_off && !form.shift_id) {
      toast.error("Shift wajib dipilih kecuali jadwal ditandai OFF.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/schedules/bulk", {
        employee_ids: form.employee_ids,
        date_from: form.date_from,
        date_to: form.date_to,
        shift_id: form.is_day_off ? null : form.shift_id,
        work_location_id: form.work_location_id || null,
        is_day_off: form.is_day_off,
        weekdays: form.weekdays.length ? form.weekdays : null,
        overwrite_existing: form.overwrite_existing,
        notes: form.notes || null,
      });
      toast.success(data?.message || "Jadwal kerja berhasil dibuat.");
      setOpen(false);
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Jadwal kerja tidak dapat dibuat."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  const removeSchedule = async () => {
    if (!deleting) return;
    setRemoving(true);
    try {
      await api.delete(`/schedules/${deleting.id}`);
      toast.success("Jadwal berhasil dihapus.");
      setDeleting(null);
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Jadwal tidak dapat dihapus."), { duration: 9000 });
    } finally {
      setRemoving(false);
    }
  };

  const shiftOptions = useMemo(
    () => (catalog?.shifts || []).filter((s) => !s.is_day_off).map((s) => ({ value: s.id, label: `${s.name} (${s.code})` })),
    [catalog]
  );

  const columns = [
    {
      key: "employee",
      header: "Karyawan",
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-foreground">{row.employee_name}</p>
          <p className="text-[12px] text-muted-foreground">{row.employee_number || "-"}</p>
        </div>
      ),
    },
    { key: "work_date", header: "Tanggal", render: (row) => dayLabel(row.work_date) },
    {
      key: "shift",
      header: "Shift",
      render: (row) =>
        row.is_day_off ? (
          <ToneBadge tone="neutral" label="OFF" />
        ) : (
          <span className="text-[13px]">
            {row.shift_name || "-"} · {row.shift_window}
            {row.is_overnight ? " (lintas hari)" : ""}
          </span>
        ),
    },
    { key: "work_location_name", header: "Lokasi Kerja", hideOnMobile: true, render: (row) => row.work_location_name || "-" },
    { key: "day_type_label", header: "Jenis Hari", hideOnMobile: true },
    { key: "source_label", header: "Sumber", hideOnMobile: true },
    {
      key: "actions",
      header: "",
      render: (row) =>
        can("attendance", "delete") ? (
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={() => setDeleting(row)}
            data-testid={`schedule-delete-${row.id}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        ) : null,
    },
  ];

  return (
    <PageBody>
      <SectionHeader
        title="Jadwal Kerja"
        description="Tetapkan shift, lokasi kerja, dan hari OFF per karyawan per tanggal."
        actions={
          can("attendance", "create") ? (
            <Button onClick={openDialog} data-testid="schedule-create-button">
              <Plus className="mr-2 h-4 w-4" /> Buat Jadwal
            </Button>
          ) : null
        }
      />

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-3">
        <FilterSelect
          label="Periode"
          value={period}
          onChange={(v) => setPeriod(v || currentPeriodKey())}
          options={periodOptions()}
          allLabel="Periode"
          testId="schedule-filter-period"
        />
        <FilterSelect
          label="Shift"
          value={shiftFilter}
          onChange={setShiftFilter}
          options={shiftOptions}
          testId="schedule-filter-shift"
        />
        <FilterSelect
          label="Karyawan"
          value={employeeFilter}
          onChange={setEmployeeFilter}
          options={employees.map((e) => ({ value: e.id, label: e.full_name }))}
          testId="schedule-filter-employee"
        />
      </div>

      <TableCard>
        <DataTable
          columns={columns}
          rows={rows}
          loading={loading}
          testId="schedules-table"
          emptyProps={{
            icon: CalendarRange,
            title: "Belum ada jadwal kerja pada periode ini.",
            description: "Buat jadwal massal, atau impor jadwal dari Excel pada tab Impor Excel.",
            actionLabel: can("attendance", "create") ? "Buat Jadwal" : undefined,
            onAction: can("attendance", "create") ? openDialog : undefined,
          }}
        />
      </TableCard>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-2xl" data-testid="schedule-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Buat Jadwal Kerja Massal</DialogTitle>
            <DialogDescription className="leading-relaxed">
              Jadwal menjadi dasar perhitungan keterlambatan, pulang cepat, dan lembur.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="schedule-from" className="text-[13px] font-medium">
                  Tanggal Mulai <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="schedule-from"
                  type="date"
                  value={form.date_from}
                  onChange={(e) => setForm((s) => ({ ...s, date_from: e.target.value }))}
                  data-testid="schedule-date-from"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="schedule-to" className="text-[13px] font-medium">
                  Tanggal Selesai <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="schedule-to"
                  type="date"
                  value={form.date_to}
                  onChange={(e) => setForm((s) => ({ ...s, date_to: e.target.value }))}
                  data-testid="schedule-date-to"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-[13px] font-medium">Hari Kerja</Label>
              <div className="flex flex-wrap gap-2">
                {WEEKDAYS.map((day) => {
                  const active = form.weekdays.includes(day.value);
                  return (
                    <Button
                      key={day.value}
                      type="button"
                      size="sm"
                      variant={active ? "default" : "outline"}
                      onClick={() =>
                        setForm((s) => ({
                          ...s,
                          weekdays: active
                            ? s.weekdays.filter((w) => w !== day.value)
                            : [...s.weekdays, day.value].sort(),
                        }))
                      }
                      data-testid={`schedule-weekday-${day.value}`}
                    >
                      {day.label}
                    </Button>
                  );
                })}
              </div>
              <p className="text-[12px] text-muted-foreground">
                Kosongkan semua pilihan untuk menerapkan ke seluruh tanggal pada rentang.
              </p>
            </div>

            <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2">
              <Switch
                id="schedule-off"
                checked={form.is_day_off}
                onCheckedChange={(v) => setForm((s) => ({ ...s, is_day_off: v }))}
                data-testid="schedule-is-day-off"
              />
              <Label htmlFor="schedule-off" className="text-[13px]">
                Tandai sebagai hari OFF (tanpa shift)
              </Label>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label className="text-[13px] font-medium">
                  Shift {!form.is_day_off && <span className="text-destructive">*</span>}
                </Label>
                <Select
                  value={form.shift_id}
                  onValueChange={(v) => setForm((s) => ({ ...s, shift_id: v }))}
                  disabled={form.is_day_off}
                >
                  <SelectTrigger data-testid="schedule-shift">
                    <SelectValue placeholder="Pilih shift…" />
                  </SelectTrigger>
                  <SelectContent>
                    {shiftOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-[13px] font-medium">Lokasi Kerja</Label>
                <Select
                  value={form.work_location_id}
                  onValueChange={(v) => setForm((s) => ({ ...s, work_location_id: v }))}
                >
                  <SelectTrigger data-testid="schedule-location">
                    <SelectValue placeholder="Ikuti lokasi karyawan" />
                  </SelectTrigger>
                  <SelectContent>
                    {(catalog?.work_locations || []).map((l) => (
                      <SelectItem key={l.id} value={l.id}>
                        {l.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-[13px] font-medium">
                Karyawan <span className="text-destructive">*</span>
              </Label>
              <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                <span className="text-[12px] text-muted-foreground" data-testid="schedule-selected-count">
                  {form.employee_ids.length} karyawan dipilih
                </span>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setForm((s) => ({ ...s, employee_ids: employees.map((e) => e.id) }))}
                    data-testid="schedule-select-all"
                  >
                    Pilih semua
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setForm((s) => ({ ...s, employee_ids: [] }))}
                    data-testid="schedule-clear-all"
                  >
                    Kosongkan
                  </Button>
                </div>
              </div>
              <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-border p-2">
                {employees.map((e) => (
                  <label
                    key={e.id}
                    className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-[13px] hover:bg-accent"
                  >
                    <Checkbox
                      checked={form.employee_ids.includes(e.id)}
                      onCheckedChange={(v) =>
                        setForm((s) => ({
                          ...s,
                          employee_ids: v
                            ? [...s.employee_ids, e.id]
                            : s.employee_ids.filter((id) => id !== e.id),
                        }))
                      }
                      data-testid={`schedule-employee-${e.id}`}
                    />
                    <span className="min-w-0 truncate">
                      {e.full_name} <span className="text-muted-foreground">({e.employee_number})</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Switch
                id="schedule-overwrite"
                checked={form.overwrite_existing}
                onCheckedChange={(v) => setForm((s) => ({ ...s, overwrite_existing: v }))}
                data-testid="schedule-overwrite"
              />
              <Label htmlFor="schedule-overwrite" className="text-[13px]">
                Perbarui jadwal yang sudah ada
              </Label>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="schedule-notes" className="text-[13px] font-medium">
                Catatan
              </Label>
              <Textarea
                id="schedule-notes"
                rows={2}
                value={form.notes}
                onChange={(e) => setForm((s) => ({ ...s, notes: e.target.value }))}
                data-testid="schedule-notes"
              />
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={saving} data-testid="schedule-cancel">
              Batal
            </Button>
            <Button onClick={submit} disabled={saving} data-testid="schedule-submit">
              Simpan Jadwal
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Hapus jadwal kerja?"
        description={`Jadwal ${deleting?.employee_name || ""} pada ${dayLabel(deleting?.work_date)} akan dihapus.`}
        confirmLabel="Hapus"
        destructive
        loading={removing}
        onConfirm={removeSchedule}
      />
    </PageBody>
  );
};

export default SchedulesPage;
