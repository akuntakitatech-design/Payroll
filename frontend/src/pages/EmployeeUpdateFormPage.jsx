import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { QRCodeCanvas } from "qrcode.react";
import {
  CheckCircle2, ClipboardList, Copy, Download, ExternalLink, Eye, FileClock, Hourglass, Link2, QrCode, RefreshCw, Send, Settings2, Share2,
  UserX, Users,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { logoVersion, TenantLogo } from "@/components/common/TenantLogo";
import { FormBuilderSettings } from "@/components/employee-form/FormBuilderSettings";
import { FormPreview } from "@/components/employee-form/FormPreview";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const BASE = "/employees/update-form";

const copyText = async (text) => {
  try { await navigator.clipboard.writeText(text); return true; } catch {
    const ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select(); let ok = false; try { ok = document.execCommand("copy"); } catch { ok = false; } ta.remove(); return ok;
  }
};

const ErrorState = ({ message, onRetry, testid }) => (
  <Alert data-testid={testid}><AlertDescription className="flex flex-wrap items-center gap-2">{message}<Button size="sm" variant="outline" onClick={onRetry} data-testid={`${testid}-retry`}><RefreshCw className="mr-1.5 h-3.5 w-3.5" />Coba lagi</Button></AlertDescription></Alert>
);

/* ------------------------------------------------------------------ QR modal (QR = public company URL only) */
function QrDialog({ open, onClose, url, company }) {
  const wrap = useRef(null);
  const download = () => {
    const qr = wrap.current?.querySelector("canvas");
    if (!qr) return;
    const W = 640, H = 820, c = document.createElement("canvas"); c.width = W; c.height = H;
    const g = c.getContext("2d");
    g.fillStyle = "#ffffff"; g.fillRect(0, 0, W, H);
    g.fillStyle = "#111827"; g.textAlign = "center";
    g.font = "bold 34px Figtree, Arial, sans-serif"; g.fillText("Pembaruan Data Karyawan", W / 2, 80);
    g.font = "24px Figtree, Arial, sans-serif"; g.fillStyle = "#4b5563"; g.fillText(company?.name || "", W / 2, 122);
    g.drawImage(qr, (W - 480) / 2, 160, 480, 480);
    g.font = "20px Figtree, Arial, sans-serif"; g.fillStyle = "#111827";
    const words = url.match(/.{1,48}/g) || [url];
    words.forEach((w, i) => g.fillText(w, W / 2, 700 + i * 28));
    g.font = "16px Figtree, Arial, sans-serif"; g.fillStyle = "#6b7280";
    g.fillText("Pindai QR, lalu verifikasi dengan Nomor Karyawan, NIK, dan Tanggal Lahir.", W / 2, 700 + words.length * 28 + 24);
    const a = document.createElement("a"); a.href = c.toDataURL("image/png"); a.download = `qr-pembaruan-data-${(company?.code || "form").toLowerCase()}.png`;
    document.body.appendChild(a); a.click(); a.remove();
    toast.success("QR Code diunduh (PNG).");
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md" data-testid="ufp-qr-dialog">
        <DialogHeader><DialogTitle>QR Code Form Pembaruan Data</DialogTitle><DialogDescription>QR hanya berisi alamat form publik perusahaan. Tidak ada data karyawan atau token.</DialogDescription></DialogHeader>
        <div className="flex flex-col items-center gap-3 rounded-xl border bg-card p-4 text-center">
          <div className="flex items-center gap-2">
            <TenantLogo size="sm" hasLogo={!!company?.logo_path} version={logoVersion(company)} name={company?.name} testId="ufp-qr-logo" />
            <span className="text-sm font-semibold" data-testid="ufp-qr-company">{company?.name}</span>
          </div>
          <p className="text-base font-bold">Pembaruan Data Karyawan</p>
          <div ref={wrap} className="rounded-lg bg-white p-3" data-testid="ufp-qr-code">
            <QRCodeCanvas value={url} size={220} level="M" marginSize={2} title="QR Code form pembaruan data" />
          </div>
          <p className="break-all text-xs text-muted-foreground" data-testid="ufp-qr-url">{url}</p>
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={async () => { if (await copyText(url)) toast.success("Link disalin."); else toast.error("Gagal menyalin link."); }} data-testid="ufp-qr-copy"><Copy className="mr-1.5 h-4 w-4" />Salin Link</Button>
          <Button onClick={download} data-testid="ufp-qr-download"><Download className="mr-1.5 h-4 w-4" />Download PNG</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ Form Aktif */
function ActiveFormTab({ overview, error, reload, company }) {
  const [qr, setQr] = useState(false);
  if (error) return <ErrorState message={error} onRetry={reload} testid="ufp-overview-error" />;
  if (!overview) return <Skeleton className="h-48 w-full" data-testid="ufp-overview-loading" />;
  const url = overview.public_path ? `${window.location.origin}${overview.public_path}` : null;
  const copy = async () => { if (url && (await copyText(url))) toast.success("Link form disalin."); else toast.error("Gagal menyalin link."); };
  const share = async () => {
    if (navigator.share) {
      try { await navigator.share({ title: "Pembaruan Data Karyawan", text: `Form pembaruan data karyawan ${overview.company?.name || ""}`, url }); return; }
      catch (e) { if (e?.name === "AbortError") return; }
    }
    await copy();
  };
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2" data-testid="ufp-active-form">
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-lg">Form Pembaruan Data Karyawan</CardTitle>
            <Badge variant="outline" className="border-success-border bg-success-soft text-success" data-testid="ufp-form-status"><CheckCircle2 className="mr-1 h-3.5 w-3.5" />Aktif</Badge>
          </div>
          <CardDescription data-testid="ufp-company-name">{overview.company?.name} · karyawan membuka link, verifikasi Nomor Karyawan + NIK + Tanggal Lahir, lalu mengisi data.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Link publik perusahaan</p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input readOnly value={url || "-"} className="font-mono text-sm" onFocus={(e) => e.target.select()} aria-label="Link publik form" data-testid="ufp-public-url" />
              <Button variant="outline" onClick={copy} disabled={!url} data-testid="ufp-copy-link"><Copy className="mr-1.5 h-4 w-4" />Salin Link</Button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" disabled={!url}><a href={url || "#"} target="_blank" rel="noopener noreferrer" data-testid="ufp-open-form"><ExternalLink className="mr-1.5 h-4 w-4" />Buka Form</a></Button>
            <Button variant="outline" onClick={share} disabled={!url} data-testid="ufp-share"><Share2 className="mr-1.5 h-4 w-4" />Bagikan</Button>
            <Button onClick={() => setQr(true)} disabled={!url} data-testid="ufp-show-qr"><QrCode className="mr-1.5 h-4 w-4" />Tampilkan QR Code</Button>
          </div>
          <p className="text-xs text-muted-foreground">Data yang dikirim karyawan menunggu verifikasi HR dan belum mengubah data master.</p>
        </CardContent>
      </Card>
      <Card data-testid="ufp-form-stats">
        <CardHeader><CardTitle className="text-base">Konfigurasi aktif</CardTitle><CardDescription>Versi {overview.form?.version}</CardDescription></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-muted-foreground">Section aktif</span><b data-testid="ufp-stat-sections">{overview.form?.sections_active}</b></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Field tampil</span><b data-testid="ufp-stat-fields">{overview.form?.fields_visible}</b></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Custom field aktif</span><b data-testid="ufp-stat-custom">{overview.form?.custom_active}</b></div>
        </CardContent>
      </Card>
      {url && <QrDialog open={qr} onClose={() => setQr(false)} url={url} company={{ ...company, name: overview.company?.name || company?.name, code: overview.company?.code }} />}
    </div>
  );
}

/* ------------------------------------------------------------------ Monitoring (DB-side aggregate) */
const STATS = [
  ["active_employees", "Total Karyawan Aktif", Users], ["not_started", "Belum Mengisi", UserX], ["draft", "Draft", FileClock],
  ["submitted", "Sudah Submit", Send], ["pending_hr", "Menunggu Verifikasi HR", Hourglass],
];
function MonitoringTab() {
  const [flt, setFlt] = useState({ project_id: "", department_id: "", employee_status_id: "" });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [opts, setOpts] = useState(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      const { data: d } = await api.get(`${BASE}/monitoring`, { params: Object.fromEntries(Object.entries(flt).filter(([, v]) => v)) });
      setData(d); setOpts((o) => o || d.filters);
    } catch (e) { setError(errorMessage(e)); }
  }, [flt]);
  useEffect(() => { load(); }, [load]);
  const sel = (key, label, list) => (
    <Select value={flt[key] || "all"} onValueChange={(v) => setFlt((f) => ({ ...f, [key]: v === "all" ? "" : v }))}>
      <SelectTrigger className="w-full sm:w-56" aria-label={label} data-testid={`ufp-filter-${key}`}><SelectValue placeholder={label} /></SelectTrigger>
      <SelectContent><SelectItem value="all">Semua {label}</SelectItem>{(list || []).map((o) => <SelectItem key={o.id} value={o.id}>{o.label}</SelectItem>)}</SelectContent>
    </Select>
  );
  return (
    <div className="space-y-4" data-testid="ufp-monitoring">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {sel("project_id", "Project", opts?.projects)}
        {sel("department_id", "Department", opts?.departments)}
        {sel("employee_status_id", "Status Karyawan", opts?.employee_statuses)}
        {(flt.project_id || flt.department_id || flt.employee_status_id) && <Button variant="ghost" onClick={() => setFlt({ project_id: "", department_id: "", employee_status_id: "" })} data-testid="ufp-filter-reset">Reset filter</Button>}
      </div>
      {error ? <ErrorState message={error} onRetry={load} testid="ufp-monitoring-error" /> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {STATS.map(([k, label, Icon]) => (
            <Card key={k} data-testid={`ufp-stat-${k}`}>
              <CardContent className="space-y-1 p-4">
                <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><Icon className="h-3.5 w-3.5" />{label}</p>
                {data ? <p className="text-2xl font-bold tabular-nums" data-numeric="true" data-testid={`ufp-stat-${k}-value`}>{data.summary[k]}</p> : <Skeleton className="h-8 w-16" />}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {data?.note && <p className="text-xs text-muted-foreground" data-testid="ufp-monitoring-note">{data.note}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ Preview tab */
function PreviewTab({ version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    setError(null);
    try { const { data: d } = await api.get(`${BASE}/preview`); setData(d); } catch (e) { setError(errorMessage(e)); }
  }, []);
  useEffect(() => { load(); }, [load, version]);
  if (error) return <ErrorState message={error} onRetry={load} testid="ufp-preview-error" />;
  if (!data) return <Skeleton className="h-96 w-full" data-testid="ufp-preview-loading" />;
  return <FormPreview key={version} data={data} />;
}

export default function EmployeeUpdateFormPage() {
  const { company } = useAuth();
  const [tab, setTab] = useState("active");
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    setError(null);
    try { const { data } = await api.get(`${BASE}/overview`); setOverview(data); } catch (e) { setError(errorMessage(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const canConfigure = !!overview?.can_configure;
  return (
    <>
      <PageHeader title="Form Pembaruan Data" subtitle="Data Karyawan · bagikan form publik, pantau pengisian, dan atur isi form tanpa bantuan developer." />
      <PageBody>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="h-auto flex-wrap" data-testid="ufp-tabs">
            <TabsTrigger value="active" data-testid="ufp-tab-active"><Link2 className="mr-1.5 h-4 w-4" />Form Aktif</TabsTrigger>
            <TabsTrigger value="monitoring" data-testid="ufp-tab-monitoring"><ClipboardList className="mr-1.5 h-4 w-4" />Monitoring</TabsTrigger>
            {canConfigure && <TabsTrigger value="settings" data-testid="ufp-tab-settings"><Settings2 className="mr-1.5 h-4 w-4" />Pengaturan Form</TabsTrigger>}
            {canConfigure && <TabsTrigger value="preview" data-testid="ufp-tab-preview"><Eye className="mr-1.5 h-4 w-4" />Preview</TabsTrigger>}
          </TabsList>
          <TabsContent value="active" className="mt-4"><ActiveFormTab overview={overview} error={error} reload={load} company={company} /></TabsContent>
          <TabsContent value="monitoring" className="mt-4"><MonitoringTab /></TabsContent>
          {canConfigure && <TabsContent value="settings" className="mt-4"><FormBuilderSettings onChanged={load} /></TabsContent>}
          {canConfigure && <TabsContent value="preview" className="mt-4"><PreviewTab version={overview?.form?.version} /></TabsContent>}
        </Tabs>
        {overview && !canConfigure && <p className="text-xs text-muted-foreground" data-testid="ufp-no-configure">Pengaturan form hanya untuk pengguna dengan izin “Atur Form Pembaruan Data”.</p>}
      </PageBody>
    </>
  );
}
