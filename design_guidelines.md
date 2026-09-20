{
  "design_personality": {
    "brand_attributes": [
      "Profesional & premium (tenang, tidak ramai)",
      "Fresh (teal/emerald + mint/soft blue sebagai aksen)",
      "Operasional (scan cepat: apa yang perlu ditindak hari ini)",
      "Enterprise Indonesia (bahasa Indonesia, formal namun ramah)"
    ],
    "anti_ai_template_rules": [
      "Hindari layout serba simetris dan semua kartu ukuran sama tanpa hierarki. Buat 1 area hero header yang lebih menonjol + grid KPI yang rapi.",
      "Jangan pakai gradient mencolok/gelap. Jika butuh aksen, gunakan strip tipis atau halo lembut di background section saja (maks 20% viewport).",
      "Jangan gunakan ikon/ilustrasi stok. Header memakai ilustrasi SVG inline sederhana (geometri + garis) yang konsisten dengan teal/mint.",
      "Hindari teks generik seperti 'Welcome back' atau 'Here’s your overview'. Gunakan copy spesifik HRIS Indonesia.",
      "Jangan menjejalkan chart banyak. Data sedikit → desain harus tetap 'penuh' lewat spacing, label, dan empty state yang elegan.",
      "Hindari badge warna-warni berlebihan. Status cukup 3 tingkat (critical/warning/info) dengan soft background + border.",
      "Jangan center-align seluruh konten. Gunakan alignment kiri dan grid yang jelas.",
      "Hindari shadow tebal. Premium = border halus + shadow tipis + whitespace besar."
    ]
  },
  "design_tokens_index_css_hsl_triplets": {
    "notes": [
      "WAJIB kompatibel ke belakang: jangan hapus/rename token yang sudah ada.",
      "Tambahkan token baru di :root (HSL triplet tanpa hsl()).",
      "Mint/soft blue dipakai sebagai aksen UI (chip, hover, highlight), bukan teks utama.",
      "Kontras: teks utama tetap foreground; teks di atas mint/soft-blue gunakan foreground atau teal gelap."
    ],
    "add_these_tokens": {
      "--accent-mint": "168 55% 92%",
      "--accent-mint-foreground": "173 80% 18%",
      "--accent-mint-border": "170 28% 78%",

      "--accent-sky": "205 70% 92%",
      "--accent-sky-foreground": "208 68% 26%",
      "--accent-sky-border": "208 35% 78%",

      "--surface-0": "0 0% 100%",
      "--surface-1": "210 20% 98%",
      "--surface-2": "210 18% 96%",

      "--ink-1": "215 25% 17%",
      "--ink-2": "215 16% 32%",
      "--ink-3": "215 12% 45%",

      "--primary-strong": "173 85% 20%",
      "--primary-hover": "173 80% 24%",
      "--primary-active": "173 85% 18%",

      "--focus-ring": "173 80% 30%",
      "--focus-ring-offset": "0 0% 100%",

      "--shadow-xs": "0 1px 0 rgba(16, 24, 40, 0.04)",
      "--shadow-sm": "0 1px 1px rgba(16, 24, 40, 0.03)",
      "--shadow-md": "0 6px 18px rgba(16, 24, 40, 0.08)",
      "--shadow-lg": "0 14px 40px rgba(16, 24, 40, 0.12)",

      "--radius-sm": "0.5rem",
      "--radius-md": "0.75rem",
      "--radius-lg": "1rem",

      "--noise-opacity": "0.035",

      "--kpi-locked": "215 10% 55%",
      "--kpi-locked-soft": "210 16% 96%",
      "--kpi-locked-border": "214 16% 86%"
    },
    "allowed_gradients": {
      "hero_header_bg": "linear-gradient(135deg, hsl(var(--primary-soft)) 0%, hsl(var(--accent-mint)) 45%, hsl(var(--accent-sky)) 100%)",
      "rule": "Gunakan hanya sebagai background header dashboard (maks ~18–20% viewport). Jangan untuk kartu konten atau area baca panjang."
    },
    "texture": {
      "css_noise_overlay": "background-image: radial-gradient(rgba(16,24,40,var(--noise-opacity)) 1px, transparent 1px); background-size: 18px 18px;"
    }
  },
  "typography": {
    "font_family": {
      "primary": "Plus Jakarta Sans (SUDAH terpasang, pertahankan)",
      "fallback": "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto"
    },
    "scale": {
      "page_title": {
        "class": "text-page-title",
        "tailwind": "text-[24px] font-semibold leading-[1.25] tracking-[-0.015em]",
        "usage": "Judul halaman Dashboard"
      },
      "header_greeting": {
        "tailwind": "text-[18px] font-semibold leading-[1.3] tracking-[-0.01em]",
        "usage": "Sapaan: 'Selamat pagi, Raka'"
      },
      "section_title": {
        "class": "text-section-title",
        "tailwind": "text-[16px] font-semibold leading-[1.4]",
        "usage": "Judul kartu/section"
      },
      "kpi_value": {
        "tailwind": "text-[28px] font-semibold leading-[1.1] tracking-[-0.02em]",
        "usage": "Angka KPI besar (pakai data-numeric=\"true\")"
      },
      "kpi_label": {
        "tailwind": "text-[13px] font-medium text-muted-foreground",
        "usage": "Label KPI"
      },
      "body": {
        "tailwind": "text-[14px] leading-[1.55]",
        "usage": "Teks isi kartu"
      },
      "meta": {
        "class": "text-meta",
        "tailwind": "text-[12px] leading-[1.5] text-muted-foreground",
        "usage": "Teks pendukung, timestamp, helper"
      }
    }
  },
  "layout_grid_dashboard": {
    "shell": {
      "sidebar_width": {
        "expanded": "16rem (w-64)",
        "collapsed": "4rem (w-16)",
        "behavior": "Collapse menyisakan ikon + tooltip; konten utama melebar."
      },
      "topbar": {
        "height": "56px",
        "position": "sticky top-0 z-40",
        "background": "bg-background/95 dengan backdrop-blur (opsional) + border-b",
        "note": "Jangan transparan penuh untuk teks gelap; gunakan solid/95% opacity."
      },
      "content_padding": "px-6 py-6 (1440/1920), px-5 py-5 (1280)",
      "max_width": "Tidak perlu max-w kecil; dashboard desktop biarkan fluid dengan batas nyaman via padding."
    },
    "dashboard_grid": {
      "breakpoints": {
        "1920": {
          "columns": "12",
          "gap": "gap-6",
          "order": [
            "Header dashboard (12)",
            "Perlu Ditindaklanjuti (5) + KPI (7, grid 4 kartu)",
            "Ringkasan SDM Hari Ini (5) + Distribusi Karyawan per Departemen (7)",
            "Menunggu Persetujuan Anda (5) + Dokumen Menjelang Berakhir (4) + Kelengkapan Setup (3)"
          ]
        },
        "1440": {
          "columns": "12",
          "gap": "gap-5",
          "order": [
            "Header dashboard (12)",
            "Perlu Ditindaklanjuti (12)",
            "KPI (12, 2x2)",
            "Ringkasan SDM Hari Ini (6) + Distribusi Karyawan per Departemen (6)",
            "Menunggu Persetujuan Anda (6) + Dokumen Menjelang Berakhir (6)",
            "Kelengkapan Setup (12)"
          ]
        },
        "1280": {
          "columns": "12",
          "gap": "gap-4",
          "order": [
            "Header dashboard (12)",
            "KPI (12, 2x2)",
            "Perlu Ditindaklanjuti (12)",
            "Distribusi Karyawan per Departemen (12)",
            "Ringkasan SDM Hari Ini (12)",
            "Menunggu Persetujuan Anda (12)",
            "Dokumen Menjelang Berakhir (12)",
            "Kelengkapan Setup (12)"
          ]
        }
      },
      "hierarchy_rules": [
        "Header dashboard harus paling menonjol (surface + gradient halus + ilustrasi kecil).",
        "Kartu 'Perlu Ditindaklanjuti' harus terlihat prioritas (border kiri berwarna + list actionable).",
        "KPI cards harus ringkas dan sejajar; 1 varian 'TERKUNCI' tetap setara tinggi.",
        "Chart horizontal bar diberi ruang cukup tinggi (min-h 280–320px) agar 4 batang tidak terlihat kosong."
      ]
    }
  },
  "components": {
    "component_path": {
      "shadcn": {
        "button": "@/components/ui/button",
        "card": "@/components/ui/card",
        "badge": "@/components/ui/badge",
        "input": "@/components/ui/input",
        "separator": "@/components/ui/separator",
        "dropdown_menu": "@/components/ui/dropdown-menu",
        "select": "@/components/ui/select",
        "tooltip": "@/components/ui/tooltip",
        "progress": "@/components/ui/progress",
        "skeleton": "@/components/ui/skeleton",
        "scroll_area": "@/components/ui/scroll-area"
      },
      "charts": {
        "recharts": "recharts@3.6.0 (sudah terpasang)"
      },
      "motion": {
        "framer_motion": "framer-motion@11.18 (sudah tersedia)"
      },
      "icons": {
        "lucide": "lucide-react (sudah terpasang)"
      }
    },
    "topbar": {
      "read_only_pill": {
        "placement": "Di kanan search bar, sebelum notification bell (agar terlihat tapi tidak mengganggu).",
        "copy": "Mode hanya-baca — data produksi, perubahan dinonaktifkan",
        "style": {
          "container": "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[12px]",
          "colors": "bg-warning-soft border-warning-border text-foreground",
          "icon": "Lock (lucide) ukuran 14px, text-warning",
          "focus": "Jika clickable (mis. buka detail), wajib focus-visible ring"
        },
        "data_testid": "read-only-mode-pill"
      },
      "company_selector": {
        "component": "Select",
        "style": "min-w-[220px] bg-card border-input shadow-xs rounded-md",
        "data_testid": "topbar-company-selector"
      },
      "search_bar": {
        "component": "Input + icon Search",
        "placeholder": "Cari karyawan, dokumen, atau menu…",
        "style": "w-[420px] max-w-[42vw] rounded-md bg-card border-input pl-10",
        "micro": "Saat fokus: ring 2px focus-ring + placeholder memudar",
        "data_testid": "topbar-search-input"
      },
      "notification_bell": {
        "component": "Button variant=ghost + Tooltip",
        "indicator": "Dot kecil (8px) di pojok kanan atas jika ada notifikasi belum dibaca",
        "style": "relative h-9 w-9 rounded-md hover:bg-accent",
        "data_testid": "topbar-notification-button"
      },
      "user_profile": {
        "component": "DropdownMenu + Avatar",
        "style": "rounded-md hover:bg-accent px-2 py-1",
        "data_testid": "topbar-user-menu"
      }
    },
    "sidebar": {
      "style": {
        "background": "bg-card",
        "border": "border-r",
        "section_label": "text-[11px] uppercase tracking-[0.08em] text-muted-foreground px-3 mt-5 mb-2",
        "item": "flex items-center gap-2 rounded-md px-3 py-2 text-[13px] text-foreground/90 hover:bg-accent",
        "active": "bg-primary-soft text-foreground border border-primary-border",
        "collapsed": "ikon center + tooltip; label disembunyikan"
      },
      "micro": "Hover item: background accent + icon shift 1px (translate-x-0.5) tanpa transition:all",
      "data_testid_examples": [
        "sidebar-nav-dashboard",
        "sidebar-nav-karyawan",
        "sidebar-collapse-button"
      ]
    },
    "dashboard_header": {
      "structure": [
        "Kiri: sapaan + nama perusahaan + meta (periode, cabang aktif)",
        "Tengah: inline stats kecil (Pengguna, Dokumen, Modul aktif) sebagai chips", 
        "Kanan: tombol aksi (mis. 'Tambah Karyawan', 'Unggah Dokumen') + ilustrasi kecil"
      ],
      "style": {
        "container": "rounded-xl border bg-[image:var(--header-gradient)] p-6 shadow-card relative overflow-hidden",
        "note": "Implementasi gradient via style inline atau class util; jangan lebih dari 20% viewport."
      },
      "inline_stats_chip": {
        "style": "inline-flex items-center gap-2 rounded-full bg-card/70 border px-3 py-1 text-[12px]",
        "data_testid": "dashboard-header-inline-stat"
      },
      "primary_cta": {
        "component": "Button",
        "variant": "default",
        "style": "rounded-lg shadow-xs",
        "data_testid": "dashboard-header-primary-action"
      },
      "secondary_cta": {
        "component": "Button",
        "variant": "outline",
        "style": "rounded-lg",
        "data_testid": "dashboard-header-secondary-action"
      },
      "inline_svg_illustration": {
        "requirements": [
          "SVG inline (tanpa aset eksternal)",
          "Gaya: garis tipis 1.5px, sudut rounded, bentuk: kartu, checklist, bar chart mini",
          "Warna: stroke hsl(var(--primary)) + fill hsl(var(--primary-soft)) / hsl(var(--accent-mint))",
          "Opacity 0.9, tambahkan 1-2 titik aksen soft blue"
        ],
        "suggested_svg_layers": [
          "Background blob: path fill primary-soft opacity 0.9",
          "Mini bar chart: 4 bar rounded",
          "Checklist: 3 item dengan check kecil",
          "Sparkle kecil (bukan emoji) berupa bintang 4-sudut sederhana"
        ]
      }
    },
    "kpi_card": {
      "base": {
        "component": "Card",
        "container": "rounded-xl border bg-card shadow-card p-4",
        "header": "flex items-start justify-between gap-3",
        "icon_wrap": "h-9 w-9 rounded-lg border flex items-center justify-center",
        "value": "mt-3 text-[28px] font-semibold leading-[1.1]",
        "label": "text-[13px] font-medium text-muted-foreground",
        "data_testid": "kpi-card"
      },
      "variants": {
        "normal": {
          "icon": "Users/Briefcase/Files/Boxes",
          "icon_colors": "bg-primary-soft border-primary-border text-primary",
          "note": "Untuk 'Karyawan Aktif' dan 'Modul Aktif'"
        },
        "warning": {
          "use_for": "Kontrak Akan Berakhir",
          "colors": "bg-warning-soft border-warning-border",
          "icon": "CalendarClock",
          "badge": "Badge variant=secondary dengan teks 'Perlu perhatian'"
        },
        "positive": {
          "optional": "Jika ada KPI yang menunjukkan peningkatan",
          "colors": "bg-success-soft border-success-border",
          "icon": "TrendingUp"
        },
        "locked_unavailable": {
          "use_for": "Hadir Hari Ini",
          "rules": [
            "JANGAN tampilkan angka.",
            "Tampilkan ikon Lock + label 'Modul Absensi belum aktif'.",
            "CTA halus 'Aktifkan Modul' (Button variant=outline ukuran sm)."
          ],
          "layout": "Value area diganti panel kecil: icon + teks + CTA",
          "colors": "bg-[hsl(var(--kpi-locked-soft))] border-[hsl(var(--kpi-locked-border))] text-foreground",
          "data_testid": {
            "card": "kpi-hadir-hari-ini-locked-card",
            "cta": "kpi-hadir-hari-ini-activate-button"
          }
        }
      },
      "states": {
        "loading": "Gunakan Skeleton: judul (w-24 h-4), value (w-20 h-8), meta (w-28 h-3)",
        "error": "Alert variant=destructive dengan copy singkat + tombol 'Coba lagi'",
        "empty": "Untuk KPI yang valid tapi 0: tampilkan 0 dengan meta 'Belum ada data hari ini'"
      }
    },
    "priority_card_perlu_ditindaklanjuti": {
      "title": "Perlu Ditindaklanjuti",
      "layout": "Card dengan list 4 item; tiap item clickable membuka halaman terkait",
      "item": {
        "container": "flex items-start gap-3 rounded-lg border p-3 hover:bg-accent",
        "left_indicator": "strip 3px rounded-full (critical/warning/info)",
        "content": "judul item + deskripsi singkat + meta (deadline/impact)",
        "right": "chevron-right",
        "data_testid": "priority-item"
      },
      "severity_styles": {
        "critical": "bg-danger-soft border-danger-border; strip bg-danger",
        "warning": "bg-warning-soft border-warning-border; strip bg-warning",
        "info": "bg-info-soft border-info-border; strip bg-info"
      },
      "states": {
        "empty": "Empty state: 'Tidak ada item prioritas hari ini' + ikon CheckCircle",
        "loading": "Skeleton list 4 baris",
        "error": "Alert + 'Muat ulang'"
      }
    },
    "card_ringkasan_sdm_hari_ini": {
      "title": "Ringkasan SDM Hari Ini",
      "layout": "2 kolom mini-metrics + catatan singkat",
      "suggested_rows": [
        "Karyawan aktif: 4",
        "Kontrak berakhir ≤45 hari: 1",
        "Kontrak sudah berakhir: 1",
        "Sertifikasi perlu perhatian: 2"
      ],
      "data_testid": "card-ringkasan-sdm"
    },
    "chart_distribusi_departemen": {
      "title": "Distribusi Karyawan per Departemen",
      "chart_type": "Horizontal BarChart (hindari donut karena data sedikit)",
      "visual_rules": [
        "Tinggi chart min-h 280px agar 4 bar tidak terlihat kosong.",
        "Bar radius 8, barSize 18–22.",
        "Gunakan warna chart-1 (teal) untuk bar utama + aksen soft blue untuk highlight hover.",
        "Tampilkan label nilai di ujung bar (data-numeric=true)."
      ],
      "empty_state": "Jika data kosong: tampilkan ilustrasi mini bar (SVG) + teks 'Belum ada data departemen'",
      "data_testid": "card-chart-distribusi-departemen"
    },
    "card_menunggu_persetujuan": {
      "title": "Menunggu Persetujuan Anda",
      "honesty_rule": "Angka 0 harus tampil sebagai empty state yang rapi, bukan error.",
      "empty_state": {
        "copy": "Belum ada pengajuan yang menunggu persetujuan.",
        "subcopy": "Saat ada pengajuan cuti/lembur/perubahan data, akan muncul di sini.",
        "cta_optional": "Lihat riwayat (ghost) atau Pelajari alur persetujuan (link)"
      },
      "data_testid": "card-menunggu-persetujuan"
    },
    "card_dokumen_menjelang_berakhir": {
      "title": "Dokumen Menjelang Berakhir",
      "layout": "List 4 item max dengan badge tanggal + status",
      "data_testid": "card-dokumen-menjelang-berakhir"
    },
    "card_kelengkapan_setup": {
      "title": "Kelengkapan Setup",
      "layout": "Progress bar + checklist 8 langkah",
      "progress": {
        "component": "Progress",
        "style": "h-2 rounded-full",
        "data_testid": "setup-progress"
      },
      "checklist": {
        "item": "Checkbox + label + helper text",
        "data_testid": "setup-checklist-item"
      }
    }
  },
  "micro_interactions_motion": {
    "principles": [
      "Animasi pendek, fungsional, tidak mencolok.",
      "Tidak pakai transition: all. Batasi ke color, background-color, border-color, box-shadow, opacity.",
      "Gunakan framer-motion untuk entrance halus pada kartu (stagger kecil)."
    ],
    "durations": {
      "hover": "150ms",
      "press": "80ms",
      "panel_enter": "220ms",
      "skeleton_pulse": "default shadcn"
    },
    "easings": {
      "standard": "cubic-bezier(0.2, 0.8, 0.2, 1)",
      "out": "cubic-bezier(0.16, 1, 0.3, 1)"
    },
    "examples_tailwind": {
      "card_hover": "hover:shadow-float hover:border-border-strong transition-[box-shadow,border-color] duration-150",
      "button_press": "active:scale-[0.98] transition-[transform,background-color,border-color] duration-150",
      "focus_ring": "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--focus-ring))] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--focus-ring-offset))]"
    }
  },
  "accessibility": {
    "rules": [
      "Kontras minimal WCAG AA: jangan gunakan mint/soft-blue sebagai warna teks utama.",
      "Semua elemen interaktif wajib punya focus-visible ring yang jelas.",
      "Target klik minimal 40x40px untuk ikon di topbar.",
      "Gunakan aria-label untuk tombol ikon (notifikasi, collapse sidebar).",
      "Semua elemen interaktif & info kunci wajib data-testid (kebab-case)."
    ]
  },
  "image_urls": {
    "note": "Tidak memakai gambar stok. Header memakai SVG inline/CSS saja sesuai requirement.",
    "categories": [
      {
        "category": "header-illustration",
        "description": "SVG inline: mini bar chart + checklist + blob lembut teal/mint",
        "image_url": "N/A (inline SVG)"
      }
    ]
  },
  "instructions_to_main_agent": {
    "implementation_notes_js": [
      "Repo memakai .js, bukan .tsx. Buat komponen React dalam .jsx/.js sesuai pola existing.",
      "Gunakan shadcn/ui dari src/components/ui sebagai komponen utama (Button, Card, Select, DropdownMenu, Progress, Skeleton).",
      "Tambahkan token baru ke index.css tanpa mengubah token lama.",
      "Pastikan KPI 'Hadir Hari Ini' memakai state TERKUNCI (tanpa angka) + CTA 'Aktifkan Modul'.",
      "Pastikan 'Menunggu Persetujuan Anda' menampilkan empty state elegan saat 0.",
      "Tambahkan pill mode hanya-baca di topbar (data dari GET /api/system/mode).",
      "Setiap tombol/link/input/menu item wajib data-testid.",
      "Chart gunakan Recharts BarChart horizontal; desain untuk 4 bar saja (min height, label)."
    ],
    "suggested_testids_minimum": [
      "layout-sidebar",
      "layout-topbar",
      "topbar-company-selector",
      "topbar-search-input",
      "topbar-notification-button",
      "topbar-user-menu",
      "read-only-mode-pill",
      "dashboard-header-primary-action",
      "kpi-karyawan-aktif-card",
      "kpi-hadir-hari-ini-locked-card",
      "kpi-hadir-hari-ini-activate-button",
      "kpi-kontrak-akan-berakhir-card",
      "kpi-modul-aktif-card",
      "card-perlu-ditindaklanjuti",
      "card-ringkasan-sdm",
      "card-chart-distribusi-departemen",
      "card-menunggu-persetujuan",
      "card-dokumen-menjelang-berakhir",
      "card-kelengkapan-setup"
    ]
  }
}

