import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Network,
  MapPin,
  Layers,
  GitBranch,
  BriefcaseBusiness,
  BadgeCheck,
  Wallet,
  FolderKanban,
  IdCard,
  FileSignature,
  Award,
  FileText,
  Boxes,
  SlidersHorizontal,
  Settings,
  ArrowRight,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { Card } from "@/components/ui/card";

const SECTIONS = [
  {
    key: "master",
    title: "1. Master Data",
    description:
      "Data induk yang dipakai berulang di semua modul. Isi sekali di sini, lalu dipakai di mana-mana.",
    items: [
      { to: "/setup/branches", label: "Cabang", icon: Network, resource: "branch", desc: "Kantor pusat dan cabang perusahaan" },
      { to: "/setup/work-locations", label: "Lokasi Kerja", icon: MapPin, resource: "work_location", desc: "Kantor, site proyek, gudang" },
      { to: "/setup/departments", label: "Departemen", icon: Layers, resource: "department", desc: "Struktur departemen" },
      { to: "/setup/divisions", label: "Divisi", icon: GitBranch, resource: "division", desc: "Unit di bawah departemen" },
      { to: "/setup/positions", label: "Jabatan", icon: BriefcaseBusiness, resource: "position", desc: "Jabatan dan garis pelaporan" },
      { to: "/setup/job-grades", label: "Grade / Level", icon: BadgeCheck, resource: "job_grade", desc: "Tingkatan dan rentang gaji" },
      { to: "/setup/cost-centers", label: "Cost Center", icon: Wallet, resource: "cost_center", desc: "Pusat pembebanan biaya" },
      { to: "/setup/projects", label: "Proyek", icon: FolderKanban, resource: "project", desc: "Proyek dan kontrak klien" },
      { to: "/setup/employment-statuses", label: "Status Kepegawaian", icon: IdCard, resource: "employment_status", desc: "PKWTT, PKWT, harian, magang" },
      { to: "/setup/contract-types", label: "Tipe Kontrak", icon: FileSignature, resource: "contract_type", desc: "Durasi dan perpanjangan kontrak" },
      { to: "/setup/certification-types", label: "Tipe Sertifikasi", icon: Award, resource: "certification_type", desc: "Sertifikat wajib dan masa berlaku" },
      { to: "/setup/document-types", label: "Tipe Dokumen", icon: FileText, resource: "document_type", desc: "CV, KTP, ijazah, kontrak, kwitansi" },
    ],
  },
  {
    key: "policy",
    title: "2. Kebijakan Perusahaan",
    description:
      "Aturan yang dapat diwariskan: Perusahaan → Cabang → Divisi → Proyek → Karyawan. Aturan paling spesifik yang berlaku.",
    items: [
      { to: "/setup/policies", label: "Kebijakan & Override", icon: SlidersHorizontal, resource: "policy", desc: "Absensi, cuti, lembur, payroll, kontrak, persetujuan" },
      { to: "/setup/approval-workflows", label: "Alur Persetujuan", icon: GitBranch, resource: "approval_workflow", desc: "Tentukan siapa menyetujui apa, berjenjang" },
    ],
  },
  {
    key: "system",
    title: "3. Konfigurasi Sistem",
    description: "Pengaturan teknis dan langganan modul untuk perusahaan aktif.",
    items: [
      { to: "/setup/modules", label: "Aktivasi Modul", icon: Boxes, resource: "module", desc: "Nyalakan hanya modul yang dipakai" },
      { to: "/settings", label: "Pengaturan Sistem", icon: Settings, resource: "settings", desc: "Format tanggal, NIK otomatis, keamanan" },
    ],
  },
];

const SetupHubPage = () => {
  const { can } = useAuth();

  useEffect(() => {
    document.title = "Pusat Setup · HRIS Suite";
  }, []);

  return (
    <>
      <PageHeader
        title="Pusat Setup"
        subtitle="Konfigurasi perusahaan dikelompokkan agar mudah diikuti berurutan."
      />
      <PageBody>
        {SECTIONS.map((section) => {
          const items = section.items.filter((i) => can(i.resource, "view"));
          if (!items.length) return null;
          return (
            <section key={section.key} className="space-y-3" data-testid={`setup-section-${section.key}`}>
              <div>
                <h2 className="text-section-title">{section.title}</h2>
                <p className="max-w-3xl text-sm text-muted-foreground">{section.description}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Card key={item.to} className="border-border bg-card p-0">
                      <Link
                        to={item.to}
                        data-testid={`setup-link-${item.to.replace(/\//g, "-")}`}
                        className="flex items-start gap-3 rounded-lg p-4 transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-secondary-foreground">
                          <Icon className="h-4 w-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-1.5 text-sm font-semibold">
                            {item.label}
                            <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                          </span>
                          <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                            {item.desc}
                          </span>
                        </span>
                      </Link>
                    </Card>
                  );
                })}
              </div>
            </section>
          );
        })}
      </PageBody>
    </>
  );
};

export default SetupHubPage;
