import React from "react";
import { Search, X, Loader2, MoreHorizontal } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import EmptyState from "./EmptyState";
import { cn } from "@/lib/utils";

export const FilterSelect = ({ label, value, onChange, options, placeholder, testId, allLabel = "Semua" }) => (
  <div className="min-w-[9.5rem] space-y-1">
    {label && <p className="text-[12px] font-medium text-muted-foreground">{label}</p>}
    <Select value={value || "__all__"} onValueChange={(v) => onChange(v === "__all__" ? "" : v)}>
      <SelectTrigger className="h-9" data-testid={testId}>
        <SelectValue placeholder={placeholder || allLabel} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__all__">{allLabel}</SelectItem>
        {options.map((opt) => (
          <SelectItem key={opt.value} value={opt.value}>
            {opt.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  </div>
);

/**
 * Baris pencarian & filter standar. Kompak, dengan jumlah filter aktif
 * agar pengguna tahu mengapa daftar terlihat lebih sedikit.
 */
export const FilterBar = ({
  search,
  onSearchChange,
  searchPlaceholder = "Cari…",
  children,
  onReset,
  showReset,
  activeFilterCount,
  className,
}) => (
  <div
    className={cn(
      "flex flex-col gap-3 rounded-lg border border-border bg-card p-3 sm:flex-row sm:flex-wrap sm:items-end",
      className
    )}
    data-testid="filter-bar"
  >
    <div className="min-w-[12rem] flex-1 space-y-1">
      <p className="text-[12px] font-medium text-muted-foreground">Pencarian</p>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={searchPlaceholder}
          className="h-9 pl-8"
          data-testid="table-search-input"
        />
      </div>
    </div>
    {children}
    {showReset && (
      <div className="flex items-center gap-2 self-end">
        {activeFilterCount > 0 && (
          <span className="text-[12px] text-muted-foreground" data-testid="active-filter-count">
            Filter ({activeFilterCount})
          </span>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
          className="h-9 gap-1.5 text-muted-foreground"
          data-testid="table-filter-reset-button"
        >
          <X className="h-3.5 w-3.5" /> Reset filter
        </Button>
      </div>
    )}
  </div>
);

export const Pagination = ({ page, totalPages, total, limit, onPageChange, onLimitChange }) => (
  <div className="flex flex-col gap-3 border-t border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
    <p className="text-[12px] text-muted-foreground" data-testid="pagination-summary">
      Menampilkan {total === 0 ? 0 : (page - 1) * limit + 1}–{Math.min(page * limit, total)} dari{" "}
      <span data-numeric="true">{total}</span> data
    </p>
    <div className="flex items-center gap-2">
      <Select value={String(limit)} onValueChange={(v) => onLimitChange(Number(v))}>
        <SelectTrigger className="h-8 w-[7.5rem]" data-testid="pagination-limit">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {[10, 20, 50, 100].map((n) => (
            <SelectItem key={n} value={String(n)}>
              {n} / halaman
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        variant="outline"
        size="sm"
        className="h-8"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        data-testid="pagination-prev"
      >
        Sebelumnya
      </Button>
      <span className="text-[12px] text-muted-foreground" data-numeric="true" data-testid="pagination-page">
        {page} / {totalPages || 1}
      </span>
      <Button
        variant="outline"
        size="sm"
        className="h-8"
        disabled={page >= (totalPages || 1)}
        onClick={() => onPageChange(page + 1)}
        data-testid="pagination-next"
      >
        Berikutnya
      </Button>
    </div>
  </div>
);

/** Menu aksi baris (tiga titik) agar tabel tetap bersih. */
export const RowActions = ({ actions = [], testId, label = "Aksi baris" }) => {
  const visible = actions.filter(Boolean);
  if (!visible.length) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          data-testid={testId}
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48" onClick={(e) => e.stopPropagation()}>
        {visible.map((action, index) => (
          <React.Fragment key={action.key || action.label}>
            {action.separatorBefore && index > 0 && <DropdownMenuSeparator />}
            <DropdownMenuItem
              onClick={(e) => {
                e.stopPropagation();
                action.onSelect?.();
              }}
              disabled={action.disabled}
              data-testid={action.testId}
              className={cn(
                "gap-2",
                action.destructive && "text-destructive focus:text-destructive"
              )}
            >
              {action.icon && <action.icon className="h-4 w-4" />}
              {action.label}
            </DropdownMenuItem>
          </React.Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

/** Sel angka: rata kanan + tabular agar mudah dibandingkan. */
export const NumberCell = ({ value, className }) => (
  <span className={cn("block text-right", className)} data-numeric="true">
    {value}
  </span>
);

/**
 * columns: [{ key, header, render(row), className, cellClassName, hideOnMobile, align }]
 * selection (opsional, UI-only): { selected: [], onChange(ids), enabled }
 */
export const DataTable = ({
  columns,
  rows,
  loading,
  rowKey = (r) => r.id,
  emptyProps,
  testId = "data-table",
  onRowClick,
  selection,
  stickyHeader = true,
}) => {
  const selectable = !!selection?.enabled;
  const selected = selection?.selected || [];
  const allIds = (rows || []).map((r) => rowKey(r));
  const allChecked = selectable && allIds.length > 0 && allIds.every((id) => selected.includes(id));

  const toggleAll = (checked) => selection?.onChange?.(checked ? allIds : []);
  const toggleOne = (id, checked) =>
    selection?.onChange?.(checked ? [...selected, id] : selected.filter((x) => x !== id));

  if (loading) {
    return (
      <div className="space-y-2 p-3" data-testid="data-table-loading">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }
  if (!rows?.length) {
    return (
      <div className="p-3">
        <EmptyState {...emptyProps} />
      </div>
    );
  }
  const alignClass = (align) =>
    align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";

  // Di layar kecil tabel berubah menjadi daftar ringkas agar tetap terbaca.
  const primaryCol = columns[0];
  const actionCol = columns.find((c) => c.key === "actions");
  const detailCols = columns.filter(
    (c) => c !== primaryCol && c.key !== "actions" && c.mobile !== false
  );

  return (
    <>
    <div className="divide-y divide-border md:hidden" data-testid={`${testId}-mobile-list`}>
      {rows.map((row) => {
        const id = rowKey(row);
        return (
          <div
            key={id}
            data-testid={`data-table-mobile-row-${id}`}
            className={cn("px-3 py-3", onRowClick && "cursor-pointer active:bg-accent/60")}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                {primaryCol.render ? primaryCol.render(row) : row[primaryCol.key] ?? "-"}
              </div>
              {actionCol && (
                <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
                  {actionCol.render ? actionCol.render(row) : null}
                </div>
              )}
            </div>
            {detailCols.length > 0 && (
              <dl className="mt-2 grid grid-cols-[8.5rem,1fr] gap-x-3 gap-y-1">
                {detailCols.map((col) => (
                  <React.Fragment key={col.key}>
                    <dt className="text-[12px] text-muted-foreground">{col.header}</dt>
                    <dd className="min-w-0 text-[13px]">
                      {col.render ? col.render(row) : row[col.key] ?? "-"}
                    </dd>
                  </React.Fragment>
                ))}
              </dl>
            )}
          </div>
        );
      })}
    </div>
    <div
      className={cn(
        "hidden table-scroll md:block",
        stickyHeader && "table-sticky max-h-[70vh] md:overflow-y-auto"
      )}
    >
      <Table data-testid={testId}>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {selectable && (
              <TableHead className="w-9 pr-0">
                <Checkbox
                  checked={allChecked}
                  onCheckedChange={toggleAll}
                  aria-label="Pilih semua baris"
                  data-testid="data-table-select-all"
                />
              </TableHead>
            )}
            {columns.map((col) => (
              <TableHead
                key={col.key}
                className={cn(
                  "whitespace-nowrap",
                  alignClass(col.align),
                  col.hideOnMobile && "hidden md:table-cell",
                  col.className
                )}
              >
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const id = rowKey(row);
            return (
              <TableRow
                key={id}
                data-testid={`data-table-row-${id}`}
                data-state={selectable && selected.includes(id) ? "selected" : undefined}
                className={cn(onRowClick && "cursor-pointer")}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {selectable && (
                  <TableCell className="w-9 pr-0" onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selected.includes(id)}
                      onCheckedChange={(v) => toggleOne(id, v)}
                      aria-label="Pilih baris"
                      data-testid={`data-table-select-${id}`}
                    />
                  </TableCell>
                )}
                {columns.map((col) => (
                  <TableCell
                    key={col.key}
                    className={cn(
                      alignClass(col.align),
                      col.hideOnMobile && "hidden md:table-cell",
                      col.cellClassName
                    )}
                  >
                    {col.render ? col.render(row) : row[col.key] ?? "-"}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
    </>
  );
};

/** Bar aksi massal — tampil saat ada baris terpilih. */
export const BulkActionBar = ({ count, onClear, children }) => {
  if (!count) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-3 border-b border-border bg-primary-soft px-3 py-2"
      data-testid="bulk-action-bar"
    >
      <span className="text-[13px] font-medium text-primary" data-numeric="true">
        {count} baris dipilih
      </span>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto h-8 text-muted-foreground"
        onClick={onClear}
        data-testid="bulk-action-clear"
      >
        Batalkan pilihan
      </Button>
    </div>
  );
};

export const TableCard = ({ children, className }) => (
  <div className={cn("overflow-hidden rounded-lg border border-border bg-card", className)}>
    {children}
  </div>
);

export const InlineLoader = ({ label = "Memuat…" }) => (
  <div className="flex items-center gap-2 text-sm text-muted-foreground">
    <Loader2 className="h-4 w-4 animate-spin" /> {label}
  </div>
);

export default DataTable;
