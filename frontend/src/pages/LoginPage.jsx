import React, { useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CalendarCheck2,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  PowerOff,
  ShieldCheck,
  UsersRound,
  WalletCards,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import { brandTitle, PlatformLogo, useBranding } from "@/lib/branding";
import { errorMessage, FLASH_KEY } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const REMEMBER_KEY = "kk_remember_email";

// Feature cards HRIS pada panel hero (konten produk, bukan data).
const FEATURES = [
  { icon: UsersRound, title: "Data karyawan terpusat", desc: "Profil, kontrak, dokumen, dan struktur organisasi dalam satu sumber." },
  { icon: CalendarCheck2, title: "Absensi, cuti & lembur", desc: "Kehadiran berbasis lokasi dan persetujuan berjenjang yang tercatat." },
  { icon: WalletCards, title: "Payroll & PPh 21", desc: "Perhitungan gaji, BPJS, dan PPh 21 TER beserta slip gaji karyawan." },
  { icon: ShieldCheck, title: "Aman per perusahaan", desc: "Data setiap tenant terpisah dan hak akses diverifikasi di server." },
];

const homeFor = (data) => (data?.is_super_admin ? "/platform" : "/");

const BLOCK_COPY = {
  inactive: {
    icon: PowerOff,
    title: "Akses tenant sedang dinonaktifkan",
    hint: "Data perusahaan Anda tetap aman dan tidak dihapus. Hubungi administrator platform untuk mengaktifkan kembali.",
  },
  expired: {
    icon: Lock,
    title: "Masa layanan tenant telah berakhir",
    hint: "Masa layanan dan masa tenggang sudah habis. Hubungi administrator platform untuk memperpanjang layanan; data Anda tetap tersimpan.",
  },
};

const LoginPage = () => {
  const { login, session, loading } = useAuth();
  const { branding } = useBranding();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState(() => {
    try {
      return localStorage.getItem(REMEMBER_KEY) || "";
    } catch {
      return "";
    }
  });
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(() => {
    try {
      return !!localStorage.getItem(REMEMBER_KEY);
    } catch {
      return false;
    }
  });
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  const [blocked, setBlocked] = useState(null); // { reason, message }
  const [error, setError] = useState(() => {
    // Pesan dari sesi yang diakhiri karena tenant dinonaktifkan / masa layanan berakhir.
    try {
      const flash = sessionStorage.getItem(FLASH_KEY);
      if (flash) sessionStorage.removeItem(FLASH_KEY);
      return flash || "";
    } catch {
      return "";
    }
  });

  useEffect(() => {
    document.title = brandTitle(branding, "Masuk");
  }, [branding]);

  if (!loading && session) {
    if (session.user?.must_change_password) return <Navigate to="/change-password" replace />;
    return <Navigate to={session.is_super_admin ? "/platform" : "/"} replace />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setBlocked(null);
    if (!email.trim() || !password) {
      setError("Email dan kata sandi wajib diisi untuk masuk.");
      return;
    }
    setSubmitting(true);
    try {
      const data = await login(email.trim(), password);
      try {
        if (remember) localStorage.setItem(REMEMBER_KEY, email.trim());
        else localStorage.removeItem(REMEMBER_KEY);
      } catch {
        /* ignore */
      }
      if (data.user?.must_change_password) {
        navigate("/change-password", { replace: true });
        return;
      }
      toast.success(`Selamat datang, ${data.user?.full_name?.split(" ")[0] || "Pengguna"}!`, {
        description: data.is_super_admin
          ? "Anda masuk ke Konsol Platform."
          : data.active_company?.name
            ? `Perusahaan aktif: ${data.active_company.name}`
            : undefined,
      });
      const from = location.state?.from;
      const target = data.is_super_admin ? (from && from.startsWith("/platform") ? from : homeFor(data)) : from && !from.startsWith("/platform") ? from : "/";
      navigate(target, { replace: true });
    } catch (err) {
      const reason = err?.response?.headers?.["x-tenant-status"];
      if (err?.response?.status === 403 && (reason === "inactive" || reason === "expired")) {
        setBlocked({ reason, message: errorMessage(err) });
      } else {
        setError(errorMessage(err, "Tidak dapat masuk. Periksa email dan kata sandi Anda."));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const block = blocked ? BLOCK_COPY[blocked.reason] : null;
  const BlockIcon = block?.icon;

  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]" data-testid="login-page">
      {/* Kolom kiri: hero branding platform */}
      <section
        className="login-accent relative hidden flex-col justify-between overflow-hidden p-10 text-white lg:flex xl:p-14"
        data-testid="login-hero"
      >
        <div className="login-hero-grid pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="relative">
          <PlatformLogo size="lg" inverse testId="login-hero-logo" />
        </div>

        <div className="relative max-w-xl space-y-8">
          <div className="space-y-4">
            <h2 className="text-[30px] font-semibold leading-[1.2] tracking-[-0.02em] xl:text-[34px]" data-testid="login-hero-headline">
              {branding.login_headline}
            </h2>
            <p className="max-w-lg text-[15px] leading-relaxed text-white/80" data-testid="login-hero-text">
              {branding.login_supporting_text}
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2" data-testid="login-feature-cards">
            {FEATURES.map(({ icon: Icon, title, desc }, i) => (
              <div
                key={title}
                className="rounded-xl border border-white/15 bg-white/[0.07] p-4 backdrop-blur-sm"
                data-testid={`login-feature-card-${i}`}
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15">
                  <Icon className="h-4 w-4" strokeWidth={2} />
                </span>
                <p className="mt-3 text-sm font-semibold">{title}</p>
                <p className="mt-1 text-[13px] leading-snug text-white/70">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-xs text-white/60" data-testid="login-hero-tagline">
          {branding.tagline}
        </p>
      </section>

      {/* Kolom kanan: form login */}
      <section className="flex items-center justify-center px-5 py-10 sm:px-10">
        <div className="w-full max-w-[400px] space-y-7">
          <div className="lg:hidden">
            <PlatformLogo size="md" testId="login-mobile-logo" />
          </div>

          <div className="space-y-1.5">
            <h1 className="text-[22px] font-semibold tracking-[-0.015em] text-ink-1" data-testid="login-title">
              Masuk ke {branding.app_name}
            </h1>
            <p className="text-sm text-muted-foreground">Gunakan email dan kata sandi akun perusahaan Anda.</p>
          </div>

          {block && (
            <div
              className={`rounded-xl border px-4 py-3 ${blocked.reason === "expired" ? "border-danger-border bg-danger-soft" : "border-warning-border bg-warning-soft"}`}
              role="alert"
              data-testid={`login-blocked-${blocked.reason}`}
            >
              <div className="flex gap-3">
                <BlockIcon className={`mt-0.5 h-5 w-5 shrink-0 ${blocked.reason === "expired" ? "text-danger" : "text-warning"}`} />
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-ink-1">{block.title}</p>
                  <p className="text-[13px] text-ink-2" data-testid="login-blocked-message">{blocked.message}</p>
                  <p className="text-xs text-ink-3">{block.hint}</p>
                </div>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" data-testid="login-form" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="nama@perusahaan.co.id"
                className="h-11"
                data-testid="login-email-input"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <button
                  type="button"
                  onClick={() => setForgotOpen(true)}
                  className="rounded text-[13px] font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  data-testid="login-forgot-password"
                >
                  Lupa Password?
                </button>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Masukkan password"
                  className="h-11 pr-11"
                  data-testid="login-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Sembunyikan password" : "Tampilkan password"}
                  data-testid="login-toggle-password"
                  className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <label className="flex w-fit cursor-pointer items-center gap-2 text-sm text-ink-2" htmlFor="remember">
              <Checkbox
                id="remember"
                checked={remember}
                onCheckedChange={(v) => setRemember(v === true)}
                data-testid="login-remember-checkbox"
              />
              Ingat Saya
            </label>

            {error && (
              <div
                className="flex items-start gap-2 rounded-lg border border-danger-border bg-danger-soft px-3 py-2 text-sm text-destructive"
                role="alert"
                data-testid="login-error"
              >
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" className="h-11 w-full text-[15px]" disabled={submitting} data-testid="login-submit">
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Masuk
            </Button>
          </form>

          <p className="text-xs text-ink-3" data-testid="login-footer">
            © {new Date().getFullYear()} {branding.app_name}
            {branding.subtitle ? ` — ${branding.subtitle}` : ""}
          </p>
        </div>
      </section>

      <Dialog open={forgotOpen} onOpenChange={setForgotOpen}>
        <DialogContent className="bg-card sm:max-w-md" data-testid="forgot-password-dialog">
          <DialogHeader>
            <DialogTitle className="text-base">Lupa Password</DialogTitle>
            <DialogDescription>
              Demi keamanan, password direset oleh administrator. Hubungi Tenant Admin perusahaan Anda
              {branding.support_contact ? ` atau ${branding.support_contact}` : ""}. Anda akan menerima password
              sementara yang wajib diganti setelah login.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button onClick={() => setForgotOpen(false)} data-testid="forgot-password-close">
              Mengerti
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LoginPage;
