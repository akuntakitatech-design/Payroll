import React, { useState } from "react";
import { BookmarkPlus, CalendarRange, RotateCcw, SlidersHorizontal, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger,
} from "@/components/ui/sheet";
import {
  ADVANCED_FILTERS, CROSS_FILTERS, FILTER_FIELDS, PERIOD_PRESETS, PRIMARY_FILTERS,
} from "@/lib/dashboardAnalytics";
import { cn } from "@/lib/utils";

const ALL_VALUE = "__all";

const FilterSelect = ({ label, value, onChange, options, testId, className }) => (
  <label className={cn("flex min-w-0 flex-col gap-1", className)}>
    <span className="text-[11px] font-medium uppercase tracking-[0.03em] text-ink-3">{label}</span>
    <Select value={value || ALL_VALUE} onValueChange={(v) => onChange(v === ALL_VALUE ? "" : v)}>
      <SelectTrigger className="h-9 w-full text-[12.5px]" data-testid={testId}>
        <SelectValue placeholder={`Semua ${label.toLowerCase()}`} />
      </SelectTrigger>
      <SelectContent className="max-h-[320px]">
        <SelectItem value={ALL_VALUE}>Semua {label.toLowerCase()}</SelectItem>
        {(options || []).map((opt) => (
          <SelectItem key={opt.id} value={opt.id}>{opt.label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  </label>
);

const DashboardFilters = ({
  options = {},
  filters,
  setFilter,
  onReset,
  preset,
  setPreset,
  custom,
  setCustom,
  saved = [],
  onSave,
  onLoad,
  onDelete,
  activeCount,
  disabled = false,
}) => {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [savedPick, setSavedPick] = useState("");

  const primaryFields = FILTER_FIELDS.filter((f) => PRIMARY_FILTERS.includes(f.key));
  const activeChips = [...FILTER_FIELDS, ...CROSS_FILTERS]
    .filter((f) => filters[f.key])
    .map((f) => ({ ...f, value: filters[f.key] }));

  const labelFor = (field, value) => {
    const list = options[field.optionKey] || [];
    return list.find((o) => o.id === value)?.label || value;
  };

  return (
    <div className="border-b border-border bg-card px-4 py-3 sm:px-6" data-testid="dashboard-filters">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-[0.03em] text-ink-3">Periode</span>
            <Select value={preset} onValueChange={setPreset}>
              <SelectTrigger className="h-9 w-[168px] text-[12.5px]" data-testid="filter-period">
                <CalendarRange className="mr-1.5 h-3.5 w-3.5 text-ink-3" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERIOD_PRESETS.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </label>

          {preset === "custom" && (
            <div className="flex items-end gap-2">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-medium uppercase tracking-[0.03em] text-ink-3">Dari</span>
                <Input
                  type="date"
                  className="h-9 w-[140px] text-[12.5px]"
                  value={custom?.from || ""}
                  onChange={(e) => setCustom((prev) => ({ ...prev, from: e.target.value }))}
                  data-testid="filter-date-from"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-medium uppercase tracking-[0.03em] text-ink-3">Sampai</span>
                <Input
                  type="date"
                  className="h-9 w-[140px] text-[12.5px]"
                  value={custom?.to || ""}
                  onChange={(e) => setCustom((prev) => ({ ...prev, to: e.target.value }))}
                  data-testid="filter-date-to"
                />
              </label>
            </div>
          )}

          {!disabled && primaryFields.map((field) => (
            <FilterSelect
              key={field.key}
              label={field.label}
              value={filters[field.key]}
              onChange={(v) => setFilter(field.key, v)}
              options={options[field.optionKey]}
              testId={`filter-${field.key}`}
              className="w-[190px]"
            />
          ))}

          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            {activeCount > 0 && (
              <Badge variant="secondary" className="h-7 gap-1 px-2 text-[11.5px]" data-testid="filter-active-count">
                {activeCount} filter aktif
              </Badge>
            )}
            {!disabled && (
              <Sheet open={advancedOpen} onOpenChange={setAdvancedOpen}>
                <SheetTrigger asChild>
                  <Button variant="outline" size="sm" className="h-9" data-testid="filter-advanced-open">
                    <SlidersHorizontal className="mr-1.5 h-3.5 w-3.5" />Filter lanjutan
                  </Button>
                </SheetTrigger>
                <SheetContent className="w-full sm:max-w-md">
                  <SheetHeader>
                    <SheetTitle>Filter lanjutan</SheetTitle>
                    <SheetDescription>
                      Semua widget mengikuti filter ini. Filter yang tidak relevan dibiarkan “Semua”.
                    </SheetDescription>
                  </SheetHeader>
                  <div className="mt-4 grid max-h-[62vh] gap-3 overflow-y-auto pr-1">
                    {ADVANCED_FILTERS.map((field) => (
                      <FilterSelect
                        key={field.key}
                        label={field.label}
                        value={filters[field.key]}
                        onChange={(v) => setFilter(field.key, v)}
                        options={options[field.optionKey]}
                        testId={`filter-${field.key}`}
                      />
                    ))}
                  </div>
                  <div className="mt-4 border-t border-border pt-3">
                    <p className="text-[11px] font-medium uppercase tracking-[0.03em] text-ink-3">Filter tersimpan</p>
                    <div className="mt-1.5 flex gap-2">
                      <Input
                        placeholder="Nama filter, mis. Site A bulan ini"
                        value={saveName}
                        onChange={(e) => setSaveName(e.target.value)}
                        className="h-9 text-[12.5px]"
                        data-testid="filter-save-name"
                      />
                      <Button
                        size="sm"
                        className="h-9"
                        disabled={!saveName.trim()}
                        onClick={() => { onSave(saveName.trim()); setSaveName(""); }}
                        data-testid="filter-save"
                      >
                        <BookmarkPlus className="mr-1 h-3.5 w-3.5" />Simpan
                      </Button>
                    </div>
                    {saved.length > 0 && (
                      <div className="mt-2 flex gap-2">
                        <Select value={savedPick} onValueChange={setSavedPick}>
                          <SelectTrigger className="h-9 flex-1 text-[12.5px]" data-testid="filter-saved-list">
                            <SelectValue placeholder="Pilih filter tersimpan" />
                          </SelectTrigger>
                          <SelectContent>
                            {saved.map((item) => <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>)}
                          </SelectContent>
                        </Select>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-9"
                          disabled={!savedPick}
                          onClick={() => onLoad(savedPick)}
                          data-testid="filter-saved-load"
                        >
                          Terapkan
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-9"
                          disabled={!savedPick}
                          onClick={() => { onDelete(savedPick); setSavedPick(""); }}
                          aria-label="Hapus filter tersimpan"
                          data-testid="filter-saved-delete"
                        >
                          <Trash2 className="h-4 w-4 text-danger" />
                        </Button>
                      </div>
                    )}
                  </div>
                </SheetContent>
              </Sheet>
            )}
            <Button variant="ghost" size="sm" className="h-9" onClick={onReset} data-testid="filter-reset">
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />Reset
            </Button>
          </div>
        </div>

        {activeChips.length > 0 && (
          <div className="flex flex-wrap gap-1.5" data-testid="filter-chips">
            {activeChips.map((chip) => (
              <button
                key={chip.key}
                type="button"
                onClick={() => setFilter(chip.key, "")}
                className="inline-flex items-center gap-1 rounded-full border border-primary-border bg-primary-soft px-2 py-0.5 text-[11.5px] font-medium text-primary transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                data-testid={`filter-chip-${chip.key}`}
              >
                {chip.label}: {labelFor(chip, chip.value)}
                <X className="h-3 w-3" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DashboardFilters;
