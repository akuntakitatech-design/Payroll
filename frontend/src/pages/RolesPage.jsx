import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Save, ShieldCheck, Info } from "lucide-react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import FormDialog from "@/components/common/FormDialog";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const ACTION_LABELS = {
  view: "Lihat",
  create: "Tambah",
  edit: "Ubah",
  delete: "Hapus",
  approve: "Setujui",
  export: "Ekspor",
  config: "Konfigurasi",
  manage: "Kelola",
  change: "Ubah Status",
};
const ACTIONS = ["view", "create", "edit", "delete", "approve", "export", "config", "manage", "change"];

const RolesPage = () => {
  const { can, isSuperAdmin } = useAuth();
  const [roles, setRoles] = useState([]);
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeRole, setActiveRole] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newRole, setNewRole] = useState({});
  const [errors, setErrors] = useState({});

  const canConfig = can("role", "config");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rolesRes, catalogRes] = await Promise.all([
        api.get("/roles"),
        api.get("/auth/catalog"),
      ]);
      const list = rolesRes.data.items || [];
      setRoles(list);
      setResources(catalogRes.data.resources || []);
      setActiveRole((prev) => {
        const found = list.find((r) => r.key === prev?.key);
        const next = found || list.find((r) => r.key === "hr_admin") || list[0] || null;
        setSelected(new Set(next?.permission_keys || []));
        return next;
      });
    } catch (err) {
      toast.error(errorMessage(err, "Gagal memuat peran dan hak akses."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    document.title = "Peran & Hak Akses · HRIS Suite";
  }, [load]);

  const isWildcard = selected.has("*:*");
  const locked =
    !canConfig ||
    (activeRole?.key === "super_admin" && !isSuperAdmin) ||
    // Peran global/sistem berlaku untuk semua tenant: hanya Platform Admin yang boleh mengubah.
    (activeRole && activeRole.editable === false);

  const grouped = useMemo(() => {
    const byModule = {};
    resources.forEach((r) => {
      byModule[r.module] = byModule[r.module] || [];
      byModule[r.module].push(r);
    });
    return byModule;
  }, [resources]);

  const pickRole = (key) => {
    const role = roles.find((r) => r.key === key);
    setActiveRole(role);
    setSelected(new Set(role?.permission_keys || []));
  };

  const toggle = (permKey) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(permKey)) next.delete(permKey);
      else next.add(permKey);
      return next;
    });
  };

  const toggleRow = (resource, actions) => {
    const keys = actions.map((a) => `${resource}:${a}`);
    const allOn = keys.every((k) => selected.has(k));
    setSelected((prev) => {
      const next = new Set(prev);
      keys.forEach((k) => (allOn ? next.delete(k) : next.add(k)));
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await api.put(`/roles/${activeRole.key}/permissions`, {
        permission_keys: Array.from(selected),
      });
      toast.success(res.data.message, {
        description: "Perubahan langsung berlaku pada sesi berikutnya bagi pengguna terkait.",
      });
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Hak akses tidak dapat disimpan."));
    } finally {
      setSaving(false);
    }
  };

  const createRole = async () => {
    const nextErrors = {};
    if (!String(newRole.key || "").trim()) nextErrors.key = "Kode peran wajib diisi.";
    else if (!/^[a-z0-9_]+$/.test(newRole.key))
      nextErrors.key = "Kode peran hanya boleh huruf kecil, angka, dan garis bawah.";
    if (!String(newRole.name || "").trim()) nextErrors.name = "Nama peran wajib diisi.";
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      return;
    }
    setSaving(true);
    try {
      await api.post("/roles", {
        key: newRole.key,
        name: newRole.name,
        description: newRole.description || null,
      });
      toast.success(`Peran ${newRole.name} berhasil dibuat. Atur hak aksesnya sekarang.`);
      setCreateOpen(false);
      setNewRole({});
      load();
    } catch (err) {
      setErrors({ __form__: errorMessage(err, "Peran tidak dapat dibuat.") });
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Peran & Hak Akses"
        subtitle="Tentukan tindakan yang boleh dilakukan setiap peran."
        actions={
          <div className="flex gap-2">
            {can("role", "create") && (
              <Button variant="outline" onClick={() => setCreateOpen(true)} data-testid="role-create-button">
                <Plus className="mr-2 h-4 w-4" /> Peran baru
              </Button>
            )}
            {canConfig && activeRole && !locked && (
              <Button onClick={save} disabled={saving} data-testid="role-save-permissions">
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Simpan hak akses
              </Button>
            )}
          </div>
        }
      />
      <PageBody>
        {loading ? (
          <Skeleton className="h-96 w-full" />
        ) : (
          <div className="grid gap-4 lg:grid-cols-4">
            <Card className="border-border bg-card p-3 lg:col-span-1" data-testid="role-list">
              <p className="px-1 pb-2 text-[12px] text-muted-foreground">
                Daftar peran
              </p>
              <div className="lg:hidden">
                <Select value={activeRole?.key} onValueChange={pickRole}>
                  <SelectTrigger data-testid="permission-matrix-role-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {roles.map((r) => (
                      <SelectItem key={r.key} value={r.key}>
                        {r.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="hidden space-y-1 lg:block">
                {roles.map((role) => (
                  <button
                    key={role.key}
                    type="button"
                    onClick={() => pickRole(role.key)}
                    data-testid={`role-item-${role.key}`}
                    className={`w-full rounded-lg px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      activeRole?.key === role.key
                        ? "bg-primary-soft text-primary"
                        : "hover:bg-accent"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{role.name}</span>
                      {role.is_system && (
                        <span className="shrink-0 text-[12px] text-muted-foreground">Sistem</span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {role.permission_keys?.includes("*:*")
                        ? "Akses penuh"
                        : `${role.permission_count} hak akses`}{" "}
                      · {role.user_count} pengguna
                    </span>
                  </button>
                ))}
              </div>
            </Card>

            <Card className="overflow-hidden border-border bg-card lg:col-span-3">
              <div className="border-b border-border px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h2 className="text-section-title">{activeRole?.name}</h2>
                    <p className="text-sm text-muted-foreground">{activeRole?.description}</p>
                  </div>
                  <span className="inline-flex shrink-0 items-center gap-1.5 text-[13px] text-muted-foreground">
                    <ShieldCheck className="h-3.5 w-3.5" />
                    {isWildcard ? "Akses penuh" : `${selected.size} hak akses dipilih`}
                  </span>
                </div>
                {locked && (
                  <p className="mt-2 flex items-start gap-1.5 rounded-lg border border-border bg-secondary px-3 py-2 text-xs text-secondary-foreground">
                    <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    {activeRole?.key === "super_admin"
                      ? "Hak akses Platform Admin hanya dapat diubah oleh Platform Admin."
                      : activeRole?.editable === false
                        ? "Peran sistem/global berlaku untuk semua tenant, sehingga hanya dapat diubah oleh Platform Admin. Buat peran khusus tenant bila membutuhkan hak akses berbeda."
                        : "Anda hanya dapat melihat matriks hak akses. Perubahan dilakukan oleh HR Manager atau Pemilik Perusahaan."}
                  </p>
                )}
                {isWildcard && (
                  <label className="mt-2 flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm">
                    <Checkbox
                      checked
                      disabled={locked}
                      onCheckedChange={() => toggle("*:*")}
                      data-testid="permission-wildcard"
                    />
                    <span>
                      <span className="font-medium">Akses penuh (semua modul, semua tindakan)</span>
                      <span className="block text-xs text-muted-foreground">
                        Hapus centang ini untuk memilih hak akses satu per satu.
                      </span>
                    </span>
                  </label>
                )}
              </div>

              {!isWildcard && (
                <div className="table-scroll">
                  <table className="w-full min-w-[46rem] border-collapse" data-testid="permission-matrix-table">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="sticky left-0 z-10 bg-card px-3 py-2 text-left text-[12px] text-muted-foreground">
                          Modul / Data
                        </th>
                        {ACTIONS.map((a) => (
                          <th
                            key={a}
                            className="px-2 py-2 text-center text-[12px] text-muted-foreground"
                          >
                            {ACTION_LABELS[a]}
                          </th>
                        ))}
                        <th className="px-2 py-2 text-center text-[12px] text-muted-foreground">
                          Semua
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(grouped).map(([moduleKey, list]) => (
                        <React.Fragment key={moduleKey}>
                          <tr className="bg-secondary/60">
                            <td
                              colSpan={ACTIONS.length + 2}
                              className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-secondary-foreground"
                            >
                              {moduleKey.replace(/_/g, " ")}
                            </td>
                          </tr>
                          {list.map((res) => (
                            <tr key={res.key} className="border-b border-border odd:bg-muted/30">
                              <td className="sticky left-0 z-10 bg-inherit px-3 py-1.5 text-sm font-medium">
                                {res.label}
                              </td>
                              {ACTIONS.map((action) => {
                                const allowed = res.actions.includes(action);
                                const permKey = `${res.key}:${action}`;
                                return (
                                  <td key={action} className="px-2 py-1.5 text-center">
                                    {allowed ? (
                                      <Checkbox
                                        checked={selected.has(permKey)}
                                        disabled={locked}
                                        onCheckedChange={() => toggle(permKey)}
                                        data-testid={`permission-matrix-cell-${res.key}-${action}`}
                                        aria-label={`${ACTION_LABELS[action]} ${res.label}`}
                                      />
                                    ) : (
                                      <span className="text-xs text-muted-foreground">—</span>
                                    )}
                                  </td>
                                );
                              })}
                              <td className="px-2 py-1.5 text-center">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 px-2 text-xs"
                                  disabled={locked}
                                  onClick={() => toggleRow(res.key, res.actions)}
                                  data-testid={`permission-row-toggle-${res.key}`}
                                >
                                  Ubah
                                </Button>
                              </td>
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        )}
      </PageBody>

      <FormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="Buat Peran Baru"
        description="Peran khusus berguna bila struktur organisasi Anda tidak cocok dengan peran bawaan."
        fields={[
          { name: "key", label: "Kode Peran", required: true, placeholder: "site_manager", hint: "Huruf kecil, angka, garis bawah." },
          { name: "name", label: "Nama Peran", required: true, placeholder: "Site Manager" },
          { name: "description", label: "Deskripsi", type: "textarea", colSpan: 2 },
        ]}
        values={newRole}
        errors={errors}
        onChange={(name, value) => {
          setNewRole((p) => ({ ...p, [name]: value }));
          setErrors((p) => ({ ...p, [name]: undefined, __form__: undefined }));
        }}
        onSubmit={createRole}
        submitting={saving}
        submitLabel="Buat peran"
      />
    </>
  );
};

export default RolesPage;
