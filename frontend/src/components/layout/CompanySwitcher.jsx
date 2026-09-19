import React, { useState } from "react";
import { Check, ChevronsUpDown, Building2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

const CompanySwitcher = () => {
  const { companies, company, switchCompany, switching } = useAuth();
  const [open, setOpen] = useState(false);

  const handleSelect = async (id) => {
    if (id === company?.id) {
      setOpen(false);
      return;
    }
    setOpen(false);
    try {
      const data = await switchCompany(id);
      toast.success(`Perusahaan aktif: ${data.active_company?.name}`, {
        description: "Semua data kini mengikuti konteks perusahaan ini.",
      });
    } catch (error) {
      toast.error(errorMessage(error, "Gagal mengganti perusahaan."));
    }
  };

  const single = companies.length <= 1;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={switching || single}
          data-testid="company-switcher-trigger"
          className="h-9 max-w-[16rem] justify-between gap-2 bg-card"
        >
          <span className="flex min-w-0 items-center gap-2">
            {switching ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
            ) : (
              <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <span className="truncate text-sm font-medium">
              {switching ? "Mengganti konteks…" : company?.name || "Pilih perusahaan"}
            </span>
          </span>
          {!single && <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[20rem] p-0" align="start">
        <Command>
          <CommandInput placeholder="Cari perusahaan…" data-testid="company-switcher-search-input" />
          <CommandList>
            <CommandEmpty>Tidak ada perusahaan yang cocok.</CommandEmpty>
            <CommandGroup heading="Perusahaan yang dapat Anda akses">
              {companies.map((c) => (
                <CommandItem
                  key={c.id}
                  value={`${c.name} ${c.code}`}
                  onSelect={() => handleSelect(c.id)}
                  data-testid={`company-switcher-item-${c.id}`}
                  className="flex items-start gap-2"
                >
                  <Check
                    className={cn(
                      "mt-0.5 h-4 w-4",
                      c.id === company?.id ? "opacity-100 text-primary" : "opacity-0"
                    )}
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{c.name}</span>
                    <span className="block text-xs text-muted-foreground">
                      {c.code} · {c.city || "-"}
                    </span>
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};

export default CompanySwitcher;
