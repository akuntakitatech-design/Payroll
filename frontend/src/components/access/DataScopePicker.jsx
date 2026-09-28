import React, { useMemo, useState } from "react";
import { Check, ChevronsUpDown, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

const MODES = [
  {
    value: "ALL_TENANT",
    label: "Semua Data Perusahaan",
    hint: "Dapat melihat seluruh karyawan di perusahaan aktif (sesuai hak akses peran).",
  },
  {
    value: "SELECTED_PROJECTS",
    label: "Project Tertentu",
    hint: "Hanya karyawan yang penempatan aktifnya berada di project terpilih.",
  },
];

/**
 * Upgrade 01I - pemilih Cakupan Data. Murni input; validasi & penegakan ada di backend.
 * props: mode, projectIds, projects [{id,name,code,status}], onChange({mode, projectIds}), disabled, error, testPrefix
 */
export const DataScopePicker = ({
  mode = "ALL_TENANT",
  projectIds = [],
  projects = [],
  onChange,
  disabled = false,
  error,
  fullScopeRole = false,
  testPrefix = "data-scope",
}) => {
  const [open, setOpen] = useState(false);
  const byId = useMemo(() => Object.fromEntries(projects.map((p) => [p.id, p])), [projects]);
  const selected = projectIds.map((id) => byId[id] || { id, name: "(project tidak ditemukan)", missing: true });

  const toggle = (id) =>
    onChange?.({
      mode,
      projectIds: projectIds.includes(id) ? projectIds.filter((x) => x !== id) : [...projectIds, id],
    });

  return (
    <div className="space-y-3 sm:col-span-2" data-testid={`${testPrefix}-picker`}>
      <div className="space-y-1">
        <Label className="text-sm font-medium">Cakupan Data</Label>
        <p className="text-xs text-muted-foreground">
          Menentukan data karyawan mana yang dapat diakses. Aksi yang boleh dilakukan tetap mengikuti peran.
        </p>
      </div>
      {fullScopeRole && (
        <p
          className="rounded-md border border-primary-border bg-primary-soft px-3 py-2 text-xs text-primary"
          data-testid={`${testPrefix}-full-role-note`}
        >
          Pengguna ini memiliki peran Tenant Admin / Pemilik Perusahaan sehingga selalu mendapat Semua Data
          Perusahaan, apa pun pengaturan di bawah.
        </p>
      )}
      <RadioGroup
        value={mode}
        onValueChange={(v) => onChange?.({ mode: v, projectIds })}
        className="grid grid-cols-1 gap-2 sm:grid-cols-2"
        disabled={disabled}
      >
        {MODES.map((m) => (
          <label
            key={m.value}
            htmlFor={`${testPrefix}-mode-${m.value}`}
            className={cn(
              "flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 transition-colors duration-150",
              mode === m.value ? "border-primary bg-primary-soft" : "border-border bg-background hover:bg-accent",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            <RadioGroupItem
              value={m.value}
              id={`${testPrefix}-mode-${m.value}`}
              data-testid={`${testPrefix}-mode-${m.value === "ALL_TENANT" ? "all" : "projects"}`}
              className="mt-0.5"
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-ink-1">{m.label}</span>
              <span className="block text-xs text-muted-foreground">{m.hint}</span>
            </span>
          </label>
        ))}
      </RadioGroup>

      {mode === "SELECTED_PROJECTS" && (
        <div className="space-y-2">
          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="outline"
                role="combobox"
                aria-expanded={open}
                disabled={disabled}
                className="w-full justify-between bg-background font-normal"
                data-testid={`${testPrefix}-project-trigger`}
              >
                <span className="truncate text-sm">
                  {selected.length ? `${selected.length} project dipilih` : "Pilih project…"}
                </span>
                <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[var(--radix-popover-trigger-width)] min-w-[18rem] p-0" align="start">
              <Command>
                <CommandInput placeholder="Cari project…" data-testid={`${testPrefix}-project-search`} />
                <CommandList>
                  <CommandEmpty>Tidak ada project yang cocok.</CommandEmpty>
                  <CommandGroup heading="Project perusahaan aktif">
                    {projects.map((p) => {
                      const on = projectIds.includes(p.id);
                      return (
                        <CommandItem
                          key={p.id}
                          value={`${p.name || ""} ${p.code || ""} ${p.id}`}
                          onSelect={() => toggle(p.id)}
                          data-testid={`${testPrefix}-project-option-${p.id}`}
                          className="flex items-start gap-2"
                        >
                          <Check className={cn("mt-0.5 h-4 w-4 shrink-0", on ? "text-primary opacity-100" : "opacity-0")} />
                          <span className="min-w-0">
                            <span className="block truncate text-sm">{p.name || p.code || p.id}</span>
                            <span className="block text-xs text-muted-foreground">
                              {p.code || "-"}
                              {p.status === "inactive" ? " · nonaktif" : ""}
                            </span>
                          </span>
                        </CommandItem>
                      );
                    })}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>

          {selected.length > 0 ? (
            <div className="flex flex-wrap gap-1.5" data-testid={`${testPrefix}-selected-list`}>
              {selected.map((p) => (
                <span
                  key={p.id}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border py-0.5 pl-2.5 pr-1 text-[12px] font-medium",
                    p.missing ? "border-warning-border bg-warning-soft text-warning" : "border-border bg-muted text-ink-1"
                  )}
                  data-testid={`${testPrefix}-selected-${p.id}`}
                >
                  {p.name || p.code}
                  {!disabled && (
                    <button
                      type="button"
                      onClick={() => toggle(p.id)}
                      aria-label={`Hapus ${p.name || p.code}`}
                      className="rounded-full p-0.5 transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      data-testid={`${testPrefix}-remove-${p.id}`}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-warning" data-testid={`${testPrefix}-no-project-warning`}>
              Belum ada project dipilih — pengguna tidak akan melihat data karyawan apa pun.
            </p>
          )}
        </div>
      )}
      {error && (
        <p className="text-xs text-destructive" data-testid={`${testPrefix}-error`}>
          {error}
        </p>
      )}
    </div>
  );
};
