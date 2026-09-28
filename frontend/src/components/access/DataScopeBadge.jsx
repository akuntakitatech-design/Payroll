import React from "react";
import { Building2, FolderKanban, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Upgrade 01I - ringkasan Cakupan Data (hanya tampilan; logika cakupan sepenuhnya di backend).
 * scope: { mode | effective_mode, projects: [{id,name}], no_access, full_scope_role }
 */
export const scopeState = (scope) => {
  if (!scope) return { kind: "all", label: "Semua Data Perusahaan", projects: [] };
  const mode = scope.effective_mode || scope.mode;
  if (scope.full_scope_role || scope.source === "role") {
    return { kind: "all", label: "Semua Data Perusahaan", note: "sesuai peran", projects: [] };
  }
  if (mode === "ALL_TENANT") return { kind: "all", label: "Semua Data Perusahaan", projects: [] };
  const projects = (scope.projects || []).filter((p) => p.valid !== false && p.status !== "missing");
  if (scope.no_access || projects.length === 0) {
    return { kind: "none", label: "Tidak ada akses data", projects: [] };
  }
  return { kind: "projects", label: "Project Tertentu", projects };
};

export const scopeText = (scope) => {
  const st = scopeState(scope);
  if (st.kind !== "projects") return st.label;
  return `${st.label} — ${st.projects.map((p) => p.name || "(tanpa nama)").join(", ")}`;
};

const STYLES = {
  all: "border-primary-border bg-primary-soft text-primary",
  projects: "border-border bg-muted text-ink-1",
  none: "border-warning-border bg-warning-soft text-warning",
};
const ICONS = { all: Building2, projects: FolderKanban, none: ShieldAlert };

export const DataScopeBadge = ({ scope, compact = false, className, testId }) => {
  const st = scopeState(scope);
  const Icon = ICONS[st.kind];
  const full = scopeText(scope);
  const shown =
    st.kind === "projects" && compact && st.projects.length > 2
      ? `${st.label} — ${st.projects.slice(0, 2).map((p) => p.name).join(", ")} +${st.projects.length - 2}`
      : full;
  return (
    <span
      title={full + (st.note ? ` (${st.note})` : "")}
      data-testid={testId}
      data-scope-kind={st.kind}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-0.5 text-[12px] font-medium",
        STYLES[st.kind],
        className
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="truncate">{shown}</span>
    </span>
  );
};
