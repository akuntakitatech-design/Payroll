import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, History, MapPin, MapPinOff, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { todayISO, CATEGORY_LABELS } from "@/lib/employeeStatus";
import FormDialog from "@/components/common/FormDialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoRow, SectionCard } from "@/components/employees/ProfileSections";

/*
 * Upgrade 01D - Penempatan Saat Ini + Riwayat Penempatan (Profile 360).
 * Tetapkan / Pindah / Akhiri Penempatan -> API /employees/{id}/assignments (tenant-safe, transaksional).
 * Standby BUKAN jenis penempatan: opsi ubah Status Karyawan saat mengakhiri memakai flow 01B di backend.
 */
const SOURCE_LABELS = {
  LEGACY_BASELINE: "Data lama (migrasi)",
  MANUAL: "Ditetapkan manual",
  TRANSFER: "Pindah penempatan",
  EMPLOYEE_CREATE: "Saat data karyawan dibuat",
  IMPORT: "Impor Excel",
  RECRUITMENT: "Konversi rekrutmen",
};

const StatusPill = ({ value, testId }) =>
  value === "ACTIVE" ? (
    <Badge variant="outline" className="border-success-border bg-success-soft text-success" data-testid={testId}>Aktif</Badge>
  ) : (
    <Badge variant="outline" className="border-border bg-muted text-muted-foreground" data-testid={testId}>Berakhir</Badge>
  );

const placementFields = (catalog, { includeStart = true } = {}) => {
  const opt = (key) => (catalog?.[key] || []).map((o) => ({ value: o.id, label: o.code ? `${o.name} (${o.code})` : o.name }));
  return [
    { name: "project_id", label: "Project", type: "select", options: opt("projects") },
    { name: "work_location_id", label: "Site / Lokasi Kerja", type: "select", options: opt("work_locations") },
    { name: "branch_id", label: "Cabang", type: "select", options: opt("branches") },
    { name: "department_id", label: "Departemen", type: "select", options: opt("departments") },
    { name: "division_id", label: "Divisi", type: "select", options: opt("divisions") },
    { name: "position_id", label: "Jabatan", type: "select", options: opt("positions") },
    { name: "cost_center_id", label: "Cost Center", type: "select", options: opt("cost_centers"), hint: "Opsional" },
    ...(includeStart ? [{ name: "start_date", label: "Tanggal Mulai Penempatan", type: "date", required: true, hint: "Hari ini atau tanggal lampau." }] : []),
    { name: "reason", label: "Alasan", required: true, colSpan: 2, placeholder: "mis. Mobilisasi ke project baru" },
    { name: "notes", label: "Catatan", type: "textarea", colSpan: 2 },
  ];
};

const PLACEMENT_KEYS = ["project_id", "work_location_id", "branch_id", "department_id", "division_id", "position_id", "cost_center_id"];

