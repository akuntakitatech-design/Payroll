import React from "react";
import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageBody } from "@/components/common/PageHeader";

const NotFoundPage = () => (
  <PageBody>
    <Card className="border-border bg-card px-6 py-16 text-center" data-testid="not-found-page">
      <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
        <Compass className="h-6 w-6" />
      </span>
      <h1 className="mt-4 text-page-title font-semibold">Halaman tidak ditemukan</h1>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        Alamat yang Anda buka tidak tersedia, atau Anda tidak memiliki akses ke halaman tersebut pada
        perusahaan aktif ini.
      </p>
      <Button asChild className="mt-5">
        <Link to="/">Kembali ke Dashboard</Link>
      </Button>
    </Card>
  </PageBody>
);

export default NotFoundPage;
