import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download, ExternalLink, Eye, FileText, History, Package, RefreshCw } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentRow, downloadDocument, viewDocument } from "@/pages/asset/AssetDocumentsPanel";

/* Phase 2A CP4 - Employee Asset 360 (read-only). Semua data dibaca langsung dari tabel transaksi & dokumen
   (holdings / handovers / returns / inspections / openings / BAST / asset_documents) - tanpa salinan. */

const EVENT = {
  OPENING_EXISTING: { label: "Saldo Awal", tone: "border-info/40 text-info" },
  HANDOVER: { label: "Penyerahan", tone: "border-primary/40 text-primary" },
  RETURN: { label: "Pengembalian", tone: "border-warning/40 text-warning" },
  INSPECTION: { label: "Pemeriksaan", tone: "border-success/40 text-success" },
};
const RESULT = { READY: "Siap Pakai", MAINTENANCE: "Perawatan", DAMAGED: "Rusak", LOST: "Hilang" };

export const sourceLink = (sourceType, sourceId) => ({
  HANDOVER: `/modules/asset/handovers?open=${sourceId}`,
  RETURN: `/modules/asset/returns?open=${sourceId}`,
  OPENING_EXISTING: `/modules/asset/imports?tab=opening&open=${sourceId}`,
}[sourceType]);

const Section = ({ icon: Icon, title, count, children, testId }) => (
  <Card data-testid={testId}>
    <CardHeader className="pb-3">
      <CardTitle className="flex items-center gap-2 text-base"><Icon className="h-4 w-4" />{title}
        {count != null && <Badge variant="secondary" data-testid={`${testId}-count`}>{count}</Badge>}</CardTitle>
    </CardHeader>
    <CardContent>{children}</CardContent>
  </Card>
);

const Empty = ({ children, testId }) => (
  <p className="rounded-lg border border-dashed border-border p-4 text-center text-[13px] text-muted-foreground" data-testid={testId}>{children}</p>
);