export const AssignmentTab = ({ employee, company, catalog, canEdit, canChangeStatus, onChanged }) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [dialog, setDialog] = useState(null); // assign | transfer | end
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const [statuses, setStatuses] = useState([]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.get(`/employees/${employee.id}/assignments`);
      setData(res.data);
    } catch (err) {
      setError(errorMessage(err, "Riwayat penempatan gagal dimuat."));
    }
  }, [employee.id]);

  useEffect(() => {
    load();
  }, [load, employee.updated_at]);

  const current = data?.current || null;
  const items = data?.items || [];
  const archived = employee.status === "archived";

  const open = (mode) => {
    const today = todayISO();
    const base = {};
    // prefill dari data organisasi karyawan saat ini (HR cukup mengubah yang berpindah)
    PLACEMENT_KEYS.forEach((k) => (base[k] = employee[k] || ""));
    if (mode === "end") setValues({ end_date: today, reason: "", notes: "", change_status_id: "" });
    else setValues({ ...base, start_date: today, reason: "", notes: "" });
    setErrors({});
    setDialog(mode);
    if (mode === "end" && canChangeStatus) {
      api
        .get("/employee-statuses", { params: { active: true } })
        .then((res) => setStatuses(res.data.items || []))
        .catch(() => setStatuses([]));
    }
  };

  const onChange = (name, value) => {
    setValues((p) => ({ ...p, [name]: value }));
    setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
  };

  const validate = () => {
    const e = {};
    const today = todayISO();
    const dateKey = dialog === "end" ? "end_date" : "start_date";
    if (!values[dateKey]) e[dateKey] = "Tanggal wajib diisi.";
    else if (values[dateKey] > today) e[dateKey] = "Tanggal tidak boleh melebihi hari ini.";
    else if (current?.start_date && values[dateKey] < current.start_date && dialog !== "assign")
      e[dateKey] = `Tidak boleh sebelum mulai penempatan saat ini (${formatDate(current.start_date)}).`;
    if ((values.reason || "").trim().length < 3) e.reason = "Alasan wajib diisi (minimal 3 karakter).";
    if (dialog !== "end" && !values.project_id && !values.work_location_id) e.project_id = "Pilih minimal Project atau Site.";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = async () => {
    if (!validate()) return;
    setSaving(true);
    try {
      let res;
      if (dialog === "end") {
        res = await api.post(`/employees/${employee.id}/assignments/end`, {
          end_date: values.end_date,
          reason: values.reason.trim(),
          notes: values.notes || null,
          change_status_id: values.change_status_id || null,
        });
        if (res.data.status_change_error) toast.warning(res.data.message);
        else toast.success(res.data.status_change ? "Penempatan diakhiri dan status karyawan diperbarui." : "Penempatan berhasil diakhiri.");
      } else {
        const payload = { start_date: values.start_date, reason: values.reason.trim(), notes: values.notes || null };
        PLACEMENT_KEYS.forEach((k) => (payload[k] = values[k] || null));
        res = await api.post(`/employees/${employee.id}/assignments${dialog === "transfer" ? "/transfer" : ""}`, payload);
        toast.success(res.data.message);
      }
      setDialog(null);
      await load();
      onChanged?.();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Penempatan tidak dapat disimpan.") });
    } finally {
      setSaving(false);
    }
  };

  const endFields = useMemo(() => {
    const f = [
      { name: "end_date", label: "Tanggal Akhir Penempatan", type: "date", required: true, hint: "Hari ini atau tanggal lampau." },
      { name: "reason", label: "Alasan", required: true, placeholder: "mis. Project selesai" },
      { name: "notes", label: "Catatan", type: "textarea", colSpan: 2 },
    ];
    if (canChangeStatus) {
      const opts = statuses
        .filter((s) => s.id !== employee.current_employee_status_id)
        .sort((a, b) => (a.system_category === "STANDBY" ? -1 : 0) - (b.system_category === "STANDBY" ? -1 : 0))
        .map((s) => ({ value: s.id, label: `${s.name} (${CATEGORY_LABELS[s.system_category] || s.system_category})` }));
      f.push({
        name: "change_status_id",
        label: "Status Karyawan setelah penempatan berakhir",
        type: "select",
        colSpan: 2,
        emptyLabel: `Tetap: ${employee.current_employee_status_name || "status saat ini"}`,
        options: opts,
        hint: "Opsional. Perubahan status memakai alur 'Ubah Status' (riwayat + audit tercatat). Tidak ada perubahan otomatis ke Standby.",
      });
    }
    return f;
  }, [canChangeStatus, statuses, employee.current_employee_status_id, employee.current_employee_status_name]);

  if (error) {
    return (
      <div className="rounded-lg border border-danger-border bg-danger-soft p-4 text-sm text-danger" role="alert" data-testid="assignment-error">
        {error}
        <Button size="sm" variant="outline" className="ml-3" onClick={load} data-testid="assignment-retry-button">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Coba lagi
        </Button>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="space-y-3" data-testid="assignment-loading">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const actions = canEdit && !archived && (
    <div className="flex flex-wrap gap-2" data-testid="assignment-actions">
      {!current ? (
        <Button size="sm" onClick={() => open("assign")} data-testid="assignment-assign-button">
          <Plus className="mr-1.5 h-3.5 w-3.5" /> Tetapkan Penempatan
        </Button>
      ) : (
        <>
          <Button size="sm" onClick={() => open("transfer")} data-testid="assignment-transfer-button">
            <ArrowRightLeft className="mr-1.5 h-3.5 w-3.5" /> Pindah Penempatan
          </Button>
          <Button size="sm" variant="outline" onClick={() => open("end")} data-testid="assignment-end-button">
            <MapPinOff className="mr-1.5 h-3.5 w-3.5" /> Akhiri Penempatan
          </Button>
        </>
      )}
    </div>
  );

  return (
    <div className="space-y-4" data-testid="assignment-tab">
      <SectionCard title="Penempatan Saat Ini" icon={MapPin} testId="placement-card">
        {actions && <div className="border-b border-border/60 py-3">{actions}</div>}
        {current ? (
          <>
            <InfoRow label="Project" value={current.project_name} testId="placement-project" />
            <InfoRow label="Site / Lokasi Kerja" value={current.work_location_name} testId="placement-location" />
            <InfoRow label="Perusahaan" value={company?.name || current.company_name} testId="placement-company" />
            <InfoRow label="Cabang" value={current.branch_name} testId="placement-branch" />
            <InfoRow label="Departemen" value={current.department_name} testId="placement-department" />
            <InfoRow label="Divisi" value={current.division_name} testId="placement-division" />
            <InfoRow label="Jabatan" value={current.position_name || employee.job_title} testId="placement-position" />
            <InfoRow label="Cost Center" value={current.cost_center_name} testId="placement-cost-center" />
            <InfoRow
              label="Mulai Penempatan"
              value={current.start_date ? formatDate(current.start_date) : "Tidak diketahui (data lama)"}
              testId="placement-start-date"
            />
            <InfoRow label="Sumber" value={SOURCE_LABELS[current.source] || current.source} testId="placement-source" />
          </>
        ) : (
          <div className="flex flex-col items-start gap-1 py-6" data-testid="placement-empty">
            <p className="text-sm font-medium">Belum ada penempatan aktif</p>
            <p className="text-[13px] text-muted-foreground">
              {items.length
                ? "Penempatan terakhir sudah berakhir. Riwayat tetap tersimpan di bawah."
                : "Karyawan ini belum pernah ditempatkan ke project / site."}
              {canEdit && !archived && " Gunakan 'Tetapkan Penempatan' untuk menempatkan karyawan."}
            </p>
          </div>
        )}
      </SectionCard>

      <SectionCard title={`Riwayat Penempatan (${items.length})`} icon={History} testId="assignment-history-card">
        {items.length === 0 ? (
          <p className="py-6 text-[13px] text-muted-foreground" data-testid="assignment-history-empty">Belum ada riwayat penempatan.</p>
        ) : (
          <>
            {/* desktop / tablet */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-[13px]" data-testid="assignment-history-table">
                <thead>
                  <tr className="border-b border-border text-left text-[12px] text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Project</th>
                    <th className="py-2 pr-3 font-medium">Site</th>
                    <th className="py-2 pr-3 font-medium">Jabatan</th>
                    <th className="py-2 pr-3 font-medium">Mulai</th>
                    <th className="py-2 pr-3 font-medium">Berakhir</th>
                    <th className="py-2 pr-3 font-medium">Alasan</th>
                    <th className="py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r) => (
                    <tr key={r.id} className="border-b border-border/60 align-top last:border-0" data-testid={`assignment-row-${r.id}`}>
                      <td className="py-2 pr-3">{r.project_name || "-"}</td>
                      <td className="py-2 pr-3">{r.work_location_name || "-"}</td>
                      <td className="py-2 pr-3">{r.position_name || "-"}</td>
                      <td className="whitespace-nowrap py-2 pr-3">{r.start_date ? formatDate(r.start_date) : "Tidak diketahui"}</td>
                      <td className="whitespace-nowrap py-2 pr-3">{r.end_date ? formatDate(r.end_date) : "-"}</td>
                      <td className="max-w-[16rem] py-2 pr-3 text-muted-foreground">
                        <span className="line-clamp-2">{r.end_reason || r.reason || "-"}</span>
                      </td>
                      <td className="py-2"><StatusPill value={r.assignment_status} testId={`assignment-status-${r.id}`} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* mobile */}
            <ul className="divide-y divide-border/60 md:hidden" data-testid="assignment-history-list">
              {items.map((r) => (
                <li key={r.id} className="space-y-1 py-3" data-testid={`assignment-item-${r.id}`}>
                  <div className="flex items-start justify-between gap-2">
                    <p className="min-w-0 break-words text-[13px] font-medium">
                      {r.project_name || "-"}{r.work_location_name ? ` · ${r.work_location_name}` : ""}
                    </p>
                    <StatusPill value={r.assignment_status} />
                  </div>
                  <p className="text-[12px] text-muted-foreground">{r.position_name || "-"}</p>
                  <p className="text-[12px] text-muted-foreground">
                    {r.start_date ? formatDate(r.start_date) : "Tidak diketahui"} – {r.end_date ? formatDate(r.end_date) : "sekarang"}
                  </p>
                  {(r.end_reason || r.reason) && <p className="break-words text-[12px] text-muted-foreground">{r.end_reason || r.reason}</p>}
                </li>
              ))}
            </ul>
          </>
        )}
      </SectionCard>

      <FormDialog
        open={!!dialog}
        onOpenChange={(v) => !v && !saving && setDialog(null)}
        title={dialog === "assign" ? "Tetapkan Penempatan" : dialog === "transfer" ? "Pindah Penempatan" : "Akhiri Penempatan"}
        description={
          dialog === "transfer"
            ? `Penempatan saat ini (${current?.project_name || current?.work_location_name || "-"}) akan diakhiri sehari sebelum tanggal mulai baru, lalu penempatan baru menjadi aktif. Riwayat tetap tersimpan.`
            : dialog === "end"
            ? "Setelah diakhiri, karyawan tidak memiliki penempatan aktif dan project di data karyawan dikosongkan. Riwayat tetap tersimpan."
            : "Pilih project / site dan data organisasi. Nilai awal diambil dari data karyawan saat ini."
        }
        fields={dialog === "end" ? endFields : placementFields(catalog)}
        values={values}
        errors={errors}
        onChange={onChange}
        onSubmit={submit}
        submitting={saving}
        submitLabel={dialog === "end" ? "Akhiri Penempatan" : dialog === "transfer" ? "Simpan Pindah Penempatan" : "Tetapkan Penempatan"}
        wide
      />
    </div>
  );
};

export default AssignmentTab;
