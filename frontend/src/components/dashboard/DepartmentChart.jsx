import React, { useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Network } from "lucide-react";
import SectionCard, { SectionHeader } from "./SectionCard";

/**
 * "Distribusi Karyawan per Departemen" - batang horizontal.
 *
 * Dipilih horizontal (bukan donut) karena jumlah departemen sedikit dan
 * namanya panjang; donut akan terlihat kosong dan labelnya bertumpuk.
 * Departemen tanpa karyawan tetap ditampilkan supaya HR melihat unit
 * mana yang masih kosong - itu justru informasi yang berguna.
 */
const ChartTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 shadow-float">
      <p className="text-[12.5px] font-semibold text-ink-1">{row.name}</p>
      {row.code && <p className="text-[11.5px] text-ink-3">{row.code}</p>}
      <p className="mt-1 text-[12.5px] text-ink-2">
        <span className="font-semibold text-primary" data-numeric="true">
          {row.count}
        </span>{" "}
        karyawan aktif
      </p>
    </div>
  );
};

const EmptyChart = () => (
  <div className="flex flex-col items-center justify-center gap-3 px-5 py-14 text-center">
    <svg viewBox="0 0 96 64" className="h-16 w-24" fill="none" aria-hidden="true">
      <rect x="6" y="40" width="16" height="18" rx="5" fill="hsl(var(--surface-2))" />
      <rect x="28" y="30" width="16" height="28" rx="5" fill="hsl(var(--surface-2))" />
      <rect x="50" y="22" width="16" height="36" rx="5" fill="hsl(var(--primary-soft))" />
      <rect x="72" y="34" width="16" height="24" rx="5" fill="hsl(var(--surface-2))" />
    </svg>
    <div>
      <p className="text-[13px] font-semibold text-ink-1">Belum ada data departemen</p>
      <p className="mt-0.5 text-[12.5px] text-ink-3">
        Tambahkan departemen dan tempatkan karyawan untuk melihat distribusinya.
      </p>
    </div>
  </div>
);

const DepartmentChart = ({ data = [], totalEmployees = 0 }) => {
  const [activeIdx, setActiveIdx] = useState(null);
  const hasAny = data.length > 0 && data.some((d) => d.count > 0);
  const filled = data.filter((d) => d.count > 0).length;

  // Tinggi menyesuaikan jumlah batang, dengan batas bawah agar tidak terlihat kosong.
  const chartHeight = Math.max(260, data.length * 52 + 40);

  return (
    <SectionCard className="flex h-full flex-col" data-testid="card-chart-distribusi-departemen">
      <SectionHeader
        icon={Network}
        title="Distribusi Karyawan per Departemen"
        description="Termasuk departemen yang belum memiliki karyawan, agar unit kosong ikut terlihat."
        aside={
          <div className="text-right">
            <p className="text-[18px] font-semibold leading-none text-ink-1" data-numeric="true">
              {totalEmployees}
            </p>
            <p className="mt-1 text-[11.5px] text-ink-3">karyawan aktif</p>
          </div>
        }
      />

      {!hasAny ? (
        <EmptyChart />
      ) : (
        <>
          <div className="px-2 pb-1" style={{ height: chartHeight }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={data}
                layout="vertical"
                margin={{ top: 4, right: 40, bottom: 4, left: 8 }}
                barCategoryGap={14}
                onMouseLeave={() => setActiveIdx(null)}
              >
                <XAxis type="number" hide domain={[0, "dataMax"]} allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={150}
                  axisLine={false}
                  tickLine={false}
                  tick={{
                    fill: "hsl(var(--ink-2))",
                    fontSize: 12.5,
                    fontWeight: 500,
                  }}
                />
                <Tooltip
                  content={<ChartTooltip />}
                  cursor={{ fill: "hsl(var(--surface-2))", radius: 8 }}
                />
                <Bar
                  dataKey="count"
                  radius={[8, 8, 8, 8]}
                  barSize={20}
                  background={{ fill: "hsl(var(--surface-2))", radius: 10 }}
                  onMouseEnter={(_, idx) => setActiveIdx(idx)}
                  isAnimationActive
                  animationDuration={520}
                >
                  {data.map((row, idx) => (
                    <Cell
                      key={row.id || row.name}
                      className="chart-bar-cell"
                      fill={
                        row.count === 0
                          ? "hsl(var(--surface-2))"
                          : activeIdx === idx
                            ? "hsl(var(--accent-sky-foreground))"
                            : "hsl(var(--chart-1))"
                      }
                    />
                  ))}
                  <LabelList
                    dataKey="count"
                    position="right"
                    offset={10}
                    style={{
                      fill: "hsl(var(--ink-2))",
                      fontSize: 12.5,
                      fontWeight: 600,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-auto flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border px-5 py-3">
            <span className="inline-flex items-center gap-2 text-[11.5px] text-ink-3">
              <span className="h-2.5 w-2.5 rounded-sm bg-chart-1" aria-hidden="true" />
              Terisi ({filled} departemen)
            </span>
            <span className="inline-flex items-center gap-2 text-[11.5px] text-ink-3">
              <span className="h-2.5 w-2.5 rounded-sm bg-surface-2 ring-1 ring-inset ring-border" aria-hidden="true" />
              Belum ada karyawan ({data.length - filled} departemen)
            </span>
          </div>
        </>
      )}
    </SectionCard>
  );
};

export default DepartmentChart;
