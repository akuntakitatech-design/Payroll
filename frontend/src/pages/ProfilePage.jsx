import React, { useEffect, useState } from "react";
import { KeyRound, Loader2, Mail, Shield, Building2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, initials } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

const ROLE_LABELS = {
  super_admin: "Super Admin",
  company_owner: "Pemilik Perusahaan",
  hr_admin: "HR Admin",
  hr_manager: "HR Manager",
  finance: "Finance",
  manager: "Manager",
  supervisor: "Supervisor",
  employee: "Karyawan",
};

const ProfilePage = () => {
  const { user, company, companies, roleKeys } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    document.title = "Profil Saya · HRIS Suite";
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!current || !next) {
      setError("Kata sandi saat ini dan kata sandi baru wajib diisi.");
      return;
    }
    if (next.length < 8) {
      setError("Kata sandi baru minimal 8 karakter agar akun Anda tetap aman.");
      return;
    }
    if (next !== confirmPwd) {
      setError("Konfirmasi kata sandi belum sama dengan kata sandi baru.");
      return;
    }
    setSaving(true);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      toast.success("Kata sandi berhasil diperbarui.");
      setCurrent("");
      setNext("");
      setConfirmPwd("");
    } catch (err) {
      const msg = errorMessage(err, "Kata sandi tidak dapat diperbarui.");
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader title="Profil Saya" subtitle="Informasi akun dan keamanan kata sandi Anda." />
      <PageBody>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="border-border bg-card p-5" data-testid="profile-info-card">
            <div className="flex items-start gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-primary text-base font-semibold text-primary-foreground">
                {initials(user?.full_name)}
              </span>
              <div className="min-w-0">
                <p className="text-section-title">{user?.full_name}</p>
                <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <Mail className="h-3.5 w-3.5" /> {user?.email}
                </p>
                {user?.job_title && <p className="text-sm text-muted-foreground">{user.job_title}</p>}
              </div>
            </div>

            <div className="mt-4 space-y-3 border-t border-border pt-4">
              <div>
                <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                  <Shield className="h-3.5 w-3.5" /> Peran di perusahaan aktif
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {roleKeys.length ? (
                    roleKeys.map((r) => (
                      <Badge key={r} variant="secondary">
                        {ROLE_LABELS[r] || r}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-sm text-muted-foreground">Belum ada peran.</span>
                  )}
                </div>
              </div>

              <div>
                <p className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                  <Building2 className="h-3.5 w-3.5" /> Perusahaan yang dapat diakses
                </p>
                <ul className="mt-1.5 space-y-1">
                  {companies.map((c) => (
                    <li key={c.id} className="flex items-center justify-between text-sm">
                      <span className="truncate">{c.name}</span>
                      {c.id === company?.id && (
                        <Badge variant="outline" className="shrink-0 text-[11px]">
                          Aktif
                        </Badge>
                      )}
                    </li>
                  ))}
                </ul>
              </div>

              <p className="text-xs text-muted-foreground">
                Login terakhir: {formatDateTime(user?.last_login_at)}
              </p>
            </div>
          </Card>

          <Card className="border-border bg-card p-5" id="password" data-testid="profile-password-card">
            <div className="flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-primary" />
              <h2 className="text-section-title">Ubah Kata Sandi</h2>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Gunakan kombinasi huruf, angka, dan simbol. Minimal 8 karakter.
            </p>
            <form onSubmit={submit} className="mt-4 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="current">Kata Sandi Saat Ini</Label>
                <Input
                  id="current"
                  type="password"
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                  data-testid="profile-current-password"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="new">Kata Sandi Baru</Label>
                <Input
                  id="new"
                  type="password"
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                  data-testid="profile-new-password"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="confirm">Konfirmasi Kata Sandi Baru</Label>
                <Input
                  id="confirm"
                  type="password"
                  value={confirmPwd}
                  onChange={(e) => setConfirmPwd(e.target.value)}
                  data-testid="profile-confirm-password"
                />
              </div>
              {error && (
                <div
                  className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive"
                  data-testid="profile-password-error"
                >
                  {error}
                </div>
              )}
              <Button type="submit" disabled={saving} data-testid="profile-password-submit">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Simpan kata sandi
              </Button>
            </form>
          </Card>
        </div>
      </PageBody>
    </>
  );
};

export default ProfilePage;
