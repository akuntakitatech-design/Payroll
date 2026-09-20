import React from "react";
import { Link } from "react-router-dom";
import { FileClock, FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDate, daysUntil } from "@/lib/format";
import { Button } from "@/components/ui/button";
import SectionCard, { SectionHeader } from "./SectionCard";

/** "Dokumen Menjelang Berakhir" - urut dari yang paling mendesak. */
const ExpiringDocsCard = ({ documents = [], horizonDays = 30, totalDocuments }) => (
  <SectionCard className="flex h-full flex-col" data-testid="card-dokumen-menjelang-berakhir">
    <SectionHeader
      icon={FileClock}
      title="Dokumen Menjelang Berakhir"
      description={`Jendela pemantauan ${horizonDays} hari`}
      aside={
        <span
          className="inline-flex h-7 min-w-7 items-center justify-center rounded-full border border-border bg-surface-1 px-2 text-[12.5px] font-semibold text-ink-2"
          data-numeric="true"
        >
          {documents.length}
        </span>
      }
    />

    <div className="flex flex-1 flex-col px-5 pb-5">
      {documents.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface-1 px-4 py-7 text-center">
          <span className="flex h-11 w-11 items-center justify-center rounded-full border border-success-border bg-success-soft text-success">
            <FolderOpen className="h-5 w-5" strokeWidth={1.75} />
          </span>
          <p className="mt-3 text-[13px] font-semibold text-ink-1">Semua dokumen masih berlaku</p>
          <p className="mt-1 max-w-[30ch] text-[12.5px] leading-[1.5] text-ink-3">
            Tidak ada dokumen yang mendekati masa berakhir dalam {horizonDays} hari.
          </p>
        </div>
      ) : (
        <>
          <ul className="space-y-1.5">
            {documents.map((doc, idx) => {
              const d = daysUntil(doc.expiry_date);
              const overdue = d < 0;
              return (
                <li key={doc.id} style={{ animationDelay: `${idx * 40}ms` }} className="animate-rise">
                  <Link
                    to="/documents"
                    data-testid={`expiring-doc-${doc.id}`}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-3.5 py-2.5 transition-[background-color,border-color] duration-150 hover:border-border-strong hover:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[12.5px] font-medium text-ink-1">{doc.name}</span>
                      <span className="mt-0.5 block truncate text-[11.5px] text-ink-3">
                        {doc.owner_label || "Perusahaan"} · {formatDate(doc.expiry_date)}
                      </span>
                    </span>
                    <span
                      className={cn(
                        "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-5",
                        overdue
                          ? "border-danger-border bg-danger-soft text-danger"
                          : "border-warning-border bg-warning-soft text-warning"
                      )}
                      data-numeric="true"
                    >
                      {overdue ? `Lewat ${Math.abs(d)} hari` : `${d} hari`}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>

          {typeof totalDocuments === "number" && (
            <p className="mt-2.5 text-[11.5px] leading-[1.5] text-ink-3">
              Menampilkan{" "}
              <span className="font-semibold text-ink-2" data-numeric="true">
                {documents.length}
              </span>{" "}
              dokumen yang perlu diperhatikan dari{" "}
              <span className="font-semibold text-ink-2" data-numeric="true">
                {totalDocuments}
              </span>{" "}
              dokumen aktif.
            </p>
          )}
        </>
      )}

      <Button asChild variant="outline" size="sm" className="mt-3 h-9 w-full justify-center">
        <Link to="/documents" data-testid="documents-archive-link">
          Buka arsip dokumen
        </Link>
      </Button>
    </div>
  </SectionCard>
);

export default ExpiringDocsCard;
