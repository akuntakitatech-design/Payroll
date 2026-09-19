import React, { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Building2, Eye, EyeOff, Loader2, ShieldCheck, Users, Layers } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";

const DEMO_ACCOUNTS = [
  { email: "superadmin@hris.id", label: "Super Admin", desc: "Akses seluruh perusahaan" },
  { email: "hr.multi@hris.id", label: "HR Multi Perusahaan", desc: "Uji pemilih perusahaan" },
  { email: "hr.admin@nep.co.id", label: "HR Admin", desc: "Kelola master data" },
  { email: "finance@nep.co.id", label: "Finance", desc: "Payroll & keuangan" },
  { email: "karyawan@nep.co.id", label: "Karyawan", desc: "Akses terbatas" },
];

const DEMO_PASSWORD = "Hris#2026";

const LoginPage = () => {
  const { login, session, loading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    document.title = "Masuk · HRIS & Payroll Suite";
  }, []);

  if (!loading && session) return <Navigate to="/" replace />;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!email.trim() || !password) {
      setError("Email dan kata sandi wajib diisi untuk masuk.");
      return;
    }
    setSubmitting(true);
    try {
      const data = await login(email.trim(), password);
      toast.success(`Selamat datang, ${data.user?.full_name?.split(" ")[0] || "Pengguna"}!`, {
        description: data.active_company?.name
          ? `Perusahaan aktif: ${data.active_company.name}`
          : undefined,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Tidak dapat masuk. Periksa email dan kata sandi Anda."));
    } finally {
      setSubmitting(false);
    }
  };

  const fillDemo = (demoEmail) => {
    setEmail(demoEmail);
    setPassword(DEMO_PASSWORD);
    setError("");
  };

  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-2">
      {/* Brand panel */}
      <div className="login-accent hidden flex-col justify-between p-10 text-white lg:flex">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/15">
            <Building2 className="h-5 w-5" />
          </span>
          <div>
            <p className="text-section-title">HRIS &amp; Payroll Suite</p>
            <p className="text-sm text-white/70">Platform HR multi-perusahaan</p>
          </div>
        </div>

        <div className="max-w-md space-y-6">
          <h2 className="text-2xl font-semibold leading-snug">
            Proses bisnis boleh rumit, pengalaman pengguna harus tetap sederhana.
          </h2>
          <div className="space-y-4">
            {[
              { icon: Layers, title: "Multi perusahaan sejak hari pertama", desc: "Data tiap perusahaan terpisah rapi dan tidak pernah tercampur." },
              { icon: ShieldCheck, title: "Hak akses berbasis peran", desc: "Setiap tindakan diverifikasi di server, bukan hanya disembunyikan di layar." },
              { icon: Users, title: "Input sekali, pakai di mana-mana", desc: "Master data terpusat menjadi fondasi semua modul HR berikutnya." },
            ].map(({ icon: Icon, title, desc }) => (
              <div key={title} className="flex gap-3">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/15">
                  <Icon className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold">{title}</p>
                  <p className="text-sm text-white/70">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs text-white/60">
          Fase 1 — Fondasi: autentikasi, struktur organisasi, hak akses, konfigurasi, audit.
        </p>
      </div>

      {/* Form panel */}
      <div className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-md space-y-6">
          <div className="space-y-2 lg:hidden">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Building2 className="h-5 w-5" />
            </span>
            <p className="text-section-title">HRIS &amp; Payroll Suite</p>
          </div>

          <div className="space-y-1.5">
            <h1 className="text-xl font-semibold tracking-tight">Masuk ke akun Anda</h1>
            <p className="text-sm text-muted-foreground">
              Gunakan email kantor dan kata sandi yang diberikan administrator HR.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4" data-testid="login-form">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="nama@perusahaan.co.id"
                data-testid="login-email-input"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Kata Sandi</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Masukkan kata sandi"
                  className="pr-10"
                  data-testid="login-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Sembunyikan kata sandi" : "Tampilkan kata sandi"}
                  data-testid="login-toggle-password"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div
                className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive"
                data-testid="login-error"
              >
                {error}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={submitting} data-testid="login-submit">
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Masuk
            </Button>
          </form>

          <Card className="border-border bg-card p-4" data-testid="login-demo-accounts">
            <p className="text-sm font-semibold">Akun demo</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Klik salah satu untuk mengisi form. Kata sandi semua akun demo:{" "}
              <span className="font-medium text-foreground">{DEMO_PASSWORD}</span>
            </p>
            <div className="mt-3 space-y-1.5">
              {DEMO_ACCOUNTS.map((acc) => (
                <button
                  key={acc.email}
                  type="button"
                  onClick={() => fillDemo(acc.email)}
                  data-testid={`login-demo-${acc.email}`}
                  className="flex w-full items-center justify-between gap-2 rounded-lg border border-border bg-background px-3 py-2 text-left transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{acc.label}</span>
                    <span className="block truncate text-xs text-muted-foreground">{acc.email}</span>
                  </span>
                  <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">{acc.desc}</span>
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
