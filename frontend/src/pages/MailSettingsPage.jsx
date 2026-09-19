import React, { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Clock,
  Eye,
  Loader2,
  Mail,
  Save,
  Send,
  ServerCog,
  XCircle,
} from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const WINDOW_CHOICES = [90, 60, 30, 14, 7, 3, 1];

const KIND_LABELS = {
  contracts: "Kontrak",
  certifications: "Sertifikasi",
  documents: "Dokumen",
};

const LOG_TONE = {
  sent: "border-emerald-200 bg-emerald-100 text-emerald-800",
  failed: "border-red-200 bg-red-100 text-red-800",
  skipped: "border-slate-200 bg-slate-100 text-slate-700",
};

const ToggleRow = ({ title, description, checked, onChange, testId, disabled }) => (
  <div className="flex items-start justify-between gap-4 rounded-lg border border-border p-3">
    <div>
      <p className="text-sm font-medium">{title}</p>
      {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
    </div>
    <Switch
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      data-testid={testId}
    />
  </div>
);

const MailSettingsPage = () => {
  const { can, user } = useAuth();
  const editable = can("settings", "config");

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [smtp, setSmtp] = useState(null);
  const [reminder, setReminder] = useState(null);
  const [savingSmtp, setSavingSmtp] = useState(false);
  const [savingReminder, setSavingReminder] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [testing, setTesting] = useState(false);
  const [sendingNow, setSendingNow] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [logs, setLogs] = useState(null);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const [settingsRes, logsRes] = await Promise.all([
        api.get("/mail/settings"),
        api.get("/mail/reminder/logs", { params: { limit: 20 } }).catch(() => ({ data: null })),
      ]);
      const payload = settingsRes.data;
      setData(payload);
      setSmtp({
        host: payload?.smtp?.host || "",
        port: String(payload?.smtp?.port || 587),
        username: payload?.smtp?.username || "",
        password: "",
        security: payload?.smtp?.security || "starttls",
        from_email: payload?.smtp?.from_email || "",
        from_name: payload?.smtp?.from_name || "",
        is_enabled: !!payload?.smtp?.is_enabled,
      });
      setReminder({
        is_enabled: !!payload?.reminder?.is_enabled,
        windows: payload?.reminder?.windows || [],
        recipients: (payload?.reminder?.recipients || []).join(", "),
        send_hour: String(payload?.reminder?.send_hour ?? 7),
        send_minute: String(payload?.reminder?.send_minute ?? 0),
        include_expired: payload?.reminder?.include_expired !== false,
        include_contracts: payload?.reminder?.include_contracts !== false,
        include_certifications: payload?.reminder?.include_certifications !== false,
        include_documents: payload?.reminder?.include_documents !== false,
        skip_when_empty: payload?.reminder?.skip_when_empty !== false,
      });
      setLogs(logsRes.data);
    } catch (error) {
      toast.error(errorMessage(error, "Pengaturan email tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    document.title = "Email & Pengingat · HRIS Suite";
  }, []);

  const smtpConfigured = data?.smtp?.is_configured;
  const scheduler = data?.scheduler;
  const nextRun = useMemo(() => scheduler?.jobs?.[0]?.next_run || null, [scheduler]);

  const saveSmtp = async () => {
    setSavingSmtp(true);
    try {
      const payload = {
        host: smtp.host.trim(),
        port: Number(smtp.port),
        username: smtp.username.trim(),
        security: smtp.security,
        from_email: smtp.from_email.trim(),
        from_name: smtp.from_name.trim(),
        is_enabled: smtp.is_enabled,
      };
      if (smtp.password) payload.password = smtp.password;
      await api.put("/mail/settings/smtp", payload);
      toast.success("Pengaturan SMTP disimpan.");
      setSmtp({ ...smtp, password: "" });
      await load({ silent: true });
    } catch (error) {
      toast.error(errorMessage(error, "Pengaturan SMTP gagal disimpan."));
    } finally {
      setSavingSmtp(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const { data: res } = await api.post("/mail/settings/smtp/test", {
        to: testTo.trim() || null,
      });
      toast.success(res?.message || `Email tes terkirim ke ${res?.recipient}.`);
      setTestOpen(false);
    } catch (error) {
      toast.error(errorMessage(error, "Email tes gagal dikirim."));
    } finally {
      setTesting(false);
    }
  };

  const saveReminder = async () => {
    setSavingReminder(true);
    try {
      await api.put("/mail/settings/reminder", {
        is_enabled: reminder.is_enabled,
        windows: reminder.windows.map(Number),
        recipients: reminder.recipients
          .split(/[,;\n]/)
          .map((value) => value.trim())
          .filter(Boolean),
        send_hour: Number(reminder.send_hour),
        send_minute: Number(reminder.send_minute),
        include_expired: reminder.include_expired,
        include_contracts: reminder.include_contracts,
        include_certifications: reminder.include_certifications,
        include_documents: reminder.include_documents,
        skip_when_empty: reminder.skip_when_empty,
      });
      toast.success("Pengaturan pengingat disimpan.");
      await load({ silent: true });
    } catch (error) {
      toast.error(errorMessage(error, "Pengaturan pengingat gagal disimpan."));
    } finally {
      setSavingReminder(false);
    }
  };

  const loadPreview = async () => {
    setPreviewLoading(true);
    try {
      const { data: res } = await api.get("/mail/reminder/preview");
      const raw = res?.items;
      const flat = Array.isArray(raw)
        ? raw
        : Object.entries(raw || {}).flatMap(([kind, list]) =>
            (Array.isArray(list) ? list : []).map((item) => ({ kind, ...item }))
          );
      setPreview({ ...res, items: flat });
    } catch (error) {
      toast.error(errorMessage(error, "Pratinjau pengingat gagal dibuat."));
    } finally {
      setPreviewLoading(false);
    }
  };

  const sendNow = async () => {
    setSendingNow(true);
    try {
      const { data: res } = await api.post("/mail/reminder/send-now", {});
      toast.success(res?.message || "Pengingat dikirim.");
      await load({ silent: true });
    } catch (error) {
      toast.error(errorMessage(error, "Pengingat gagal dikirim."));
    } finally {
      setSendingNow(false);
    }
  };

  const toggleWindow = (value) =>
    setReminder((prev) => ({
      ...prev,
      windows: prev.windows.includes(value)
        ? prev.windows.filter((w) => w !== value)
        : [...prev.windows, value].sort((a, b) => b - a),
    }));

  if (loading || !smtp || !reminder) {
    return (
      <>
        <PageHeader title="Email & Pengingat" subtitle="Memuat pengaturan…" />
        <PageBody>
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </PageBody>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Email & Pengingat"
        subtitle="Kirim pengingat masa berlaku kontrak, sertifikasi, dan dokumen lewat SMTP perusahaan."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {editable && (
              <Button
                variant="outline"
                onClick={() => {
                  setTestTo(user?.email || "");
                  setTestOpen(true);
                }}
                disabled={!smtpConfigured}
                data-testid="mail-test-open"
              >
                <Send className="mr-2 h-4 w-4" /> Kirim email tes
              </Button>
            )}
            <Button variant="outline" onClick={loadPreview} disabled={previewLoading} data-testid="mail-preview">
              {previewLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Eye className="mr-2 h-4 w-4" />
              )}
              Pratinjau isi
            </Button>
          </div>
        }
      />
      <PageBody>
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-secondary/40 p-3 text-xs">
          <Badge
            variant="outline"
            className={smtpConfigured ? LOG_TONE.sent : LOG_TONE.skipped}
            data-testid="mail-smtp-status"
          >
            {smtpConfigured ? "SMTP terkonfigurasi" : "SMTP belum diatur"}
          </Badge>
          <Badge
            variant="outline"
            className={reminder.is_enabled ? LOG_TONE.sent : LOG_TONE.skipped}
            data-testid="mail-reminder-status"
          >
            {reminder.is_enabled ? "Pengingat aktif" : "Pengingat nonaktif"}
          </Badge>
          <span className="flex items-center gap-1 text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            Penjadwal {scheduler?.running ? "berjalan" : "berhenti"} ({scheduler?.timezone})
            {nextRun ? ` · jadwal berikutnya ${formatDateTime(nextRun)}` : ""}
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ServerCog className="h-4 w-4" /> Server SMTP Perusahaan
              </CardTitle>
              <CardDescription>
                Kata sandi disimpan terenkripsi di server dan tidak pernah ditampilkan kembali.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1.5 sm:col-span-2">
                  <Label htmlFor="smtp-host">Host SMTP</Label>
                  <Input
                    id="smtp-host"
                    value={smtp.host}
                    onChange={(e) => setSmtp({ ...smtp, host: e.target.value })}
                    placeholder="mail.perusahaan.co.id"
                    disabled={!editable}
                    data-testid="smtp-host"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="smtp-port">Port</Label>
                  <Input
                    id="smtp-port"
                    type="number"
                    min="1"
                    max="65535"
                    value={smtp.port}
                    onChange={(e) => setSmtp({ ...smtp, port: e.target.value })}
                    disabled={!editable}
                    data-testid="smtp-port"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="smtp-security">Keamanan</Label>
                  <Select
                    value={smtp.security}
                    onValueChange={(v) => setSmtp({ ...smtp, security: v })}
                    disabled={!editable}
                  >
                    <SelectTrigger id="smtp-security" data-testid="smtp-security">
                      <SelectValue placeholder="Pilih mode" />
                    </SelectTrigger>
                    <SelectContent>
                      {(data?.security_modes || []).map((mode) => (
                        <SelectItem key={mode.value} value={mode.value}>
                          {mode.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="smtp-username">Username</Label>
                  <Input
                    id="smtp-username"
                    value={smtp.username}
                    onChange={(e) => setSmtp({ ...smtp, username: e.target.value })}
                    autoComplete="off"
                    disabled={!editable}
                    data-testid="smtp-username"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="smtp-password">Kata sandi</Label>
                  <Input
                    id="smtp-password"
                    type="password"
                    value={smtp.password}
                    onChange={(e) => setSmtp({ ...smtp, password: e.target.value })}
                    placeholder={data?.smtp?.has_password ? "Tersimpan · isi untuk mengganti" : "Kata sandi email"}
                    autoComplete="new-password"
                    disabled={!editable}
                    data-testid="smtp-password"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="smtp-from-email">Email pengirim</Label>
                  <Input
                    id="smtp-from-email"
                    type="email"
                    value={smtp.from_email}
                    onChange={(e) => setSmtp({ ...smtp, from_email: e.target.value })}
                    placeholder="hris@perusahaan.co.id"
                    disabled={!editable}
                    data-testid="smtp-from-email"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="smtp-from-name">Nama pengirim</Label>
                  <Input
                    id="smtp-from-name"
                    value={smtp.from_name}
                    onChange={(e) => setSmtp({ ...smtp, from_name: e.target.value })}
                    placeholder="HRIS Perusahaan"
                    disabled={!editable}
                    data-testid="smtp-from-name"
                  />
                </div>
              </div>
              <ToggleRow
                title="Aktifkan pengiriman email"
                description="Matikan sementara bila server email sedang bermasalah."
                checked={smtp.is_enabled}
                onChange={(v) => setSmtp({ ...smtp, is_enabled: v })}
                disabled={!editable}
                testId="smtp-enabled"
              />
              {editable && (
                <div className="flex justify-end">
                  <Button onClick={saveSmtp} disabled={savingSmtp} data-testid="smtp-save">
                    {savingSmtp ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="mr-2 h-4 w-4" />
                    )}
                    Simpan SMTP
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <BellRing className="h-4 w-4" /> Pengingat Masa Berlaku
              </CardTitle>
              <CardDescription>
                Email otomatis dikirim setiap hari pada jam yang Anda tentukan (zona Asia/Jakarta).
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Kirim pada H-</Label>
                <div className="flex flex-wrap gap-2" data-testid="reminder-windows">
                  {WINDOW_CHOICES.map((value) => {
                    const active = reminder.windows.includes(value);
                    return (
                      <button
                        key={value}
                        type="button"
                        disabled={!editable}
                        onClick={() => toggleWindow(value)}
                        className={`rounded-full border px-3 py-1 text-sm transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60 ${
                          active
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border bg-card text-muted-foreground hover:bg-secondary"
                        }`}
                        data-testid={`reminder-window-${value}`}
                      >
                        H-{value}
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  Item hanya dikirim ketika sisa harinya tepat pada salah satu penanda di atas.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="reminder-recipients">Penerima</Label>
                <Textarea
                  id="reminder-recipients"
                  value={reminder.recipients}
                  onChange={(e) => setReminder({ ...reminder, recipients: e.target.value })}
                  placeholder="hr@perusahaan.co.id, manager@perusahaan.co.id"
                  disabled={!editable}
                  data-testid="reminder-recipients"
                />
                <p className="text-xs text-muted-foreground">Pisahkan dengan koma atau baris baru.</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="reminder-hour">Jam kirim</Label>
                  <Input
                    id="reminder-hour"
                    type="number"
                    min="0"
                    max="23"
                    value={reminder.send_hour}
                    onChange={(e) => setReminder({ ...reminder, send_hour: e.target.value })}
                    disabled={!editable}
                    data-testid="reminder-hour"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="reminder-minute">Menit</Label>
                  <Input
                    id="reminder-minute"
                    type="number"
                    min="0"
                    max="59"
                    value={reminder.send_minute}
                    onChange={(e) => setReminder({ ...reminder, send_minute: e.target.value })}
                    disabled={!editable}
                    data-testid="reminder-minute"
                  />
                </div>
              </div>

              <Separator />
              <div className="grid grid-cols-1 gap-2">
                <ToggleRow
                  title="Sertakan kontrak kerja"
                  checked={reminder.include_contracts}
                  onChange={(v) => setReminder({ ...reminder, include_contracts: v })}
                  disabled={!editable}
                  testId="reminder-include-contracts"
                />
                <ToggleRow
                  title="Sertakan sertifikasi"
                  checked={reminder.include_certifications}
                  onChange={(v) => setReminder({ ...reminder, include_certifications: v })}
                  disabled={!editable}
                  testId="reminder-include-certifications"
                />
                <ToggleRow
                  title="Sertakan dokumen"
                  checked={reminder.include_documents}
                  onChange={(v) => setReminder({ ...reminder, include_documents: v })}
                  disabled={!editable}
                  testId="reminder-include-documents"
                />
                <ToggleRow
                  title="Sertakan yang sudah kedaluwarsa"
                  description="Tetap ingatkan item yang terlewat agar segera ditindak."
                  checked={reminder.include_expired}
                  onChange={(v) => setReminder({ ...reminder, include_expired: v })}
                  disabled={!editable}
                  testId="reminder-include-expired"
                />
                <ToggleRow
                  title="Jangan kirim bila tidak ada item"
                  checked={reminder.skip_when_empty}
                  onChange={(v) => setReminder({ ...reminder, skip_when_empty: v })}
                  disabled={!editable}
                  testId="reminder-skip-empty"
                />
                <ToggleRow
                  title="Aktifkan pengingat otomatis"
                  description="Perlu minimal satu penerima dan SMTP yang sudah diatur."
                  checked={reminder.is_enabled}
                  onChange={(v) => setReminder({ ...reminder, is_enabled: v })}
                  disabled={!editable}
                  testId="reminder-enabled"
                />
              </div>

              {editable && (
                <div className="flex flex-wrap justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={sendNow}
                    disabled={sendingNow || !smtpConfigured}
                    data-testid="reminder-send-now"
                  >
                    {sendingNow ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Mail className="mr-2 h-4 w-4" />
                    )}
                    Kirim sekarang
                  </Button>
                  <Button onClick={saveReminder} disabled={savingReminder} data-testid="reminder-save">
                    {savingReminder ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="mr-2 h-4 w-4" />
                    )}
                    Simpan pengingat
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {preview ? (
          <Card data-testid="reminder-preview">
            <CardHeader>
              <CardTitle className="text-base">Pratinjau pengingat</CardTitle>
              <CardDescription>
                {preview.subject} · {preview.total} item · penerima{" "}
                {(preview.recipients || []).join(", ") || "belum diatur"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {preview.total === 0 ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" /> Tidak ada masa berlaku yang
                  jatuh pada penanda H- saat ini.
                </p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {(preview.items || []).slice(0, 25).map((item, index) => (
                    <li key={index} className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{KIND_LABELS[item.kind] || item.kind}</Badge>
                      <span className="font-medium">{item.title}</span>
                      <span className="text-xs text-muted-foreground">
                        {item.subtitle ? `${item.subtitle} · ` : ""}
                        {item.days_left < 0
                          ? `kedaluwarsa ${Math.abs(item.days_left)} hari`
                          : `H-${item.days_left}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Riwayat pengiriman</CardTitle>
            <CardDescription>
              {logs?.sent_count ?? 0} terkirim · {logs?.failed_count ?? 0} gagal
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!logs?.items?.length ? (
              <p className="text-sm text-muted-foreground" data-testid="reminder-logs-empty">
                Belum ada riwayat pengiriman pengingat.
              </p>
            ) : (
              <ul className="divide-y divide-border" data-testid="reminder-logs">
                {logs.items.map((log) => (
                  <li key={log.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                    <Badge variant="outline" className={LOG_TONE[log.status] || ""}>
                      {log.status === "sent" ? (
                        <CheckCircle2 className="mr-1 h-3 w-3" />
                      ) : log.status === "failed" ? (
                        <XCircle className="mr-1 h-3 w-3" />
                      ) : (
                        <AlertTriangle className="mr-1 h-3 w-3" />
                      )}
                      {log.status}
                    </Badge>
                    <span className="text-xs text-muted-foreground">{formatDateTime(log.created_at)}</span>
                    <span className="text-xs">{log.trigger}</span>
                    <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                      {log.item_count} item · {log.message}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </PageBody>

      <Dialog open={testOpen} onOpenChange={setTestOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Kirim email tes</DialogTitle>
            <DialogDescription>
              Kami mengirim satu email singkat memakai pengaturan SMTP yang tersimpan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="test-to">Tujuan</Label>
            <Input
              id="test-to"
              type="email"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              placeholder={user?.email || "nama@perusahaan.co.id"}
              data-testid="smtp-test-to"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTestOpen(false)} data-testid="smtp-test-cancel">
              Batal
            </Button>
            <Button onClick={sendTest} disabled={testing} data-testid="smtp-test-send">
              {testing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
              Kirim
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default MailSettingsPage;