<General UI UX Design Guidelines>  
    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms
    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text
   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json

 **GRADIENT RESTRICTION RULE**
NEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc
NEVER use dark gradients for logo, testimonial, footer etc
NEVER let gradients cover more than 20% of the viewport.
NEVER apply gradients to text-heavy content or reading areas.
NEVER use gradients on small UI elements (<100px width).
NEVER stack multiple gradient layers in the same viewport.

**ENFORCEMENT RULE:**
    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors

**How and where to use:**
   • Section backgrounds (not content backgrounds)
   • Hero section header content. Eg: dark to light to dark color
   • Decorative overlays and accent elements only
   • Hero section with 2-3 mild color
   • Gradients creation can be done for any angle say horizontal, vertical or diagonal

- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**

</Font Guidelines>

- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. 
   
- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.

- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.
   
- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly
    Eg: - if it implies playful/energetic, choose a colorful scheme
           - if it implies monochrome/minimal, choose a black–white/neutral scheme

**Component Reuse:**
	- Prioritize using pre-existing components from src/components/ui when applicable
	- Create new components that match the style and conventions of existing components when needed
	- Examine existing components to understand the project's component patterns before creating new ones

**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component

**Best Practices:**
	- Use Shadcn/UI as the primary component library for consistency and accessibility
	- Import path: ./components/[component-name]

**Export Conventions:**
	- Components MUST use named exports (export const ComponentName = ...)
	- Pages MUST use default exports (export default function PageName() {...})

**Toasts:**
  - Use `sonner` for toasts"
  - Sonner component are located in `/app/src/components/ui/sonner.tsx`

Use 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.
</General UI UX Design Guidelines>
