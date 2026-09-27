import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronRight, Fingerprint, Inbox, Paperclip, RefreshCw, Search } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const UV_BASE = "/employees/update-verifications";
const TABS = [
  ["PENDING_HR_VERIFICATION", "Menunggu Verifikasi"], ["REVISION_REQUESTED", "Perlu Perbaikan"],
  ["APPROVED", "Disetujui"], ["REJECTED", "Ditolak"], ["ALL", "Semua"],
];
export const STATUS_STYLE = {
  PENDING_HR_VERIFICATION: "border-sky-200 bg-sky-50 text-sky-800",
  REVISION_REQUESTED: "border-amber-300 bg-amber-50 text-amber-900",
  APPROVED: "border-emerald-200 bg-emerald-50 text-emerald-800",
  REJECTED: "border-rose-200 bg-rose-50 text-rose-800",
};
const SECTION_SHORT = { personal: "Pribadi", contact: "Kontak", bank_tax: "Bank & Pajak", bpjs: "BPJS", family: "Keluarga", custom: "Tambahan", documents: "Dokumen" };

export const StatusPill = ({ status, label, testid }) => (
  <Badge variant="outline" className={`whitespace-nowrap ${STATUS_STYLE[status] || ""}`} data-testid={testid}>{label}</Badge>
);

const ChangeChips = ({ changes }) => {
  const entries = Object.entries(changes || {});
  if (!entries.length) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([k, n]) => <span key={k} className="rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium text-foreground">{SECTION_SHORT[k] || k} {n}</span>)}
    </div>
  );
};

export default function EmployeeUpdateVerificationPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("PENDING_HR_VERIFICATION");
  const [flt, setFlt] = useState({ project_id: "", department_id: "", q: "", date_from: "", date_to: "" });
  const [qInput, setQInput] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [counts, setCounts] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const params = { status: tab, page, page_size: 25, ...Object.fromEntries(Object.entries(flt).filter(([, v]) => v)) };
      const [{ data: d }, { data: s }] = await Promise.all([api.get(UV_BASE, { params }), api.get(`${UV_BASE}/summary`)]);
      setData(d); setCounts(s.counts);
    } catch (e) { setError(errorMessage(e)); } finally { setLoading(false); }
  }, [tab, flt, page]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { const t = setTimeout(() => { setPage(1); setFlt((f) => ({ ...f, q: qInput.trim() })); }, 350); return () => clearTimeout(t); }, [qInput]);

  const setF = (k, v) => { setPage(1); setFlt((f) => ({ ...f, [k]: v })); };
  const sel = (key, label, list) => (
    <Select value={flt[key] || "all"} onValueChange={(v) => setF(key, v === "all" ? "" : v)}>
      <SelectTrigger className="w-full sm:w-52" aria-label={label} data-testid={`uv-filter-${key}`}><SelectValue placeholder={label} /></SelectTrigger>
      <SelectContent><SelectItem value="all">Semua {label}</SelectItem>{(list || []).map((o) => <SelectItem key={o.id} value={o.id}>{o.label}</SelectItem>)}</SelectContent>
    </Select>
  );
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const open = (id) => navigate(`${UV_BASE}/${id}`);
  const anyFilter = flt.project_id || flt.department_id || flt.q || flt.date_from || flt.date_to;

  return (
    <>
      <PageHeader title="Verifikasi Pembaruan Data"
        subtitle="Periksa data yang diajukan karyawan lewat Form Pembaruan Data, lalu Setujui, Minta Perbaikan, atau Tolak. Data resmi hanya berubah setelah disetujui."
        actions={<Button variant="outline" onClick={load} data-testid="uv-refresh"><RefreshCw className="mr-1.5 h-4 w-4" />Muat ulang</Button>} />
      <PageBody>
        <Tabs value={tab} onValueChange={(v) => { setTab(v); setPage(1); }}>
          <TabsList className="h-auto flex-wrap" data-testid="uv-tabs">
            {TABS.map(([k, label]) => (
              <TabsTrigger key={k} value={k} data-testid={`uv-tab-${k}`}>
                {label}
                {counts && k !== "ALL" && <span className={`ml-1.5 rounded-full px-1.5 text-[11px] font-semibold tabular-nums ${k === "PENDING_HR_VERIFICATION" && counts[k] ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`} data-testid={`uv-count-${k}`}>{counts[k] ?? 0}</span>}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-center">
          <div className="relative w-full lg:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Cari nama / nomor karyawan" className="pl-9" data-testid="uv-search" />
          </div>
          {sel("project_id", "Project", data?.filters?.projects)}
          {sel("department_id", "Departemen", data?.filters?.departments)}
          <div className="flex items-center gap-2">
            <Input type="date" value={flt.date_from} onChange={(e) => setF("date_from", e.target.value)} className="w-full sm:w-40" aria-label="Dikirim dari tanggal" data-testid="uv-date-from" />
            <span className="text-xs text-muted-foreground">s/d</span>
            <Input type="date" value={flt.date_to} onChange={(e) => setF("date_to", e.target.value)} className="w-full sm:w-40" aria-label="Dikirim sampai tanggal" data-testid="uv-date-to" />
          </div>
          {anyFilter && <Button variant="ghost" onClick={() => { setQInput(""); setPage(1); setFlt({ project_id: "", department_id: "", q: "", date_from: "", date_to: "" }); }} data-testid="uv-filter-reset">Reset filter</Button>}
        </div>

        {error ? (
          <Alert data-testid="uv-list-error"><AlertDescription className="flex flex-wrap items-center gap-2">{error}<Button size="sm" variant="outline" onClick={load} data-testid="uv-list-retry"><RefreshCw className="mr-1.5 h-3.5 w-3.5" />Coba lagi</Button></AlertDescription></Alert>
        ) : loading && !data ? (
          <div className="space-y-2" data-testid="uv-list-loading">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
        ) : !data?.items?.length ? (
          <EmptyState icon={Inbox} testId="uv-empty" title={tab === "PENDING_HR_VERIFICATION" ? "Tidak ada pengajuan yang menunggu verifikasi." : "Belum ada pengajuan pada status ini."}
            description={anyFilter ? "Coba ubah atau reset filter pencarian." : "Pengajuan baru muncul di sini setelah karyawan mengirim Form Pembaruan Data."} />
        ) : (
          <>
            <Card className="hidden overflow-hidden md:block">
              <table className="w-full text-sm" data-testid="uv-table">
                <thead className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr><th className="px-4 py-2.5">Karyawan</th><th className="px-4 py-2.5">Project / Departemen</th><th className="px-4 py-2.5">Dikirim</th><th className="px-4 py-2.5">Status</th><th className="px-4 py-2.5">Ringkasan Perubahan</th><th className="px-2 py-2.5" /></tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <tr key={r.id} className="cursor-pointer border-b transition-colors last:border-b-0 hover:bg-muted/40" onClick={() => open(r.id)} data-testid={`uv-row-${r.id}`}>
                      <td className="px-4 py-3"><p className="font-semibold">{r.employee.full_name}</p><p className="text-xs text-muted-foreground">{r.employee.employee_number}</p></td>
                      <td className="px-4 py-3 text-muted-foreground">{r.project || "—"}<br /><span className="text-xs">{r.department || ""}</span></td>
                      <td className="px-4 py-3 whitespace-nowrap">{r.submitted_at ? formatDateTime(r.submitted_at) : "—"}{r.revision_count > 0 && <p className="text-xs text-muted-foreground">Revisi ke-{r.revision_count}</p>}</td>
                      <td className="px-4 py-3"><StatusPill status={r.status} label={r.status_label} testid={`uv-row-status-${r.id}`} /></td>
                      <td className="px-4 py-3">
                        <ChangeChips changes={r.changes} />
                        <div className="mt-1 flex flex-wrap gap-1">
                          {r.identity_change && <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-800" data-testid={`uv-row-identity-${r.id}`}><Fingerprint className="mr-1 h-3 w-3" />Perubahan identitas</Badge>}
                          {r.has_conflict && <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-900" data-testid={`uv-row-conflict-${r.id}`}><AlertTriangle className="mr-1 h-3 w-3" />Ada konflik</Badge>}
                          {r.attachments > 0 && <span className="inline-flex items-center text-xs text-muted-foreground"><Paperclip className="mr-0.5 h-3 w-3" />{r.attachments} lampiran</span>}
                        </div>
                      </td>
                      <td className="px-2 py-3 text-muted-foreground"><ChevronRight className="h-4 w-4" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <div className="space-y-2 md:hidden" data-testid="uv-cards">
              {data.items.map((r) => (
                <Card key={r.id} className="cursor-pointer" onClick={() => open(r.id)} data-testid={`uv-card-${r.id}`}>
                  <CardContent className="space-y-2 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div><p className="font-semibold">{r.employee.full_name}</p><p className="text-xs text-muted-foreground">{r.employee.employee_number} · {r.submitted_at ? formatDateTime(r.submitted_at) : "—"}</p></div>
                      <StatusPill status={r.status} label={r.status_label} />
                    </div>
                    <ChangeChips changes={r.changes} />
                    <div className="flex flex-wrap gap-1">
                      {r.identity_change && <Badge variant="outline" className="border-violet-200 bg-violet-50 text-violet-800">Perubahan identitas</Badge>}
                      {r.has_conflict && <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-900">Ada konflik</Badge>}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
            <div className="flex items-center justify-between text-sm text-muted-foreground" data-testid="uv-pagination">
              <span>{data.total} pengajuan</span>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} data-testid="uv-prev">Sebelumnya</Button>
                <span>Hal. {page} / {pages}</span>
                <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage((p) => p + 1)} data-testid="uv-next">Berikutnya</Button>
              </div>
            </div>
          </>
        )}
      </PageBody>
    </>
  );
}