export const EmployeeAsset360 = ({ employeeId }) => {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    setData(null);
    try {
      const res = await api.get(`/employees/${employeeId}/asset-360`);
      setData(res.data);
    } catch (e) {
      setError(errorMessage(e, "Data aset karyawan gagal dimuat."));
    }
  }, [employeeId]);
  useEffect(() => { load(); }, [load]);

  if (error) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-border p-4 text-sm text-danger" role="alert" data-testid="asset360-error">
        {error}<Button size="sm" variant="outline" onClick={load} data-testid="asset360-retry"><RefreshCw className="mr-1 h-3.5 w-3.5" />Coba lagi</Button>
      </div>
    );
  }
  if (!data) return <div className="space-y-3" data-testid="asset360-loading"><Skeleton className="h-32 w-full" /><Skeleton className="h-48 w-full" /></div>;

  const linkBtns = (st, sid, bastId, key) => (
    <div className="flex flex-wrap gap-1.5">
      <Button size="sm" variant="outline" onClick={() => navigate(sourceLink(st, sid))} data-testid={`asset360-open-source-${key}`}>
        <ExternalLink className="mr-1 h-3.5 w-3.5" />Transaksi
      </Button>
      {bastId && (
        <Button size="sm" variant="outline" onClick={() => navigate(`/modules/asset/basts?open=${bastId}`)} data-testid={`asset360-open-bast-${key}`}>
          <FileText className="mr-1 h-3.5 w-3.5" />BAST
        </Button>
      )}
    </div>
  );

  return (
    <div className="space-y-4" data-testid="asset360">
      <Section icon={Package} title="Aset Saat Ini" count={data.current.length} testId="asset360-current">
        {data.current.length === 0 ? <Empty testId="asset360-current-empty">Karyawan ini tidak sedang memegang aset.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[56rem] text-[13px]">
              <thead className="text-left text-[12px] text-muted-foreground">
                <tr>{["Aset", "Kategori", "Serial", "Kondisi", "Mulai Pegang", "Proyek / Lokasi", "Sumber", "BAST", ""].map((h) => <th key={h} className="py-2 pr-3 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody>
                {data.current.map((a) => (
                  <tr key={a.holding_id} className="border-t border-border align-top" data-testid={`asset360-current-row-${a.asset_code}`}>
                    <td className="py-2 pr-3"><div className="font-mono text-[12px]">{a.asset_code}</div><div>{a.asset_name}</div></td>
                    <td className="py-2 pr-3">{a.category_name || "-"}</td>
                    <td className="py-2 pr-3">{a.serial_number || "-"}</td>
                    <td className="py-2 pr-3">{a.current_condition_name || a.initial_condition_name || "-"}</td>
                    <td className="py-2 pr-3 whitespace-nowrap">{a.start_date ? formatDate(a.start_date) : "-"}</td>
                    <td className="py-2 pr-3">{[a.project_name, a.work_location_name].filter(Boolean).join(" / ") || "-"}</td>
                    <td className="py-2 pr-3"><Badge variant="outline" className={EVENT[a.source_type].tone}>{a.source_type === "OPENING_EXISTING" ? "Opening Existing" : "Penyerahan"}</Badge></td>
                    <td className="py-2 pr-3 font-mono text-[12px] whitespace-nowrap">{a.bast_number || "-"}</td>
                    <td className="py-2">{linkBtns(a.source_type, a.source_id, a.bast_id, `current-${a.asset_code}`)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section icon={History} title="Histori Aset" count={data.history.length} testId="asset360-history">
        {data.history.length === 0 ? <Empty testId="asset360-history-empty">Belum ada histori transaksi aset.</Empty> : (
          <ol className="space-y-2" data-testid="asset360-history-list">
            {data.history.map((h, i) => (
              <li key={`${h.event_type}-${h.source_id}-${h.asset_id}-${i}`} className="flex flex-col gap-2 rounded-lg border border-border p-3 sm:flex-row sm:items-center"
                data-testid={`asset360-history-row-${i}`}>
                <div className="w-28 shrink-0 text-[12px] text-muted-foreground">{h.date ? formatDate(h.date) : "-"}</div>
                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className={EVENT[h.event_type].tone}>{EVENT[h.event_type].label}</Badge>
                    <span className="font-mono text-[12px]">{h.asset_code}</span><span className="text-sm">{h.asset_name}</span>
                  </div>
                  <p className="text-[12px] text-muted-foreground">
                    {h.project_name ? `${h.project_name} · ` : ""}
                    {h.condition_before ? `Kondisi ${h.condition_before} → ${h.condition_after || "-"}` : h.condition_after ? `Kondisi ${h.condition_after}` : ""}
                    {h.result_state ? ` · Hasil ${RESULT[h.result_state] || h.result_state}` : ""}
                    {h.bast_number ? ` · ${h.bast_number}` : ""}
                  </p>
                </div>
                {linkBtns(h.source_type, h.source_id, h.bast_id, `history-${i}`)}
              </li>
            ))}
          </ol>
        )}
      </Section>

      {data.documents !== null && (
        <Section icon={FileText} title="Dokumen Aset" count={data.documents.length} testId="asset360-documents">
          <p className="mb-3 text-[12px] text-muted-foreground">Dokumen dari transaksi Penyerahan, Pengembalian, dan Saldo Awal karyawan ini (tanpa upload ulang).</p>
          {data.documents.length === 0 ? <Empty testId="asset360-documents-empty">Belum ada dokumen transaksi aset.</Empty> : (
            <ul className="space-y-2" data-testid="asset360-documents-list">
              {data.documents.map((d) => (
                <DocumentRow key={d.id} doc={d} testId={`asset360-doc-${d.id}`}
                  meta={<p className="text-[12px] text-muted-foreground">Sumber: {d.source_label}{d.bast_number ? ` · ${d.bast_number}` : ""}</p>}
                  actions={(
                    <>
                      <Button size="sm" variant="outline" onClick={() => viewDocument(d)} data-testid={`asset360-doc-view-${d.id}`}><Eye className="mr-1 h-3.5 w-3.5" />Lihat</Button>
                      <Button size="sm" variant="outline" onClick={() => downloadDocument(d)} data-testid={`asset360-doc-download-${d.id}`}><Download className="mr-1 h-3.5 w-3.5" />Unduh</Button>
                      {linkBtns(d.source_type, d.source_id, d.bast_id, `doc-${d.id}`)}
                    </>
                  )} />
              ))}
            </ul>
          )}
        </Section>
      )}
    </div>
  );
};

export default EmployeeAsset360;
