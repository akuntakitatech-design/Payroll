import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { filterNav } from "@/lib/nav";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

/**
 * Pencarian global di topbar.
 *
 * Bukan kotak hias: menelusuri seluruh menu yang benar-benar boleh diakses
 * pengguna (hasil `filterNav` - sudah disaring izin & aktivasi modul), lalu
 * melompat ke halamannya. Tersedia juga jalan pintas mencari karyawan dan
 * dokumen memakai kata kunci yang diketik.
 *
 * Pintasan papan tombol: Ctrl/Cmd + K.
 */
const GlobalSearch = () => {
  const navigate = useNavigate();
  const { can, hasModule } = useAuth();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const groups = useMemo(() => filterNav({ can, hasModule }), [can, hasModule]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const go = (to) => {
    setOpen(false);
    setQuery("");
    navigate(to);
  };

  const trimmed = query.trim();

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="topbar-search-input"
        aria-label="Buka pencarian global"
        className="group hidden h-9 w-full max-w-[24rem] items-center gap-2.5 rounded-lg border border-input bg-card px-3 text-left transition-[border-color,box-shadow] duration-150 hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 md:flex"
      >
        <Search className="h-4 w-4 shrink-0 text-ink-3" strokeWidth={2} />
        <span className="flex-1 truncate text-[13px] text-ink-3">
          Cari karyawan, dokumen, atau menu…
        </span>
        <kbd className="hidden shrink-0 items-center gap-0.5 rounded border border-border bg-surface-1 px-1.5 py-0.5 text-[10.5px] font-medium text-ink-3 lg:inline-flex">
          Ctrl K
        </kbd>
      </button>

      {/* Tombol ikon untuk layar sempit */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Buka pencarian global"
        data-testid="topbar-search-button-mobile"
        className="flex h-9 w-9 items-center justify-center rounded-lg text-ink-2 transition-colors duration-150 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
      >
        <Search className="h-4.5 w-4.5" style={{ height: 18, width: 18 }} strokeWidth={2} />
      </button>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput
          placeholder="Cari karyawan, dokumen, atau menu…"
          value={query}
          onValueChange={setQuery}
          data-testid="global-search-input"
        />
        <CommandList>
          <CommandEmpty>Tidak ada hasil yang cocok.</CommandEmpty>

          {trimmed && (
            <>
              <CommandGroup heading={`Cari “${trimmed}” di…`}>
                <CommandItem
                  value={`cari-karyawan-${trimmed}`}
                  onSelect={() => go(`/employees?q=${encodeURIComponent(trimmed)}`)}
                  data-testid="global-search-employees"
                >
                  Data Karyawan
                </CommandItem>
                <CommandItem
                  value={`cari-dokumen-${trimmed}`}
                  onSelect={() => go(`/documents?q=${encodeURIComponent(trimmed)}`)}
                  data-testid="global-search-documents"
                >
                  Arsip Dokumen
                </CommandItem>
              </CommandGroup>
              <CommandSeparator />
            </>
          )}

          {groups.map((group) => (
            <CommandGroup key={group.key} heading={group.label}>
              {group.items.map((item) => (
                <CommandItem
                  key={item.key}
                  value={`${group.label} ${item.label}`}
                  onSelect={() => go(item.to)}
                  data-testid={`global-search-nav-${item.key}`}
                  className="gap-2"
                >
                  <item.icon className="h-4 w-4 shrink-0 text-ink-3" strokeWidth={1.75} />
                  {item.label}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}
        </CommandList>
      </CommandDialog>
    </>
  );
};

export default GlobalSearch;
