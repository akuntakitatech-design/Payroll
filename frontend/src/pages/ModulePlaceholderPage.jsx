import React, { useEffect } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowRight, CheckCircle2, Clock, Layers, Lock } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { MODULE_INFO } from "@/lib/nav";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const ModulePlaceholderPage = () => {
  const { moduleKey } = useParams();
  const { hasModule } = useAuth();
  const info = MODULE_INFO[moduleKey];
  const active = hasModule(moduleKey);
  const Icon = info?.icon || Layers;

  useEffect(() => {
    document.title = `${info?.name || "Modul"} · HRIS Suite`;
  }, [info?.name]);

  if (moduleKey === "employee_core" && active) {
    return <Navigate to="/employees" replace />;
  }

  if (!info) {
    return (
      <PageBody>
        <Card className="border-border bg-card p-8 text-center">
          <p className="text-section-title">Modul tidak dikenal</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Kembali ke dashboard untuk melihat daftar modul yang tersedia.
          </p>
          <Button asChild className="mt-4">
            <Link to="/">Ke Dashboard</Link>
          </Button>
        </Card>
      </PageBody>
    );
  }

  return (
    <>
      <PageHeader
        title={info.name}
        subtitle={info.summary}
        actions={
          <Badge variant={active ? "secondary" : "outline"} className="h-8 px-3 text-sm">
            {active ? "Modul aktif" : "Modul belum diaktifkan"}
          </Badge>
        }
      />
      <PageBody>
        <div className="grid gap-4 lg:grid-cols-3" data-testid="placeholder-module-page">
          <Card className="border-border bg-card p-5 lg:col-span-2">
            <div className="flex items-center gap-2 text-primary">
              <Clock className="h-4 w-4" />
              <p className="text-sm font-semibold">Akan hadir di fase berikutnya</p>
            </div>
            <h2 className="mt-2 text-section-title">
              Fungsi operasional {info.name} belum diaktifkan pada fase Fondasi
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              Fase ini fokus pada fondasi: struktur perusahaan, hak akses, master data, kebijakan,
              alur persetujuan, dan audit. Agar tidak menyesatkan, kami tidak menampilkan angka atau
              transaksi simulasi di halaman ini.
            </p>

            <div className="mt-4 space-y-2 rounded-lg border border-border bg-background p-4">
              <p className="text-sm font-semibold">Yang akan tersedia</p>
              <ul className="space-y-1.5">
                {info.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-muted-foreground">
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--severity-success))]" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </div>

            <Button disabled className="mt-4" data-testid="placeholder-module-primary-cta">
              <Lock className="mr-2 h-4 w-4" /> Belum tersedia
            </Button>
          </Card>

          <Card className="border-border bg-card p-5">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary text-secondary-foreground">
              <Icon className="h-5 w-5" />
            </span>
            <h3 className="mt-3 text-section-title">Siapkan sekarang</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Agar modul ini langsung bisa dipakai saat dirilis, lengkapi dulu hal berikut:
            </p>
            <div className="mt-3 space-y-2">
              {[
                { to: "/setup", label: "Lengkapi master data", desc: "Struktur organisasi & data referensi" },
                { to: "/setup/policies", label: "Atur kebijakan", desc: "Aturan per perusahaan/cabang/proyek" },
                { to: "/setup/approval-workflows", label: "Tentukan alur persetujuan", desc: "Siapa menyetujui apa" },
                { to: "/users", label: "Atur pengguna & hak akses", desc: "Siapa boleh melakukan apa" },
              ].map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className="flex items-start gap-2 rounded-lg border border-border bg-background px-3 py-2 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <ArrowRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{item.label}</span>
                    <span className="block text-xs text-muted-foreground">{item.desc}</span>
                  </span>
                </Link>
              ))}
            </div>
          </Card>
        </div>
      </PageBody>
    </>
  );
};

export default ModulePlaceholderPage;
