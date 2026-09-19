import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Loader2, RefreshCw, Wallet } from "lucide-react";

import { api, errorMessage } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import { downloadFile } from "@/lib/download";
import PageHeader, { PageBody } from "@/components/common/PageHeader";
import EmptyState from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_TONE = {
  approved: "bg-emerald-100 text-emerald-800 border-emerald-200",
  paid: "bg-sky-100 text-sky-800 border-sky-200",
};

const MyPayslipsPage = () => {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [employee, setEmployee] = useState(null);
  const [message, setMessage] = useState("");
  const [downloading, setDownloading] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/payroll/my/payslips");
      setItems(data?.items || []);
      setEmployee(data?.employee || null);
      setMessage(data?.message || "");
    } catch (error) {
      toast.error(errorMessage(error, "Gagal memuat slip gaji Anda."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    document.title = "Slip Gaji Saya · HRIS Suite";
  }, []);

  const download = async (item) => {
    setDownloading(item.id);
    try {
      await downloadFile(
        `/payroll/my/payslips/${item.id}/payslip`,
        `Slip-Gaji-${item.period?.label || ""}.pdf`
      );
      toast.success("Slip gaji berhasil diunduh.");
    } catch (error) {
      toast.error(errorMessage(error, "Slip gaji tidak dapat diunduh."));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Slip Gaji Saya"
        subtitle={
          employee
            ? `${employee.full_name}${employee.employee_number ? ` · ${employee.employee_number}` : ""}${
                employee.job_title ? ` · ${employee.job_title}` : ""
              }`
            : "Riwayat slip gaji pribadi Anda."
        }
        actions={
          <Button variant="outline" onClick={load} data-testid="my-payslips-refresh">
            <RefreshCw className="mr-2 h-4 w-4" /> Muat ulang
          </Button>
        }
      />
      <PageBody>
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={Wallet}
            title="Belum ada slip gaji"
            description={
              message ||
              "Slip gaji akan muncul di sini setelah payroll periode terkait disetujui oleh HR."
            }
            testId="my-payslips-empty"
          />
        ) : (
          <div className="space-y-3" data-testid="my-payslips-list">
            {items.map((item) => (
              <Card key={item.id} data-testid={`my-payslip-${item.id}`}>
                <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold">{item.period?.label || "-"}</p>
                      <Badge
                        variant="outline"
                        className={STATUS_TONE[item.run_status] || ""}
                        data-testid={`my-payslip-status-${item.id}`}
                      >
                        {item.run_status_label || item.run_status}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Bruto {formatCurrency(item.totals?.gross)} · Potongan{" "}
                      {formatCurrency(item.totals?.total_deductions)}
                      {item.payment_date ? ` · Dibayar ${formatDate(item.payment_date)}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center justify-between gap-4 sm:justify-end">
                    <div className="text-right">
                      <p className="text-xs text-muted-foreground">Take home pay</p>
                      <p
                        className="text-lg font-semibold tabular-nums"
                        data-testid={`my-payslip-net-${item.id}`}
                      >
                        {formatCurrency(item.totals?.net_pay)}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => download(item)}
                      disabled={downloading === item.id}
                      data-testid={`my-payslip-download-${item.id}`}
                    >
                      {downloading === item.id ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="mr-2 h-4 w-4" />
                      )}
                      Unduh PDF
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </PageBody>
    </>
  );
};

export default MyPayslipsPage;
