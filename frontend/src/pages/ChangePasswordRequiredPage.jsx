import React, { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Eye, EyeOff, KeyRound, Loader2, LogOut, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { api, errorMessage } from "@/lib/api";
import { brandTitle, PlatformLogo, useBranding } from "@/lib/branding";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const PasswordField = ({ id, label, value, onChange, autoComplete, testId, hint }) => {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type={show ? "text" : "password"}
          autoComplete={autoComplete}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-11 pr-11"
          data-testid={testId}
        />
        <button
          type="button"
          onClick={() => setShow((v) => !v)}
          aria-label={show ? "Sembunyikan password" : "Tampilkan password"}
          data-testid={`${testId}-toggle`}
          className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
};

/**
 * Wajib ganti password: tampil untuk akun dengan password sementara (akun baru / hasil reset).
 * Backend juga menolak API operasional (403) sampai password diganti.
 */
export default function ChangePasswordRequiredPage() {
  const { session, loading, user, logout, refreshSession } = useAuth();
  const branding = useBranding();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    document.title = brandTitle(branding, "Ganti Password");
  }, [branding]);

  if (loading) return null;
  if (!session) return <Navigate to="/login" replace />;
  if (!user?.must_change_password) return <Navigate to={session.is_super_admin ? "/platform" : "/"} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!current || !next) return setError("Password sementara dan password baru wajib diisi.");
    if (next.length < 8) return setError("Password baru minimal 8 karakter.");
    if (next === current) return setError("Password baru harus berbeda dari password sementara.");
    if (next !== confirmPwd) return setError("Konfirmasi password belum sama dengan password baru.");
    setSaving(true);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      toast.success("Password berhasil diperbarui.", { description: "Selamat bekerja kembali." });
      await refreshSession();
      navigate(session.is_super_admin ? "/platform" : "/", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Password tidak dapat diperbarui."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10" data-testid="change-password-required-page">
      <div className="w-full max-w-[440px] space-y-6">
        <PlatformLogo size="md" testId="change-password-logo" />
        <Card className="space-y-6 border-border bg-card p-6 sm:p-7">
          <div className="space-y-2">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <KeyRound className="h-5 w-5" />
            </span>
            <h1 className="text-[20px] font-semibold tracking-[-0.015em] text-ink-1" data-testid="change-password-title">
              Ganti password sementara
            </h1>
            <p className="text-sm text-muted-foreground">
              Akun <span className="font-medium text-ink-1" data-testid="change-password-email">{user?.email}</span> masih
              memakai password sementara. Buat password baru sebelum menggunakan aplikasi.
            </p>
          </div>

          <form onSubmit={submit} className="space-y-4" noValidate data-testid="change-password-form">
            <PasswordField id="cp-current" label="Password sementara" value={current} onChange={setCurrent}
              autoComplete="current-password" testId="change-password-current-input" />
            <PasswordField id="cp-new" label="Password baru" value={next} onChange={setNext}
              autoComplete="new-password" testId="change-password-new-input" hint="Minimal 8 karakter dan berbeda dari password sementara." />
            <PasswordField id="cp-confirm" label="Konfirmasi password baru" value={confirmPwd} onChange={setConfirmPwd}
              autoComplete="new-password" testId="change-password-confirm-input" />

            {error && (
              <p className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-[13px] text-danger" role="alert" data-testid="change-password-error">
                {error}
              </p>
            )}

            <Button type="submit" className="h-11 w-full" disabled={saving} data-testid="change-password-submit">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
              Simpan password baru
            </Button>
          </form>

          <div className="flex items-center justify-between border-t border-border pt-4 text-xs text-muted-foreground">
            <span>Password lama langsung tidak berlaku setelah diganti.</span>
            <Button variant="ghost" size="sm" onClick={() => logout()} data-testid="change-password-logout">
              <LogOut className="mr-1.5 h-3.5 w-3.5" /> Keluar
            </Button>
          </div>
        </Card>
      </div>
    </main>
  );
}
