import React from "react";
import { Link } from "react-router-dom";
import { GitBranch, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import SectionCard, { SectionHeader } from "./SectionCard";

/**
 * "Menunggu Persetujuan Anda".
 *
 * Aturan kejujuran data: bila belum ada transaksi yang menunggu, angkanya
 * memang 0. Itu ditampilkan sebagai keadaan kosong yang rapi dan informatif,
 * BUKAN sebagai kegagalan atau angka palsu.
 */
const ApprovalCard = ({ pending, workflowCount = 0 }) => {
  const count = pending?.count ?? 0;
  const isEmpty = count === 0;

  return (
    <SectionCard className="flex h-full flex-col" data-testid="card-menunggu-persetujuan">
      <SectionHeader
        icon={GitBranch}
        title="Menunggu Persetujuan Anda"
        aside={
          <span
            className="inline-flex h-7 min-w-7 items-center justify-center rounded-full border border-border bg-surface-1 px-2 text-[12.5px] font-semibold text-ink-2"
            data-numeric="true"
            data-testid="approval-pending-count"
          >
            {count}
          </span>
        }
      />

      <div className="flex flex-1 flex-col px-5 pb-5">
        {isEmpty ? (
          <div className="flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface-1 px-4 py-7 text-center">
            <span className="flex h-11 w-11 items-center justify-center rounded-full border border-primary-border bg-primary-soft text-primary">
              <Inbox className="h-5 w-5" strokeWidth={1.75} />
            </span>
            <p className="mt-3 text-[13px] font-semibold text-ink-1">
              Belum ada pengajuan yang menunggu persetujuan.
            </p>
            <p className="mt-1 max-w-[30ch] text-[12.5px] leading-[1.5] text-ink-3">
              {workflowCount > 0
                ? `${workflowCount} alur persetujuan sudah siap. Pengajuan akan muncul di sini begitu modul transaksi mulai dipakai.`
                : "Atur alur persetujuan terlebih dahulu agar pengajuan dapat diteruskan ke penyetuju yang tepat."}
            </p>
          </div>
        ) : (
          <div className="flex-1">
            <p className="text-[28px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink-1" data-numeric="true">
              {count}
            </p>
            <p className="mt-1 text-[12.5px] leading-[1.5] text-ink-3">{pending?.note}</p>
          </div>
        )}

        <Button asChild variant="outline" size="sm" className="mt-3 h-9 w-full justify-center">
          <Link to="/setup/approval-workflows" data-testid="approval-manage-link">
            {workflowCount > 0 ? "Kelola alur persetujuan" : "Atur alur persetujuan"}
          </Link>
        </Button>
      </div>
    </SectionCard>
  );
};

export default ApprovalCard;
