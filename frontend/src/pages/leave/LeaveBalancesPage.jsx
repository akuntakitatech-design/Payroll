import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { BookOpen, Scale, Wallet } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import { DataTable, FilterSelect, TableCard } from "@/components/common/DataTable";
import ToneBadge from "@/components/time/ToneBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { dayLabel } from "@/lib/timeCatalog";
import { formatDateTime } from "@/lib/format";

const LeaveBalancesPage = () => {
  const { can } = useAuth();
  const year = new Date().getFullYear();
  const [selectedYear, setSelectedYear] = useState(String(year));
  const [data, setData] = useState({ items: [], leave_types: [] });
  const [loading, setLoading] = useState(true);
  const [ledger, setLedger] = useState(null); // { employee, rows }
  const [adjustRow, setAdjustRow] = useState(null);
  const [adjust, setAdjust] = useState({ days: "", reason: "" });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get("/leave/balances", { params: { year: Number(selectedYear) } });
      setData(res);
    } catch (error) {
      toast.error(errorMessage(error, "Saldo cuti tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, [selectedYear]);

  useEffect(() => {
    load();
  }, [load]);

  const openLedger = async (row) => {
    try {
      const { data: res } = await api.get("/leave/ledger", {
        params: { employee_id: row.employee_id, leave_type_id: row.leave_type_id, year: Number(selectedYear) },
      });
      setLedger({ row, rows: res?.items || [] });
    } catch (error) {
      toast.error(errorMessage(error, "Buku besar saldo tidak dapat dimuat."));
    }
  };

  const submitAdjust = async () => {
    const days = Number(adjust.days);
    if (!adjust.days || Number.isNaN(days) || days === 0) {
      toast.error("Jumlah hari penyesuaian wajib diisi dan tidak boleh 0.");
      return;
    }
    if (adjust.reason.trim().length < 3) {
      toast.error("Alasan penyesuaian wajib diisi minimal 3 karakter.");
      return;
    }
    setSaving(true);
    try {
      await api.post("/leave/balances/adjust", {
        employee_id: adjustRow.employee_id,
        leave_type_id: adjustRow.leave_type_id,
        year: Number(selectedYear),
        days,
        reason: adjust.reason.trim(),
      });
      toast.success("Penyesuaian saldo tercatat pada buku besar.");
      setAdjustRow(null);
      setAdjust({ days: "", reason: "" });
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Penyesuaian saldo tidak dapat disimpan."), { duration: 9000 });
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageBody>
      <SectionHeader
        title="Saldo Cuti"
        description="Setiap pergerakan saldo tercatat pada buku besar sehingga dapat ditelusuri."
        actions={
          <FilterSelect
            value={selectedYear}
            onChange={(v) => setSelectedYear(v || String(year))}
            options={[0, 1, 2].map((i) => {
              const y = year - 1 + i;
              return { value: String(y), label: String(y) };
            })}
            allLabel="Tahun"
            testId="balance-filter-year"
          />
        }
      />

      <TableCard>
        <DataTable
          loading={loading}
          rows={data.items || []}
          rowKey={(r) => `${r.employee_id}-${r.leave_type_id}`}
          testId="balances-table"
          columns={[
            {
              key: "employee",
              header: "Karyawan",
              render: (r) => (
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-foreground">{r.employee_name}</p>
                  <p className="text-[12px] text-muted-foreground">
                    {r.employee_number} · {r.leave_type_name}
                  </p>
                </div>
              ),
            },
            { key: "entitlement_days", header: "Hak", align: "right" },
            { key: "carry_forward_days", header: "Sisa Tahun Lalu", align: "right", hideOnMobile: true },
            { key: "adjustment_days", header: "Penyesuaian", align: "right", hideOnMobile: true },
            { key: "used_days", header: "Terpakai", align: "right" },
            { key: "pending_days", header: "Menunggu", align: "right" },
            {
              key: "available_days",
              header: "Tersisa",
              align: "right",
              render: (r) => (
                <ToneBadge
                  tone={r.has_problem ? "danger" : "success"}
                  label={String(r.available_days)}
                  testId={`balance-available-${r.employee_id}-${r.leave_type_id}`}
                />
              ),
            },
            {
              key: "actions",
              header: "",
              render: (r) => (
                <div className="flex justify-end gap-1">
                  <Button variant="ghost" size="sm" onClick={() => openLedger(r)} data-testid={`ledger-open-${r.employee_id}`}>
                    <BookOpen className="h-3.5 w-3.5" />
                  </Button>
                  {can("leave", "edit") && (
                    <Button variant="ghost" size="sm" onClick={() => setAdjustRow(r)} data-testid={`balance-adjust-${r.employee_id}`}>
                      <Scale className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              ),
            },
          ]}
          emptyProps={{
            icon: Wallet,
            title: "Belum ada saldo cuti pada tahun ini.",
            description: "Pastikan jenis cuti dengan kuota sudah dibuat pada tab Pengaturan modul Absensi.",
          }}
        />
      </TableCard>

      {/* Buku besar */}
      <Dialog open={!!ledger} onOpenChange={(o) => !o && setLedger(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto bg-card sm:max-w-2xl" data-testid="ledger-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">
              Buku Besar Saldo · {ledger?.row?.employee_name}
            </DialogTitle>
            <DialogDescription>
              {ledger?.row?.leave_type_name} · tahun {selectedYear}
            </DialogDescription>
          </DialogHeader>
          <TableCard>
            <DataTable
              rows={ledger?.rows || []}
              testId="ledger-table"
              columns={[
                { key: "movement_label", header: "Pergerakan" },
                { key: "days", header: "Hari", align: "right" },
                { key: "effective_date", header: "Berlaku", render: (r) => dayLabel(r.effective_date) },
                { key: "notes", header: "Catatan" },
                { key: "created_at", header: "Dicatat", render: (r) => formatDateTime(r.created_at), hideOnMobile: true },
              ]}
              emptyProps={{ title: "Belum ada pergerakan saldo." }}
            />
          </TableCard>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLedger(null)}>
              Tutup
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Penyesuaian saldo */}
      <Dialog open={!!adjustRow} onOpenChange={(o) => !o && setAdjustRow(null)}>
        <DialogContent className="bg-card sm:max-w-lg" data-testid="adjust-dialog">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">Penyesuaian Saldo Cuti</DialogTitle>
            <DialogDescription className="leading-relaxed">
              {adjustRow?.employee_name} · {adjustRow?.leave_type_name}. Gunakan nilai negatif untuk mengurangi saldo.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="adjust-days" className="text-[13px] font-medium">
                Jumlah Hari <span className="text-destructive">*</span>
              </Label>
              <Input
                id="adjust-days"
                type="number"
                step="0.5"
                value={adjust.days}
                onChange={(e) => setAdjust((s) => ({ ...s, days: e.target.value }))}
                data-testid="adjust-days"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="adjust-reason" className="text-[13px] font-medium">
                Alasan <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="adjust-reason"
                rows={3}
                value={adjust.reason}
                onChange={(e) => setAdjust((s) => ({ ...s, reason: e.target.value }))}
                placeholder="Contoh: sisa cuti tahun lalu dialihkan sesuai kebijakan."
                data-testid="adjust-reason"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setAdjustRow(null)} disabled={saving}>
              Batal
            </Button>
            <Button onClick={submitAdjust} disabled={saving} data-testid="adjust-submit">
              Simpan Penyesuaian
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
};

export default LeaveBalancesPage;
