import React, { useCallback, useEffect, useState } from "react";
import { Eye, FileText, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import DataTable, { FilterBar, FilterSelect, Pagination, RowActions, TableCard } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { BAST_TYPE_LABEL, BastPdfActions, SnapshotView, StateBadge, employeeLabel } from "@/pages/asset/assetLifecycleShared";

// Phase 2A CP2 - Dokumen BAST gabungan (Penyerahan + Pengembalian). Detail & PDF dibaca dari snapshot terbit.

const AssetBastPage = () => {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ bast_type: "", date_from: "", date_to: "" });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [detail, setDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const params = { page, limit, q: search || undefined };
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
      const { data } = await api.get("/asset-basts", { params });
      setRows(data.items);
      setTotal(data.total);
    } catch (e) {
      setLoadError(errorMessage(e, "Daftar BAST gagal dimuat."));
    } finally {
      setLoading(false);
    }
  }, [page, limit, search, filters]);

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, search]);

  const openDetail = async (row) => {
    try {
      setDetail((await api.get(`/asset-basts/${row.id}`)).data);
    } catch (e) {
      toast.error(errorMessage(e, "Detail BAST gagal dimuat."));
    }
  };

  const setFilter = (k) => (v) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(1);
  };
  const hasFilters = !!(search || filters.bast_type || filters.date_from || filters.date_to);

  const columns = [
    { key: "system_number", header: "Nomor Sistem", render: (r) => <span className="font-medium tabular-nums" data-testid={`bast-number-${r.id}`}>{r.system_number}</span> },
    { key: "bast_type", header: "Tipe", render: (r) => <Badge variant="outline" className="whitespace-nowrap">{BAST_TYPE_LABEL[r.bast_type] || r.bast_type}</Badge> },
    { key: "manual_number", header: "No. Referensi", hideOnMobile: true, render: (r) => r.manual_number || "-" },
    { key: "bast_date", header: "Tanggal", render: (r) => formatDate(r.bast_date) },
    { key: "employee_name", header: "Karyawan", render: (r) => employeeLabel({ full_name: r.employee_name, employee_number: r.employee_number }) },
    { key: "project_name", header: "Project", hideOnMobile: true, render: (r) => r.project_name || "-" },
    { key: "item_count", header: "Aset", align: "right", render: (r) => <span className="tabular-nums">{r.item_count}</span> },
    { key: "doc_state", header: "Status", render: (r) => <StateBadge state={r.doc_state} /> },
    { key: "actions", header: "", align: "right", render: (r) => (
      <RowActions testId={`bast-row-actions-${r.id}`} actions={[{ key: "view", label: "Lihat detail", icon: Eye, onSelect: () => openDetail(r), testId: `bast-view-${r.id}` }]} />
    ) },
  ];

  return (
    <PageBody className="space-y-4">
      <div className="space-y-4" data-testid="asset-bast-page">
        <SectionHeader title="Dokumen BAST" description="Seluruh BAST Penyerahan dan Pengembalian yang sudah terbit. PDF dibuat langsung dari isi dokumen saat terbit." />
        <FilterBar search={search} onSearchChange={(v) => { setSearch(v); setPage(1); }} searchPlaceholder="Cari nomor sistem, nomor referensi, atau karyawan…"
          showReset={hasFilters} onReset={() => { setSearch(""); setFilters({ bast_type: "", date_from: "", date_to: "" }); setPage(1); }}>
          <FilterSelect label="Tipe" value={filters.bast_type} onChange={setFilter("bast_type")} allLabel="Semua tipe" testId="bast-filter-type"
            options={[{ value: "HANDOVER", label: "Penyerahan" }, { value: "RETURN", label: "Pengembalian" }]} />
          <div className="space-y-1">
            <Label className="text-[12px] font-medium text-muted-foreground">Dari tanggal</Label>
            <Input type="date" className="h-9 w-[10rem]" value={filters.date_from} onChange={(e) => setFilter("date_from")(e.target.value)} data-testid="bast-filter-date-from" />
          </div>
          <div className="space-y-1">
            <Label className="text-[12px] font-medium text-muted-foreground">Sampai tanggal</Label>
            <Input type="date" className="h-9 w-[10rem]" value={filters.date_to} onChange={(e) => setFilter("date_to")(e.target.value)} data-testid="bast-filter-date-to" />
          </div>
        </FilterBar>
        <TableCard>
          {loadError && !loading ? (
            <EmptyState testId="bast-list-error" icon={RefreshCw} title="Daftar BAST gagal dimuat" description={loadError} actionLabel="Coba lagi" onAction={load} />
          ) : (
            <>
              <DataTable testId="bast-table" columns={columns} rows={rows} loading={loading} onRowClick={openDetail}
                emptyProps={{ icon: FileText, testId: "bast-list-empty", title: hasFilters ? "Tidak ada BAST yang cocok" : "Belum ada BAST terbit",
                  description: hasFilters ? "Ubah kata kunci atau filter." : "BAST terbit otomatis saat penyerahan atau pengembalian dipublish." }} />
              <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / limit))} total={total} limit={limit} onPageChange={setPage}
                onLimitChange={(v) => { setLimit(v); setPage(1); }} />
            </>
          )}
        </TableCard>
      </div>
      <Sheet open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl" data-testid="bast-detail-sheet">
          {detail && (
            <div className="space-y-5">
              <SheetHeader>
                <SheetTitle className="flex flex-wrap items-center gap-2">{detail.system_number}
                  <Badge variant="outline">{BAST_TYPE_LABEL[detail.bast_type]}</Badge></SheetTitle>
                <SheetDescription>No. referensi terkini: {detail.manual_number || "-"}</SheetDescription>
              </SheetHeader>
              <BastPdfActions bastId={detail.id} systemNumber={detail.system_number} testIdPrefix="bast-detail" />
              <SnapshotView snapshot={detail.snapshot} testId="bast-detail-snapshot" />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </PageBody>
  );
};

export default AssetBastPage;
