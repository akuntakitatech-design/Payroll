import React, { useCallback, useEffect, useState } from "react";
import { History, RefreshCw } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { SOURCE_LABELS } from "@/lib/employeeStatus";
import { formatDate, formatDateTime } from "@/lib/format";
import { EmployeeStatusBadge } from "@/components/employees/EmployeeStatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const StatusCell = ({ name, category, inactive }) =>
  name ? (
    <div className="space-y-0.5">
      <EmployeeStatusBadge name={name} category={category} />
      {inactive && <p className="text-[11px] text-muted-foreground">Status master kini nonaktif</p>}
    </div>
  ) : (
    <span className="text-muted-foreground">-</span>
  );

/** Kartu Riwayat Status di detail karyawan (bukan Profile 360). */
export const StatusHistoryCard = ({ employeeId, refreshKey }) => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/employees/${employeeId}/status-history`);
      setRows(res.data.items || []);
    } catch (err) {
      setError(errorMessage(err, "Riwayat status gagal dimuat."));
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <section className="rounded-xl border border-border bg-card p-5" data-testid="status-history-card">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <h2 className="text-section-title">Riwayat Status</h2>
        </div>
        <span className="text-[12px] text-muted-foreground" data-testid="status-history-count">
          {loading ? "" : `${rows.length} catatan`}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : error ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-danger-border bg-danger-soft p-3 text-sm text-danger" data-testid="status-history-error">
          {error}
          <Button size="sm" variant="outline" onClick={load} data-testid="status-history-retry">
            <RefreshCw className="mr-2 h-3.5 w-3.5" /> Coba lagi
          </Button>
        </div>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="status-history-empty">
          Belum ada riwayat perubahan status.
        </p>
      ) : (
        <div className="-mx-5 overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm" data-testid="status-history-table">
            <thead>
              <tr className="border-b border-border text-left text-[12px] font-medium text-muted-foreground">
                <th className="px-5 py-2">Tanggal Efektif</th>
                <th className="px-3 py-2">Status Sebelumnya</th>
                <th className="px-3 py-2">Status Baru</th>
                <th className="px-3 py-2">Alasan</th>
                <th className="px-3 py-2">Catatan</th>
                <th className="px-3 py-2">Diubah Oleh</th>
                <th className="px-5 py-2">Waktu Dicatat</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-border/60 align-top last:border-0" data-testid={`status-history-row-${r.id}`}>
                  <td className="whitespace-nowrap px-5 py-2.5">
                    {r.effective_date ? formatDate(r.effective_date) : <span className="text-muted-foreground">Tidak diketahui</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusCell name={r.previous_status_name} category={r.previous_category} inactive={r.previous_status_is_active === false} />
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusCell name={r.new_status_name} category={r.new_category} inactive={r.new_status_is_active === false} />
                  </td>
                  <td className="px-3 py-2.5">{r.reason || "-"}</td>
                  <td className="max-w-[220px] px-3 py-2.5 text-muted-foreground">{r.notes || "-"}</td>
                  <td className="px-3 py-2.5">
                    {r.changed_by_name || <span className="text-muted-foreground">{SOURCE_LABELS[r.source] || "Sistem"}</span>}
                    {r.source && r.source !== "MANUAL" && (
                      <span className="mt-0.5 block text-[11px] text-muted-foreground">{SOURCE_LABELS[r.source] || r.source}</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-5 py-2.5 text-muted-foreground">{formatDateTime(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};

export default StatusHistoryCard;
