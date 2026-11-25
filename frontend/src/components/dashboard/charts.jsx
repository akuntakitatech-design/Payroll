import React from "react";
import { cn } from "@/lib/utils";

/** Palet terbatas untuk kategori data. Status memakai warna semantik terpisah. */
export const CHART_PALETTE = [
  "#087E70", "#102D40", "#065F50", "#64748B", "#B45309",
  "#1D4ED8", "#9A3412", "#0F766E",
];

export const STATUS_COLORS = {
  success: "#087E70",
  info: "#1D4ED8",
  warning: "#B45309",
  critical: "#B91C1C",
  neutral: "#64748B",
};

export const ChartCard = ({ title, subtitle, actions, children, testId, className, footer }) => (
  <section
    className={cn("flex min-w-0 flex-col rounded-card border border-border bg-card p-4 shadow-card", className)}
    data-testid={testId}
  >
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <h2 className="text-[14px] font-bold tracking-[-0.01em] text-ink-1">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[12px] leading-relaxed text-ink-3">{subtitle}</p>}
      </div>
      {actions}
    </div>
    <div className="mt-3 min-w-0 flex-1">{children}</div>
    {footer && <div className="mt-3 border-t border-border pt-2.5 text-[11.5px] text-ink-3">{footer}</div>}
  </section>
);

const LegendRows = ({ items, onSelect, activeKey, valueSuffix = "" }) => (
  <ul className="min-w-0 flex-1 space-y-1.5">
    {items.map((item, index) => {
      const active = activeKey && activeKey === item.key;
      return (
        <li key={item.key || item.label}>
          <button
            type="button"
            onClick={onSelect ? () => onSelect(item) : undefined}
            disabled={!onSelect}
            className={cn(
              "flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors",
              onSelect && "hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active && "bg-primary-soft",
              !onSelect && "cursor-default"
            )}
            data-testid={item.key ? `chart-legend-${item.key}` : undefined}
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: CHART_PALETTE[index % CHART_PALETTE.length] }}
              aria-hidden="true"
            />
            <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-2">{item.label}</span>
            <span className="shrink-0 text-[12.5px] font-semibold tabular-nums text-ink-1">
              {item.count}
              {valueSuffix}
            </span>
            <span className="w-12 shrink-0 text-right text-[11.5px] tabular-nums text-ink-3">{item.pct}%</span>
          </button>
        </li>
      );
    })}
  </ul>
);

