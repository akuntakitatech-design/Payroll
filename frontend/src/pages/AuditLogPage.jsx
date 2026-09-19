import React, { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Download, History, Monitor } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import { FilterBar, FilterSelect, Pagination, TableCard } from "@/components/common/DataTable";
import EmptyState from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

const renderVal = (v) => {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Ya" : "Tidak";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
};

const AuditLogPage = () => {
  const { can, company } = useAuth();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 25, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [catalog, setCatalog] = useState({ actions: [], modules: [], resources: [], users: [] });
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filters, setFilters] = useState({ module: "", resource: "", action: "", user_id: "" });
  const [dates, setDates] = useState({ date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(25);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const loadCatalog = useCallback(async () => {
    try {
      const res = await api.get("/audit-logs/catalog");
      setCatalog(res.data);
    } catch {
      /* ignore */
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (debounced) params.q = debounced;
      Object.entries({ ...filters, ...dates }).forEach(([k, v]) => {
        if (v) params[k] = v;
      });
      const res = await api.get("/audit-logs", { params });
      setRows(res.data.items || []);
      setMeta({
        total: res.data.total,
        page: res.data.page,
        limit: res.data.limit,
        total_pages: res.data.total_pages,
      });
    } catch (err) {
      toast.error(errorMessage(err, "Gagal memuat audit log."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [page, limit, debounced, filters, dates]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    loadCatalog();
    document.title = "Audit Log · HRIS Suite";
  }, [loadCatalog, company?.id]);

  const exportLogs = async () => {
    try {
      const res = await api.get("/audit-logs/export", {
        params: { module: filters.module || undefined, action: filters.action || undefined },
      });
      const blob = new Blob([JSON.stringify(res.data.items, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-log-${company?.code || "perusahaan"}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast.success(`${res.data.total} baris audit log berhasil diekspor.`);
    } catch (err) {
      toast.error(errorMessage(err, "Audit log tidak dapat diekspor."));
    }
  };

  const hasFilters =
    !!debounced || Object.values(filters).some(Boolean) || Object.values(dates).some(Boolean);

  return (
    <>
      <PageHeader
        title="Audit Log"
        subtitle="Riwayat perubahan data: siapa mengubah apa dan kapan."
        actions={
          can("audit_log", "export") && (
            <Button variant="outline" onClick={exportLogs} data-testid="audit-export-button">
              <Download className="mr-2 h-4 w-4" /> Ekspor
            </Button>
          )
        }
      />
      <PageBody>
        <FilterBar
          search={search}
          onSearchChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          searchPlaceholder="Cari nama data, pengguna, atau ID…"
          showReset={hasFilters}
          onReset={() => {
            setSearch("");
            setFilters({ module: "", resource: "", action: "", user_id: "" });
            setDates({ date_from: "", date_to: "" });
            setPage(1);
          }}
        >
          <FilterSelect
            label="Modul"
            value={filters.module}
            onChange={(v) => {
              setFilters((p) => ({ ...p, module: v }));
              setPage(1);
            }}
            options={catalog.modules.map((m) => ({ value: m.key, label: m.label }))}
            allLabel="Semua modul"
            testId="filter-module"
          />
          <FilterSelect
            label="Tindakan"
            value={filters.action}
            onChange={(v) => {
              setFilters((p) => ({ ...p, action: v }));
              setPage(1);
            }}
            options={catalog.actions.map((a) => ({ value: a.key, label: a.label }))}
            allLabel="Semua tindakan"
            testId="filter-action"
          />
          <FilterSelect
            label="Pengguna"
            value={filters.user_id}
            onChange={(v) => {
              setFilters((p) => ({ ...p, user_id: v }));
              setPage(1);
            }}
            options={catalog.users.map((u) => ({ value: u.id, label: u.name || u.email }))}
            allLabel="Semua pengguna"
            testId="filter-user"
          />
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Dari Tanggal</p>
            <Input
              type="date"
              className="h-9 bg-card"
              value={dates.date_from}
              onChange={(e) => {
                setDates((p) => ({ ...p, date_from: e.target.value }));
                setPage(1);
              }}
              data-testid="filter-date-from"
            />
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Sampai Tanggal</p>
            <Input
              type="date"
              className="h-9 bg-card"
              value={dates.date_to}
              onChange={(e) => {
                setDates((p) => ({ ...p, date_to: e.target.value }));
                setPage(1);
              }}
              data-testid="filter-date-to"
            />
          </div>
        </FilterBar>

        <TableCard>
          {loading ? (
            <div className="space-y-2 p-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <div className="p-3">
              <EmptyState
                icon={History}
                title="Belum ada aktivitas audit untuk filter ini."
                description="Coba perluas rentang tanggal atau hapus filter yang aktif."
              />
            </div>
          ) : (
            <ul className="divide-y divide-border" data-testid="audit-log-list">
              {rows.map((log) => {
                const isOpen = !!expanded[log.id];
                const hasDiff = log.before_value || log.after_value;
                return (
                  <li key={log.id} data-testid={`audit-log-row-${log.id}`}>
                    <button
                      type="button"
                      onClick={() => setExpanded((p) => ({ ...p, [log.id]: !p[log.id] }))}
                      data-testid={`audit-log-row-expand-${log.id}`}
                      className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {hasDiff ? (
                        isOpen ? (
                          <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                        )
                      ) : (
                        <span className="mt-1 h-4 w-4 shrink-0" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[12px] uppercase tracking-[0.06em] text-muted-foreground">
                            {log.action_label}
                          </span>
                          <span className="text-[13px] font-medium">{log.resource_label}</span>
                          {log.record_label && (
                            <span className="truncate text-[13px] text-muted-foreground">
                              — {log.record_label}
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 text-[12px] text-muted-foreground">
                          {log.user_name || log.user_email} · {formatDateTime(log.created_at)}
                          {log.ip_address ? ` · IP ${log.ip_address}` : ""}
                        </p>
                      </div>
                    </button>

                    {isOpen && hasDiff && (
                      <div
                        className="space-y-3 border-t border-border bg-muted/40 px-3 py-3 sm:pl-10"
                        data-testid={`audit-log-row-diff-${log.id}`}
                      >
                        {log.changed_fields?.length > 0 && (
                          <p className="text-xs text-muted-foreground">
                            Kolom berubah:{" "}
                            <span className="font-medium text-foreground">
                              {log.changed_fields.join(", ")}
                            </span>
                          </p>
                        )}
                        <div className="grid gap-3 sm:grid-cols-2">
                          <div className="rounded-lg border border-border bg-card p-3">
                            <p className="text-[12px] text-muted-foreground">
                              Sebelum
                            </p>
                            <dl className="mt-1.5 space-y-1">
                              {(log.changed_fields?.length
                                ? log.changed_fields
                                : Object.keys(log.before_value || {})
                              ).map((f) => (
                                <div key={f} className="flex justify-between gap-2 text-sm">
                                  <dt className="text-muted-foreground">{f}</dt>
                                  <dd className="max-w-[60%] truncate text-right">
                                    {renderVal(log.before_value?.[f])}
                                  </dd>
                                </div>
                              ))}
                              {!log.before_value && (
                                <p className="text-sm text-muted-foreground">Data baru dibuat.</p>
                              )}
                            </dl>
                          </div>
                          <div className="rounded-lg border border-border bg-accent/50 p-3">
                            <p className="text-[12px] text-muted-foreground">
                              Sesudah
                            </p>
                            <dl className="mt-1.5 space-y-1">
                              {(log.changed_fields?.length
                                ? log.changed_fields
                                : Object.keys(log.after_value || {})
                              ).map((f) => (
                                <div key={f} className="flex justify-between gap-2 text-sm">
                                  <dt className="text-muted-foreground">{f}</dt>
                                  <dd className="max-w-[60%] truncate text-right font-medium">
                                    {renderVal(log.after_value?.[f])}
                                  </dd>
                                </div>
                              ))}
                              {!log.after_value && (
                                <p className="text-sm text-muted-foreground">Data dihapus.</p>
                              )}
                            </dl>
                          </div>
                        </div>
                        {log.user_agent && (
                          <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                            <Monitor className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span className="break-all">{log.user_agent}</span>
                          </p>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {rows.length > 0 && (
            <Pagination
              page={meta.page}
              totalPages={meta.total_pages}
              total={meta.total}
              limit={meta.limit}
              onPageChange={setPage}
              onLimitChange={(v) => {
                setLimit(v);
                setPage(1);
              }}
            />
          )}
        </TableCard>
      </PageBody>
    </>
  );
};

export default AuditLogPage;
