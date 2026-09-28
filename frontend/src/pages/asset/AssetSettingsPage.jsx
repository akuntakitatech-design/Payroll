import React from "react";
import { Hash } from "lucide-react";

import { PageBody } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import MasterDataPage from "@/pages/MasterDataPage";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";

const SECTIONS = [
  { key: "asset-categories", label: "Kategori" },
  { key: "asset-units", label: "Satuan" },
  { key: "asset-conditions", label: "Kondisi" },
  { key: "asset-statuses", label: "Status" },
];

// Pengaturan Manajemen Aset (CP1): master Kategori, Satuan, Kondisi, Status memakai engine master generik yang sama.
export default function AssetSettingsPage() {
  const { can } = useAuth();

  if (!can("asset_master", "view")) {
    return (
      <PageBody>
        <EmptyState testId="asset-settings-forbidden" title="Tidak ada akses" description="Anda tidak memiliki hak akses melihat pengaturan aset." />
      </PageBody>
    );
  }

  return (
    <PageBody className="space-y-4">
      <Card className="flex items-start gap-3 border-border bg-card p-4" data-testid="asset-code-format-info">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
          <Hash className="h-4 w-4" />
        </span>
        <div className="min-w-0 text-[13px]">
          <p className="font-semibold text-foreground">Kode aset otomatis</p>
          <p className="mt-0.5 text-muted-foreground">
            Bila kode dikosongkan saat menambah aset, sistem membuat kode berurutan per perusahaan dengan format{" "}
            <span className="font-mono font-medium text-foreground">AST-000001</span>. Kode yang diisi manual tetap dipakai apa adanya
            dan tidak pernah ditimpa.
          </p>
        </div>
      </Card>
      <Tabs defaultValue={SECTIONS[0].key} className="space-y-4">
        <TabsList data-testid="asset-settings-tabs">
          {SECTIONS.map((s) => (
            <TabsTrigger key={s.key} value={s.key} data-testid={`asset-settings-tab-${s.key}`}>
              {s.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {SECTIONS.map((s) => (
          <TabsContent key={s.key} value={s.key} className="space-y-4">
            <MasterDataPage resourcePath={s.key} embedded />
          </TabsContent>
        ))}
      </Tabs>
    </PageBody>
  );
}
