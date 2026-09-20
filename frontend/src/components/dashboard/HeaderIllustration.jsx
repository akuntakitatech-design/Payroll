import React from "react";

/**
 * Ilustrasi kecil untuk header dashboard - SVG inline, tanpa aset eksternal.
 *
 * Bentuknya sengaja dibuat "bahasa HRIS": kartu data karyawan, checklist
 * kelengkapan, dan batang statistik mini. Garis tipis, sudut lembut, warna
 * mengikuti token teal/mint agar menyatu dengan tema.
 */
const HeaderIllustration = ({ className = "" }) => (
  <svg
    viewBox="0 0 240 160"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    focusable="false"
    className={className}
  >
    {/* Blob latar lembut */}
    <path
      d="M196 18c22 14 36 44 30 72-6 28-32 54-62 60-30 6-64-8-88-28C52 102 34 74 42 50 50 26 82 8 114 6c32-2 60 -2 82 12Z"
      fill="hsl(var(--surface-0))"
      opacity="0.55"
    />

    {/* Kartu utama: data karyawan */}
    <rect
      x="30"
      y="34"
      width="108"
      height="72"
      rx="12"
      fill="hsl(var(--surface-0))"
      stroke="hsl(var(--primary))"
      strokeOpacity="0.28"
      strokeWidth="1.5"
    />
    {/* Avatar */}
    <circle cx="52" cy="56" r="9" fill="hsl(var(--accent-mint))" stroke="hsl(var(--primary))" strokeOpacity="0.35" strokeWidth="1.5" />
    <path d="M47.5 58.5a4.5 4.5 0 0 1 9 0" stroke="hsl(var(--primary))" strokeOpacity="0.55" strokeWidth="1.5" strokeLinecap="round" />
    {/* Baris teks */}
    <rect x="68" y="50" width="50" height="5" rx="2.5" fill="hsl(var(--primary))" opacity="0.35" />
    <rect x="68" y="60" width="34" height="5" rx="2.5" fill="hsl(var(--primary))" opacity="0.18" />

    {/* Batang statistik mini di dalam kartu */}
    <rect x="46" y="92" width="7" height="10" rx="3.5" fill="hsl(var(--primary))" opacity="0.3" />
    <rect x="58" y="85" width="7" height="17" rx="3.5" fill="hsl(var(--primary))" opacity="0.5" />
    <rect x="70" y="78" width="7" height="24" rx="3.5" fill="hsl(var(--primary))" opacity="0.72" />
    <rect x="82" y="88" width="7" height="14" rx="3.5" fill="hsl(var(--accent-sky-border))" />

    {/* Kartu checklist melayang */}
    <rect
      x="120"
      y="62"
      width="92"
      height="64"
      rx="12"
      fill="hsl(var(--surface-0))"
      stroke="hsl(var(--primary))"
      strokeOpacity="0.22"
      strokeWidth="1.5"
    />
    {[0, 1, 2].map((i) => (
      <g key={i}>
        <rect
          x="132"
          y={76 + i * 16}
          width="11"
          height="11"
          rx="3.5"
          fill={i < 2 ? "hsl(var(--primary))" : "hsl(var(--surface-2))"}
          stroke="hsl(var(--primary))"
          strokeOpacity={i < 2 ? "0" : "0.3"}
          strokeWidth="1.5"
        />
        {i < 2 && (
          <path
            d={`M134.6 ${81.5 + i * 16}l2.2 2.2 3.6-3.9`}
            stroke="hsl(var(--primary-foreground))"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        <rect
          x="150"
          y={79 + i * 16}
          width={i === 2 ? 30 : 48}
          height="5"
          rx="2.5"
          fill="hsl(var(--primary))"
          opacity={i === 2 ? 0.16 : 0.3}
        />
      </g>
    ))}

    {/* Aksen bintang empat sudut (bukan emoji) */}
    <path
      d="M196 36l2.4 6.1 6.1 2.4-6.1 2.4-2.4 6.1-2.4-6.1-6.1-2.4 6.1-2.4 2.4-6.1Z"
      fill="hsl(var(--primary))"
      opacity="0.45"
    />
    <path
      d="M168 26l1.5 3.8 3.8 1.5-3.8 1.5-1.5 3.8-1.5-3.8-3.8-1.5 3.8-1.5 1.5-3.8Z"
      fill="hsl(var(--accent-sky-foreground))"
      opacity="0.35"
    />
    {/* Titik aksen soft blue */}
    <circle cx="214" cy="96" r="4" fill="hsl(var(--accent-sky-border))" />
    <circle cx="26" cy="116" r="3" fill="hsl(var(--accent-mint-border))" />
  </svg>
);

export default HeaderIllustration;
