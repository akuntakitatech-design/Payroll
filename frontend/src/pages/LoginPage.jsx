import React, { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Building2, Eye, EyeOff, Loader2, ShieldCheck, Users, Layers, ChevronDown, UserRound } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const DEMO_PASSWORD = "Hris#2026";

const DEMO_GROUPS = [
  {
    company: "Akses Global",
    accounts: [
      { email: "superadmin@hris.id", name: "Super Administrator", role: "System Administrator" },
      { email: "hr.multi@hris.id", name: "Laila Fitriani", role: "Group HR Business Partner" },
    ],
  },
  {
    company: "PT Nusantara Energi Prima (NEP)",
    accounts: [
      { email: "owner@nep.co.id", name: "Bapak Hendra Wijaya", role: "Direktur Utama" },
      { email: "hr.manager@nep.co.id", name: "Dewi Kartika", role: "HR Manager" },
      { email: "hr.admin@nep.co.id", name: "Siti Rahmawati", role: "HR Administrator" },
      { email: "finance@nep.co.id", name: "Agus Prasetyo", role: "Finance Manager" },
      { email: "manager@nep.co.id", name: "Rudi Hartono", role: "Operation Manager" },
      { email: "supervisor@nep.co.id", name: "Bambang Setiawan", role: "Site Supervisor" },
      { email: "karyawan@nep.co.id", name: "Rina Kusuma", role: "Staff Administrasi" },
    ],
  },
  {
    company: "PT Karya Bangun Sejahtera (KBS)",
    accounts: [
      { email: "owner@kbs.co.id", name: "Ibu Maria Tanujaya", role: "Direktur" },
      { email: "hr.admin@kbs.co.id", name: "Yusuf Maulana", role: "HR Administrator" },
      { email: "karyawan@kbs.co.id", name: "Andi Saputra", role: "Teknisi" },
    ],
  },
];

const LoginPage = () => {
  const { login, session, loading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [showDemo, setShowDemo] = useState(false);

  useEffect(() => {
    document.title = "Masuk · HRIS & Payroll Suite";
  }, []);

  if (!loading && session) return <Navigate to="/" replace />;

  const fillDemo = (demoEmail) => {
    setEmail(demoEmail);
    setPassword(DEMO_PASSWORD);
    setError("");
    toast.info("Kredensial demo terisi", {
      description: `${demoEmail} · tekan "Masuk" untuk melanjutkan.`,
    });
  };

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

          {/* Demo account picker */}
          <div className="rounded-xl border border-border bg-card">
            <button
              type="button"
              onClick={() => setShowDemo((v) => !v)}
              aria-expanded={showDemo}
              data-testid="demo-accounts-toggle"
              className="flex w-full items-center justify-between rounded-xl px-4 py-3 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="flex items-center gap-2">
                <Users className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium">Coba dengan akun demo</span>
              </span>
              <ChevronDown
                className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${showDemo ? "rotate-180" : ""}`}
              />
            </button>

            {showDemo && (
              <div className="space-y-4 border-t border-border px-4 py-4" data-testid="demo-accounts-panel">
                <p className="text-xs text-muted-foreground">
                  Klik salah satu akun untuk mengisi formulir secara otomatis. Kata sandi semua akun demo:{" "}
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] font-semibold text-foreground">
                    {DEMO_PASSWORD}
                  </span>
                </p>

                <div className="max-h-72 space-y-4 overflow-y-auto pr-1">
                  {DEMO_GROUPS.map((group) => (
                    <div key={group.company} className="space-y-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {group.company}
                      </p>
                      <div className="space-y-1.5">
                        {group.accounts.map((acct) => (
                          <button
                            key={acct.email}
                            type="button"
                            onClick={() => fillDemo(acct.email)}
                            data-testid={`demo-account-${acct.email}`}
                            className="flex w-full items-center gap-3 rounded-lg border border-border bg-background px-3 py-2 text-left transition-colors hover:border-primary/50 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                              <UserRound className="h-4 w-4" />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium text-foreground">{acct.name}</span>
                              <span className="block truncate text-xs text-muted-foreground">{acct.email}</span>
                            </span>
                            <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                              {acct.role}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
};

export default LoginPage;