/** Donut komposisi + legenda. Klik legenda/segmen dipakai untuk cross-filter. */
export const DonutChart = ({ items = [], size = 168, thickness = 20, onSelect, activeKey, testId }) => {
  const data = items.filter((i) => Number(i.count) > 0);
  const total = data.reduce((sum, i) => sum + Number(i.count || 0), 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  if (!total) {
    return <p className="py-8 text-center text-[12.5px] text-ink-3" data-testid={testId}>Belum ada data untuk ditampilkan.</p>;
  }

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start" data-testid={testId}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`Komposisi ${total} karyawan`}
        className="shrink-0"
      >
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#E2E8F0" strokeWidth={thickness} />
        {data.map((item, index) => {
          const fraction = Number(item.count || 0) / total;
          const length = fraction * circumference;
          const dash = `${length} ${circumference - length}`;
          const color = CHART_PALETTE[index % CHART_PALETTE.length];
          const dashOffset = -offset * circumference;
          offset += fraction;
          return (
            <circle
              key={item.key || item.label}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={color}
              strokeWidth={activeKey && activeKey === item.key ? thickness + 5 : thickness}
              strokeDasharray={dash}
              strokeDashoffset={dashOffset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
              className={onSelect ? "cursor-pointer" : undefined}
              onClick={onSelect ? () => onSelect(item) : undefined}
            >
              <title>{`${item.label}: ${item.count} (${item.pct}%)`}</title>
            </circle>
          );
        })}
        <text x="50%" y="46%" textAnchor="middle" className="fill-ink-1" style={{ fontSize: 24, fontWeight: 700 }}>
          {total}
        </text>
        <text x="50%" y="58%" textAnchor="middle" className="fill-ink-3" style={{ fontSize: 11 }}>
          karyawan
        </text>
      </svg>
      <LegendRows items={data} onSelect={onSelect} activeKey={activeKey} />
    </div>
  );
};

/** Horizontal bar: distribusi dengan banyak kategori. */
export const BarList = ({ items = [], onSelect, activeKey, testId, emptyLabel = "Belum ada data.",
  valueFormatter, hidePct = false }) => {
  const data = items.filter((i) => Number(i.count) > 0);
  const max = Math.max(...data.map((i) => Number(i.count || 0)), 1);
  if (!data.length) return <p className="py-6 text-center text-[12.5px] text-ink-3" data-testid={testId}>{emptyLabel}</p>;
  return (
    <ul className="space-y-2" data-testid={testId}>
      {data.map((item, index) => {
        const active = activeKey && activeKey === item.key;
        return (
          <li key={item.key || item.label}>
            <button
              type="button"
              onClick={onSelect ? () => onSelect(item) : undefined}
              disabled={!onSelect}
              className={cn(
                "w-full rounded-md px-1.5 py-1 text-left transition-colors",
                onSelect && "hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active && "bg-primary-soft",
                !onSelect && "cursor-default"
              )}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="min-w-0 truncate text-[12.5px] text-ink-2">{item.label}</span>
                <span className="shrink-0 text-[12.5px] font-semibold tabular-nums text-ink-1">
                  {valueFormatter ? valueFormatter(item.count) : item.count}
                  {!hidePct && (
                    <span className="ml-1.5 text-[11.5px] font-normal text-ink-3">{item.pct}%</span>
                  )}
                </span>
              </div>
              <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-[#E2E8F0]">
                <div
                  className="h-full rounded-full transition-[width] duration-300"
                  style={{
                    width: `${Math.max((Number(item.count || 0) / max) * 100, 2)}%`,
                    backgroundColor: active ? "#065F50" : CHART_PALETTE[index % CHART_PALETTE.length],
                  }}
                />
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
};

/** Line chart untuk tren (mis. masuk/keluar per bulan). */
export const TrendChart = ({ data = [], series = [], height = 200, testId }) => {
  if (!data.length) return <p className="py-8 text-center text-[12.5px] text-ink-3" data-testid={testId}>Belum ada data tren.</p>;
  const width = 640;
  const padX = 34;
  const padY = 18;
  const values = data.flatMap((row) => series.map((s) => Number(row[s.key] || 0)));
  const max = Math.max(...values, 1);
  const stepX = data.length > 1 ? (width - padX * 2) / (data.length - 1) : 0;
  const y = (value) => height - padY - (Number(value || 0) / max) * (height - padY * 2);

  return (
    <div className="w-full overflow-x-auto" data-testid={testId}>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full min-w-[420px]" role="img"
           aria-label={series.map((s) => s.label).join(" dan ")}>
        {[0, 0.5, 1].map((frac) => (
          <line key={frac} x1={padX} x2={width - padX} y1={padY + frac * (height - padY * 2)}
                y2={padY + frac * (height - padY * 2)} stroke="#E2E8F0" strokeWidth="1" />
        ))}
        {series.map((s, sIndex) => {
          const points = data.map((row, index) => `${padX + index * stepX},${y(row[s.key])}`).join(" ");
          const color = s.color || CHART_PALETTE[sIndex % CHART_PALETTE.length];
          return (
            <g key={s.key}>
              <polyline points={points} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round"
                        strokeLinecap="round" />
              {data.map((row, index) => (
                <circle key={`${s.key}-${row.month || index}`} cx={padX + index * stepX} cy={y(row[s.key])} r="3"
                        fill="#FFFFFF" stroke={color} strokeWidth="2">
                  <title>{`${row.month || row.period} · ${s.label}: ${row[s.key] ?? 0}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
        {data.map((row, index) => (
          <text key={`x-${row.month || index}`} x={padX + index * stepX} y={height - 4} textAnchor="middle"
                style={{ fontSize: 10, fill: "#64748B" }}>
            {String(row.month || row.period || "").slice(-5)}
          </text>
        ))}
        <text x={padX - 6} y={padY + 4} textAnchor="end" style={{ fontSize: 10, fill: "#64748B" }}>{max}</text>
        <text x={padX - 6} y={height - padY} textAnchor="end" style={{ fontSize: 10, fill: "#64748B" }}>0</text>
      </svg>
      <div className="mt-1 flex flex-wrap gap-3">
        {series.map((s, index) => (
          <span key={s.key} className="inline-flex items-center gap-1.5 text-[11.5px] text-ink-3">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color || CHART_PALETTE[index % CHART_PALETTE.length] }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
};

/** Bar vertikal sederhana untuk komposisi antarperiode (mis. biaya tenaga kerja). */
export const PeriodBars = ({ data = [], valueKey = "value", labelKey = "label", onSelect, testId }) => {
  if (!data.length) return <p className="py-6 text-center text-[12.5px] text-ink-3" data-testid={testId}>Belum ada data.</p>;
  const max = Math.max(...data.map((d) => Number(d[valueKey] || 0)), 1);
  return (
    <div className="flex items-end gap-2 overflow-x-auto pb-1" data-testid={testId}>
      {data.map((row, index) => (
        <button
          key={row[labelKey] || index}
          type="button"
          onClick={onSelect ? () => onSelect(row) : undefined}
          disabled={!onSelect}
          className={cn(
            "group flex min-w-[42px] flex-1 flex-col items-center gap-1 rounded-md px-1 py-1",
            onSelect && "hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            !onSelect && "cursor-default"
          )}
        >
          <span className="text-[10.5px] tabular-nums text-ink-3">
            {Number(row[valueKey] || 0) >= 1_000_000
              ? `${(Number(row[valueKey] || 0) / 1_000_000).toFixed(1)} jt`
              : Number(row[valueKey] || 0).toLocaleString("id-ID")}
          </span>
          <span
            className="w-full rounded-t-md bg-primary transition-all duration-300 group-hover:bg-primary-hover"
            style={{ height: `${Math.max((Number(row[valueKey] || 0) / max) * 96, 3)}px` }}
            title={`${row[labelKey]}: ${Number(row[valueKey] || 0).toLocaleString("id-ID")}`}
          />
          <span className="w-full truncate text-center text-[10.5px] text-ink-3">{row[labelKey]}</span>
        </button>
      ))}
    </div>
  );
};
