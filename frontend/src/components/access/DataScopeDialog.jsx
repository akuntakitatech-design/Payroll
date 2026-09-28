import React, { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DataScopePicker } from "./DataScopePicker";
import { DataScopeBadge } from "./DataScopeBadge";

/** Upgrade 01I - atur Cakupan Data satu pengguna (company aktif). Disimpan lewat backend scope engine. */
export const DataScopeDialog = ({ user, open, onOpenChange, onSaved }) => {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [value, setValue] = useState({ mode: "ALL_TENANT", projectIds: [] });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !user) return;
    let alive = true;
    setData(null);
    setLoadError("");
    setError("");
    api
      .get(`/users/${user.id}/data-scope`)
      .then((res) => {
        if (!alive) return;
        setData(res.data);
        setValue({ mode: res.data.configured_mode || "ALL_TENANT", projectIds: res.data.project_ids || [] });
      })
      .catch((err) => alive && setLoadError(errorMessage(err, "Cakupan Data tidak dapat dimuat.")));
    return () => {
      alive = false;
    };
  }, [open, user]);

  const save = async () => {
    if (value.mode === "SELECTED_PROJECTS" && value.projectIds.length === 0) {
      setError("Pilih minimal satu project untuk Cakupan 'Project Tertentu'.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.put(`/users/${user.id}/data-scope`, { mode: value.mode, project_ids: value.projectIds });
      toast.success(`Cakupan Data ${user.full_name} berhasil disimpan.`);
      onOpenChange(false);
      onSaved?.();
    } catch (err) {
      setError(errorMessage(err, "Cakupan Data tidak dapat disimpan."));
    } finally {
      setSaving(false);
    }
  };

  const canManage = data?.can_manage !== false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" data-testid="data-scope-dialog">
        <DialogHeader>
          <DialogTitle>Cakupan Data — {user?.full_name}</DialogTitle>
          <DialogDescription>
            Perubahan langsung berlaku pada permintaan berikutnya dan tercatat di audit log.
          </DialogDescription>
        </DialogHeader>

        {loadError ? (
          <div className="space-y-3" data-testid="data-scope-load-error">
            <p className="text-sm text-destructive">{loadError}</p>
          </div>
        ) : !data ? (
          <div className="space-y-3" data-testid="data-scope-loading">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Cakupan efektif saat ini:</span>
              <DataScopeBadge scope={data} testId="data-scope-effective-badge" />
            </div>
            <DataScopePicker
              mode={value.mode}
              projectIds={value.projectIds}
              projects={data.available_projects || []}
              onChange={(v) => {
                setValue(v);
                setError("");
              }}
              disabled={!canManage || saving}
              fullScopeRole={!!data.full_scope_role}
              error={error}
              testPrefix="data-scope"
            />
            {!canManage && (
              <p className="text-xs text-muted-foreground" data-testid="data-scope-readonly-note">
                Hanya admin dengan Cakupan Data “Semua Data Perusahaan” yang dapat mengubah cakupan pengguna lain.
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="data-scope-cancel">
            Batal
          </Button>
          <Button onClick={save} disabled={!data || !canManage || saving} data-testid="data-scope-save">
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Simpan Cakupan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
