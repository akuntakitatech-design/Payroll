import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, ClipboardCheck, MapPin, RefreshCw, XCircle } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { PageBody, SectionHeader } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import ToneBadge from "@/components/time/ToneBadge";
import DecisionDialog from "@/components/time/DecisionDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";
import { dayLabel, timeInZone, timeOf } from "@/lib/timeCatalog";
import { formatDateTime } from "@/lib/format";

const meters = (value) =>
  value === null || value === undefined || value === "" ? "-" : `${Math.round(Number(value))} m`;
const coords = (lat, lng) =>
  lat === null || lat === undefined || lng === null || lng === undefined
    ? "-"
    : `${Number(lat).toFixed(5)}, ${Number(lng).toFixed(5)}`;

const AttendanceApprovalsPage = () => {
  const { can } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(null); // { row, mode }
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/attendance/approvals");
      setItems(data?.items || []);
    } catch (error) {
      toast.error(errorMessage(error, "Daftar persetujuan tidak dapat dimuat."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async ({ notes }) => {
    if (!dialog) return;
    setSubmitting(true);
    try {
      const { data } = await api.post(`/attendance/approvals/${dialog.row.approval.id}/decide`, {
        decision: dialog.mode === "approve" ? "approved" : "rejected",
        notes,
      });
      toast.success(data?.message || "Keputusan tersimpan.");
      setDialog(null);
      load();
    } catch (error) {
      toast.error(errorMessage(error, "Keputusan tidak dapat disimpan."), { duration: 9000 });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <PageBody>
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </PageBody>
    );
  }

  return (
    <PageBody>
      <SectionHeader
        title="Persetujuan Absensi"
        description="Absensi di luar radius (Absen Masuk/Pulang) dan koreksi absensi yang menunggu keputusan Anda sesuai Konfigurasi Alur Persetujuan."
        actions={
          <Button variant="ghost" onClick={load} data-testid="approvals-refresh">
            <RefreshCw className="mr-2 h-4 w-4" /> Muat Ulang
          </Button>
        }
      />

      {items.length === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title="Tidak ada pengajuan yang menunggu keputusan Anda."
          description="Pengajuan akan muncul di sini ketika Anda menjadi penyetuju pada tahap yang aktif."
          testId="attendance-approvals-empty"
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2" data-testid="attendance-approvals-list">
          {items.map((item) => {
            const a = item.approval;
            const d = item.detail || {};
            const isLocation = a.document_kind === "attendance_location";
            return (
              <Card key={a.id} data-testid={`approval-card-${a.id}`}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                    {d.employee_name || a.record_label || "-"}
                    <ToneBadge tone="warning" label={a.document_label} />
                  </CardTitle>
                  <CardDescription>
                    {dayLabel(d.work_date)} · Tahap {a.step_order}: {a.step_name} · diajukan{" "}
                    {formatDateTime(a.submitted_at)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {isLocation ? (
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2 text-[13px]">
                        <span className="text-muted-foreground">Jenis Absen</span>
                        <ToneBadge
                          tone="info"
                          label={d.approval_for_label || "Absen Masuk"}
                          testId={`approval-for-${a.id}`}
                        />
                        {d.shift_name && (
                          <span className="text-muted-foreground">
                            · Shift <span className="font-medium text-foreground">{d.shift_name}</span>
                          </span>
                        )}
                        {d.timezone && <span className="text-[12px] text-muted-foreground">· zona {d.timezone}</span>}
                      </div>
                      <dl className="grid grid-cols-2 gap-2 text-[13px] sm:grid-cols-3">
                        <div>
                          <dt className="text-[12px] text-muted-foreground">Jam Masuk</dt>
                          <dd className="font-medium">
                            {timeInZone(d.check_in_at, d.timezone)}
                            {d.check_in_geofence_label && d.check_in_at ? (
                              <span className="block text-[12px] font-normal text-muted-foreground">
                                {d.check_in_geofence_label}
                              </span>
                            ) : null}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[12px] text-muted-foreground">Jam Pulang</dt>
                          <dd className="font-medium">
                            {timeInZone(d.check_out_at, d.timezone)}
                            {d.check_out_geofence_label && d.check_out_at ? (
                              <span className="block text-[12px] font-normal text-muted-foreground">
                                {d.check_out_geofence_label}
                              </span>
                            ) : null}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[12px] text-muted-foreground">Lokasi Kerja Seharusnya</dt>
                          <dd className="font-medium">
                            {d.work_location_name || "-"}
                            <span className="block text-[12px] font-normal text-muted-foreground">
                              Radius {d.configured_radius_meter ? `${Math.round(d.configured_radius_meter)} m` : "-"}
                            </span>
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[12px] text-muted-foreground">Jarak Aktual</dt>
                          <dd className="font-medium" data-testid={`approval-distance-${a.id}`}>
                            {meters(d.approval_for === "check_out" ? d.check_out_distance_meter : d.check_in_distance_meter)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[12px] text-muted-foreground">Akurasi GPS</dt>
                          <dd className="font-medium">
                            {meters(d.approval_for === "check_out" ? d.check_out_accuracy : d.check_in_accuracy)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[12px] text-muted-foreground">GPS Aktual</dt>
                          <dd className="font-medium" data-numeric="true">
                            {coords(
                              d.approval_for === "check_out" ? d.check_out_latitude : d.check_in_latitude,
                              d.approval_for === "check_out" ? d.check_out_longitude : d.check_in_longitude
                            )}
                          </dd>
                        </div>
                        <div className="col-span-2 sm:col-span-3">
                          <dt className="text-[12px] text-muted-foreground">Alasan Karyawan</dt>
                          <dd className="font-medium" data-testid={`approval-reason-${a.id}`}>
                            {(d.approval_for === "check_out"
                              ? d.check_out_location_reason_label
                              : d.location_reason_label) || d.location_reason_label || "-"}
                            {(d.approval_for === "check_out" ? d.check_out_location_reason : d.location_reason)
                              ? ` · ${d.approval_for === "check_out" ? d.check_out_location_reason : d.location_reason}`
                              : ""}
                          </dd>
                        </div>
                      </dl>
                      {(d.check_in_map_url || d.check_out_map_url) && (
                        <div className="flex flex-wrap gap-3">
                          {d.check_in_map_url && (
                            <a
                              href={d.check_in_map_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1.5 text-[13px] font-medium text-primary underline-offset-2 hover:underline"
                              data-testid={`approval-map-in-${a.id}`}
                            >
                              <MapPin className="h-3.5 w-3.5" /> Titik Absen Masuk di peta
                            </a>
                          )}
                          {d.check_out_map_url && (
                            <a
                              href={d.check_out_map_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1.5 text-[13px] font-medium text-primary underline-offset-2 hover:underline"
                              data-testid={`approval-map-out-${a.id}`}
                            >
                              <MapPin className="h-3.5 w-3.5" /> Titik Absen Pulang di peta
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <dl className="grid grid-cols-2 gap-2 text-[13px]">
                      <div>
                        <dt className="text-[12px] text-muted-foreground">Jenis Koreksi</dt>
                        <dd className="font-medium">{d.correction_type_label || "-"}</dd>
                      </div>
                      <div>
                        <dt className="text-[12px] text-muted-foreground">Tanggal Kerja</dt>
                        <dd className="font-medium">{dayLabel(d.work_date)}</dd>
                      </div>
                      <div>
                        <dt className="text-[12px] text-muted-foreground">Jam Saat Ini</dt>
                        <dd className="font-medium">
                          {timeOf(d.current_check_in_at)} - {timeOf(d.current_check_out_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[12px] text-muted-foreground">Usulan Jam</dt>
                        <dd className="font-medium">
                          {timeOf(d.proposed_check_in_at)} - {timeOf(d.proposed_check_out_at)}
                        </dd>
                      </div>
                      <div className="col-span-2">
                        <dt className="text-[12px] text-muted-foreground">Alasan</dt>
                        <dd className="font-medium">{d.reason || "-"}</dd>
                      </div>
                    </dl>
                  )}


                  {/* Daftar ini sudah difilter ke tahap yang menunggu keputusan pengguna login. */}
                  {(can("attendance", "approve") || a.decision === "pending") && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button
                        size="sm"
                        onClick={() => setDialog({ row: item, mode: "approve" })}
                        data-testid={`approval-approve-${a.id}`}
                      >
                        <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Setujui
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => setDialog({ row: item, mode: "reject" })}
                        data-testid={`approval-reject-${a.id}`}
                      >
                        <XCircle className="mr-1.5 h-3.5 w-3.5" /> Tolak
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <DecisionDialog
        open={!!dialog}
        onOpenChange={(open) => !open && setDialog(null)}
        mode={dialog?.mode}
        title={dialog?.mode === "reject" ? "Tolak Pengajuan Absensi" : "Setujui Pengajuan Absensi"}
        description={dialog?.row?.approval?.document_label}
        submitting={submitting}
        onSubmit={decide}
      />
    </PageBody>
  );
};

export default AttendanceApprovalsPage;
