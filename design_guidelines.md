{
  "design_personality": {
    "brand_attributes": [
      "Profesional",
      "Tenang & terpercaya (compliance/payroll)",
      "Minimal, rapi, tidak ramai",
      "Action-oriented (fokus ke Perlu Tindakan & Persetujuan)",
      "Enterprise-ready (tabel padat tapi tetap terbaca)"
    ],
    "ux_principles": [
      "Exception-based UX: tampilkan yang butuh tindakan dulu, sisanya otomatis",
      "Input sekali, pakai di mana-mana: gunakan pola dialog + inline validation",
      "Scannable density: tabel rapat dengan spacing konsisten, filter selalu terlihat",
      "No decorative charts-first: dashboard utamakan daftar aksi & status"
    ],
    "layout_archetype": {
      "desktop": "Collapsible sidebar + topbar + content container (max-w none, full width) + sticky page header",
      "mobile": "Topbar + Sheet drawer navigation + bottom-safe padding; tables become cards/stacked rows"
    }
  },

  "design_tokens": {
    "notes": [
      "Gunakan solid colors untuk area baca. Gradien hanya dekoratif dan maksimal 20% viewport (mis. strip tipis di header dashboard).",
      "Tidak ada background transparan; semua surface harus solid agar konsisten di OS theme apa pun.",
      "Semua token di bawah ditulis sebagai CSS variables di /app/frontend/src/index.css (replace default shadcn tokens)."
    ],

    "css_variables_index_css": {
      "google_fonts_import": "@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600&family=Figtree:wght@400;500;600&display=swap');",

      "root_hsl_tokens": {
        "--background": "36 33% 97%",
        "--foreground": "174 28% 12%",

        "--card": "0 0% 100%",
        "--card-foreground": "174 28% 12%",

        "--popover": "0 0% 100%",
        "--popover-foreground": "174 28% 12%",

        "--primary": "173 80% 26%",
        "--primary-foreground": "0 0% 98%",

        "--secondary": "174 22% 93%",
        "--secondary-foreground": "174 28% 14%",

        "--muted": "36 18% 93%",
        "--muted-foreground": "174 10% 38%",

        "--accent": "174 30% 92%",
        "--accent-foreground": "174 28% 14%",

        "--destructive": "0 72% 52%",
        "--destructive-foreground": "0 0% 98%",

        "--border": "174 18% 86%",
        "--input": "174 18% 86%",
        "--ring": "173 80% 26%",

        "--radius": "0.75rem",

        "--chart-1": "173 80% 26%",
        "--chart-2": "199 70% 38%",
        "--chart-3": "43 74% 56%",
        "--chart-4": "160 45% 38%",
        "--chart-5": "0 72% 52%"
      },

      "additional_custom_tokens": {
        "--font-sans": "'Figtree', ui-sans-serif, system-ui",
        "--font-display": "'Space Grotesk', ui-sans-serif, system-ui",

        "--shadow-sm": "0 1px 0 rgba(12, 33, 30, 0.04)",
        "--shadow-md": "0 10px 24px rgba(12, 33, 30, 0.08)",

        "--surface-1": "hsl(var(--background))",
        "--surface-2": "hsl(0 0% 100%)",
        "--surface-3": "hsl(174 22% 95%)",

        "--focus-ring": "0 0 0 3px hsl(173 80% 26% / 0.18)",

        "--severity-critical": "0 72% 52%",
        "--severity-warning": "43 74% 56%",
        "--severity-info": "199 70% 38%",
        "--severity-neutral": "174 10% 38%"
      },

      "base_layer_additions": {
        "body": "font-family: var(--font-sans);",
        "headings": "h1,h2,h3 { font-family: var(--font-display); letter-spacing: -0.02em; }",
        "numbers": "[data-numeric='true'] { font-variant-numeric: tabular-nums; }",
        "selection": "::selection { background: hsl(174 30% 88%); }"
      },

      "allowed_micro_gradient": {
        "usage": "Hanya sebagai aksen dekoratif di header dashboard (strip tipis) atau empty state illustration background.",
        "css_example": "background: linear-gradient(90deg, hsl(174 30% 92%), hsl(36 33% 97%), hsl(199 40% 92%));"
      },

      "noise_texture": {
        "usage": "Tambahkan noise halus pada page background untuk menghindari flat look (opsional).",
        "css_example": ".app-noise { background-image: url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"120\" height=\"120\"><filter id=\"n\"><feTurbulence type=\"fractalNoise\" baseFrequency=\"0.9\" numOctaves=\"2\" stitchTiles=\"stitch\"/></filter><rect width=\"120\" height=\"120\" filter=\"url(%23n)\" opacity=\"0.035\"/></svg>'); background-repeat: repeat; }"
      }
    },

    "spacing_density": {
      "cadence_px": [4, 8, 12, 16, 24, 32, 48],
      "page_padding": {
        "mobile": "px-4 py-4",
        "desktop": "px-6 py-6",
        "wide": "px-8 py-8"
      },
      "card_padding": "p-4 sm:p-5",
      "table_density": {
        "row_height": "h-10 (default), h-12 for touch/mobile",
        "cell_padding": "px-3 py-2",
        "header": "text-xs font-medium tracking-wide uppercase text-muted-foreground"
      }
    },

    "radius": {
      "card": "rounded-xl",
      "input": "rounded-lg",
      "button": "rounded-lg",
      "pill": "rounded-full"
    }
  },

  "typography": {
    "font_pairing": {
      "display": "Space Grotesk (500/600)",
      "body": "Figtree (400/500)",
      "notes": "Keduanya modern, corporate, dan sangat terbaca untuk tabel padat."
    },
    "text_size_hierarchy_tailwind": {
      "h1": "text-4xl sm:text-5xl lg:text-6xl",
      "h2": "text-base md:text-lg",
      "body": "text-sm sm:text-base",
      "small": "text-xs text-muted-foreground"
    },
    "component_type_rules": [
      "Page title pakai font-display + tracking-tight.",
      "Label form selalu text-sm font-medium.",
      "Tabel: body text-sm; angka gunakan data-numeric='true'.",
      "Badge/status gunakan text-xs font-medium."
    ]
  },

  "grid_and_responsive": {
    "breakpoints": {
      "mobile_first": true,
      "sidebar": "hidden < lg; collapsible >= lg",
      "content_max_width": "Jangan pakai max-w sempit; gunakan container fluid dengan padding tokens."
    },
    "dashboard_layout": {
      "desktop": "Grid 12 kolom: kiri (8) untuk Perlu Tindakan + feed; kanan (4) untuk checklist setup + ringkasan.",
      "mobile": "Single column; sections become stacked cards; action buttons full-width."
    },
    "tables_on_mobile": [
      "Gunakan mode 'stacked rows': setiap row jadi Card dengan key fields + kebab menu.",
      "FilterBar tetap di atas (sticky) dengan tombol 'Filter' membuka Sheet."
    ]
  },

  "component_recipes": {
    "component_path": {
      "button": "/app/frontend/src/components/ui/button.jsx",
      "card": "/app/frontend/src/components/ui/card.jsx",
      "badge": "/app/frontend/src/components/ui/badge.jsx",
      "table": "/app/frontend/src/components/ui/table.jsx",
      "pagination": "/app/frontend/src/components/ui/pagination.jsx",
      "dialog": "/app/frontend/src/components/ui/dialog.jsx",
      "alert_dialog": "/app/frontend/src/components/ui/alert-dialog.jsx",
      "dropdown_menu": "/app/frontend/src/components/ui/dropdown-menu.jsx",
      "select": "/app/frontend/src/components/ui/select.jsx",
      "input": "/app/frontend/src/components/ui/input.jsx",
      "textarea": "/app/frontend/src/components/ui/textarea.jsx",
      "tabs": "/app/frontend/src/components/ui/tabs.jsx",
      "sheet": "/app/frontend/src/components/ui/sheet.jsx",
      "drawer": "/app/frontend/src/components/ui/drawer.jsx",
      "command": "/app/frontend/src/components/ui/command.jsx",
      "breadcrumb": "/app/frontend/src/components/ui/breadcrumb.jsx",
      "separator": "/app/frontend/src/components/ui/separator.jsx",
      "progress": "/app/frontend/src/components/ui/progress.jsx",
      "switch": "/app/frontend/src/components/ui/switch.jsx",
      "calendar": "/app/frontend/src/components/ui/calendar.jsx",
      "sonner": "/app/frontend/src/components/ui/sonner.jsx",
      "tooltip": "/app/frontend/src/components/ui/tooltip.jsx",
      "scroll_area": "/app/frontend/src/components/ui/scroll-area.jsx",
      "skeleton": "/app/frontend/src/components/ui/skeleton.jsx"
    },

    "app_shell": {
      "layout": {
        "desktop": "Sidebar (w-64 collapsed w-16) + main content; Topbar sticky top-0; content scroll independent.",
        "mobile": "Topbar with hamburger -> Sheet; optional bottom safe padding pb-20 for long forms."
      },
      "sidebar": {
        "groups": [
          "Ringkasan",
          "Karyawan (placeholder)",
          "Persetujuan",
          "Dokumen",
          "Setup",
          "Keamanan & Audit"
        ],
        "nav_item_style": "flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "active_state": "bg-accent text-foreground font-medium",
        "collapsed_behavior": "Icon-only + Tooltip; group labels hidden.",
        "data_testids": {
          "sidebar": "app-sidebar",
          "toggle": "sidebar-collapse-toggle",
          "nav_item": "sidebar-nav-item-<route-key>"
        }
      },
      "topbar": {
        "elements": [
          "CompanySwitcher",
          "GlobalSearch placeholder (Command)",
          "Quick actions (optional)",
          "User menu"
        ],
        "style": "h-14 bg-card/100 border-b border-border",
        "data_testids": {
          "topbar": "app-topbar",
          "global_search": "global-search-trigger",
          "user_menu": "user-menu-trigger"
        }
      }
    },

    "company_switcher": {
      "pattern": "DropdownMenu + searchable Command list inside Popover/Dropdown",
      "behavior": [
        "Menampilkan hanya perusahaan yang user punya akses",
        "Saat switch: tampilkan loading state + toast sukses",
        "Jika gagal: toast error + tetap di company sebelumnya"
      ],
      "microcopy_id": {
        "label": "Perusahaan",
        "search_placeholder": "Cari perusahaan…",
        "empty": "Tidak ada perusahaan yang cocok.",
        "loading": "Mengganti konteks perusahaan…"
      },
      "data_testids": {
        "trigger": "company-switcher-trigger",
        "search": "company-switcher-search-input",
        "item": "company-switcher-item-<company-id>"
      }
    },

    "page_header": {
      "structure": "Breadcrumb (optional) + Title + Subtitle + Primary action + Secondary actions",
      "style": "sticky top-14 z-10 bg-background/100 border-b border-border",
      "title_class": "font-display text-xl sm:text-2xl tracking-tight",
      "subtitle_class": "text-sm text-muted-foreground",
      "actions": "Primary button right aligned on desktop; stacked full-width on mobile",
      "data_testids": {
        "container": "page-header",
        "primary_action": "page-header-primary-action"
      }
    },

    "dashboard": {
      "sections": {
        "perlu_tindakan": {
          "component": "SeverityCalloutList",
          "card_style": "Card with left severity rail (w-1) + title/desc + action button",
          "severity_colors": {
            "critical": "bg-[hsl(var(--severity-critical))]",
            "warning": "bg-[hsl(var(--severity-warning))]",
            "info": "bg-[hsl(var(--severity-info))]"
          },
          "data_testids": {
            "list": "dashboard-needs-attention-list",
            "item": "dashboard-needs-attention-item-<id>",
            "action": "dashboard-needs-attention-item-action-<id>"
          }
        },
        "setup_progress": {
          "component": "Progress + Checklist",
          "style": "Card with Progress bar + 8 checklist items; each item has status badge",
          "data_testids": {
            "card": "dashboard-setup-progress-card",
            "progress": "dashboard-setup-progress-bar"
          }
        },
        "audit_feed": {
          "component": "ScrollArea feed",
          "row": "timestamp + user + action + module; expandable to show record id",
          "data_testids": {
            "card": "dashboard-audit-feed-card"
          }
        },
        "module_tiles": {
          "component": "Bento grid of module cards",
          "style": "Small cards with module name + status Active/Nonaktif + CTA 'Buka' disabled when inactive",
          "data_testids": {
            "grid": "dashboard-module-tiles",
            "tile": "dashboard-module-tile-<module-key>"
          }
        }
      }
    },

    "data_table": {
      "pattern": "Shadcn Table + server-side pagination + column visibility optional",
      "filter_bar": {
        "desktop": "Inline filters row: Search Input + Select filters + Date range (Calendar in Popover) + Reset",
        "mobile": "Search + Filter button opens Sheet with filters",
        "data_testids": {
          "search": "table-search-input",
          "filter_button": "table-filter-open-button",
          "reset": "table-filter-reset-button"
        }
      },
      "row_actions": "DropdownMenu (⋯) with View/Edit/Deactivate/Delete; destructive actions require AlertDialog",
      "empty_state": {
        "title": "Belum ada data.",
        "description": "Tambahkan data pertama untuk mulai menggunakan modul ini.",
        "cta": "Tambah",
        "data_testids": {
          "container": "table-empty-state",
          "cta": "table-empty-state-cta"
        }
      },
      "safe_delete_conflict": {
        "microcopy": "Data ini tidak dapat dihapus karena sudah digunakan oleh transaksi lain. Nonaktifkan data ini agar tidak bisa dipilih lagi.",
        "data_testid": "safe-delete-conflict-message"
      }
    },

    "form_dialog": {
      "pattern": "Dialog + react-hook-form + zod; footer sticky with primary/secondary",
      "validation_tone": "Kalimat lengkap, spesifik, dan menyarankan solusi.",
      "buttons": {
        "primary": "Simpan",
        "secondary": "Batal",
        "destructive": "Hapus"
      },
      "data_testids": {
        "dialog": "form-dialog",
        "submit": "form-dialog-submit-button",
        "cancel": "form-dialog-cancel-button"
      }
    },

    "status_badge": {
      "use": "Aktif/Nonaktif, Draft/Aktif, Terkunci",
      "classes": {
        "aktif": "bg-[hsl(174_30%_92%)] text-[hsl(173_80%_20%)] border border-[hsl(174_18%_86%)]",
        "nonaktif": "bg-muted text-muted-foreground border border-border",
        "draft": "bg-[hsl(43_74%_92%)] text-[hsl(43_74%_30%)] border border-[hsl(43_40%_80%)]"
      },
      "data_testid": "status-badge"
    },

    "severity_callout": {
      "pattern": "Card row with severity rail + Badge + action",
      "interaction": "Hover: background accent; Focus: ring; Button press scale 0.98",
      "data_testid": "severity-callout"
    },

    "placeholder_module_page": {
      "structure": "PageHeader + Card with 'Akan hadir di fase berikutnya' + bullet list 'Yang akan tersedia' + disabled CTA",
      "microcopy_id": {
        "title": "Akan hadir di fase berikutnya",
        "desc": "Modul ini belum aktif pada fase FOUNDATION. Anda tetap bisa menyiapkan master data dan alur persetujuan terlebih dahulu."
      },
      "data_testids": {
        "container": "placeholder-module-page",
        "cta": "placeholder-module-primary-cta"
      }
    },

    "permission_matrix": {
      "pattern": "Sticky first column (resource) + horizontally scrollable actions; use ScrollArea",
      "interaction": "Checkbox grid with row/column toggles; show 'Inherited/Locked' state for Super Admin",
      "visual": "Use subtle zebra rows (odd:bg-muted/40) and thin borders",
      "data_testids": {
        "table": "permission-matrix-table",
        "role_select": "permission-matrix-role-select",
        "cell": "permission-matrix-cell-<resource>-<action>"
      }
    },

    "policy_inheritance_card": {
      "pattern": "Tabs: Efektif | Override | Simulator",
      "effective_view": "Show resolved value + badge 'Sumber: Perusahaan/Cabang/Divisi/Proyek/Karyawan'",
      "simulator": "Form selects scope + preview result; show explanation 'Aturan paling spesifik menang'",
      "data_testids": {
        "tabs": "policy-tabs",
        "simulator": "policy-scope-simulator"
      }
    },

    "approval_step_builder": {
      "pattern": "Reorderable list (simple) using buttons Up/Down (avoid heavy canvas for phase 1)",
      "step_card": "Card with step number + approver type Select + SLA Input + mandatory Switch + remove",
      "validation": [
        "Minimal 1 langkah persetujuan",
        "Tidak boleh ada langkah tanpa approver",
        "SLA harus angka >= 0"
      ],
      "data_testids": {
        "list": "approval-step-builder-list",
        "add": "approval-step-add-button",
        "remove": "approval-step-remove-button-<index>",
        "move_up": "approval-step-move-up-<index>",
        "move_down": "approval-step-move-down-<index>"
      }
    },

    "audit_diff_row": {
      "pattern": "Expandable Table row: summary line + chevron; expanded shows before/after JSON diff blocks",
      "diff_visual": "Use two columns: Sebelum (muted) vs Sesudah (accent). Highlight changed fields only.",
      "data_testids": {
        "row": "audit-log-row-<id>",
        "expand": "audit-log-row-expand-<id>",
        "diff": "audit-log-row-diff-<id>"
      }
    }
  },

  "motion_and_microinteractions": {
    "principles": [
      "Hemat animasi (enterprise). Gunakan motion untuk feedback, bukan dekorasi.",
      "Tidak boleh transition: all. Hanya transisi pada color, background-color, border-color, box-shadow, opacity."
    ],
    "tailwind_recipes": {
      "button": "transition-colors duration-150 active:scale-[0.98]",
      "card_hover": "hover:bg-accent/40 transition-colors duration-150",
      "focus": "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
      "drawer_sheet": "Use shadcn Sheet/Drawer default animations; respect prefers-reduced-motion"
    },
    "loading_states": [
      "Gunakan Skeleton untuk tabel dan kartu dashboard",
      "Disable tombol saat submit + tampilkan spinner kecil (lucide Loader2)"
    ]
  },

  "accessibility": {
    "requirements": [
      "WCAG AA contrast untuk teks dan badge",
      "Semua input punya Label dan aria-describedby untuk error",
      "Dialog/Sheet harus keyboard-usable (shadcn sudah)",
      "Focus ring selalu terlihat (gunakan ring token)"
    ],
    "data_testid_rule": "Semua elemen interaktif dan informasi kunci WAJIB punya data-testid (kebab-case)."
  },

  "bahasa_indonesia_microcopy_tone": {
    "tone": [
      "Jelas, sopan, langsung",
      "Hindari istilah teknis internal",
      "Selalu beri langkah berikutnya"
    ],
    "examples": {
      "generic_error_bad": "Transaksi tidak valid.",
      "generic_error_good": "Data tidak bisa disimpan karena 'Tanggal berakhir kontrak' lebih awal dari 'Tanggal mulai penempatan'. Perbaiki tanggal kontrak atau ubah periode penempatan."
    },
    "empty_states": {
      "master_data": "Belum ada data. Tambahkan data pertama agar bisa dipakai di modul lain.",
      "audit": "Belum ada aktivitas audit untuk filter ini. Coba perluas rentang tanggal atau hapus filter."
    }
  },

  "image_urls": {
    "notes": "Aplikasi enterprise ini tidak butuh hero imagery. Gunakan ilustrasi ringan hanya untuk empty/placeholder (opsional).",
    "categories": [
      {
        "category": "empty_state_illustrations",
        "description": "Ilustrasi abstrak ringan untuk empty state (opsional, kecil, tidak dominan).",
        "urls": [
          "https://images.unsplash.com/photo-1557683316-973673baf926?auto=format&fit=crop&w=1200&q=60",
          "https://images.unsplash.com/photo-1557682250-33bd709cbe85?auto=format&fit=crop&w=1200&q=60"
        ]
      },
      {
        "category": "company_logo_placeholders",
        "description": "Gunakan avatar initials (tanpa gambar) sebagai default; tidak perlu URL."
      }
    ]
  },

  "libraries_and_integrations": {
    "recommended_now": [
      {
        "name": "framer-motion",
        "use": "Micro-interactions ringan (collapse sidebar, list entrance).",
        "install": "sudah tersedia",
        "notes": "Batasi animasi; hormati prefers-reduced-motion."
      },
      {
        "name": "recharts",
        "use": "Jika butuh chart kecil (mis. Payroll status) di fase berikutnya.",
        "install": "sudah tersedia",
        "notes": "Jangan jadikan chart fokus utama dashboard."
      }
    ],
    "avoid_for_phase_1": [
      "React Flow canvas workflow builder (terlalu berat untuk FOUNDATION). Gunakan builder list reorder dulu.",
      "Three.js / R3F (tidak relevan untuk enterprise HRIS)."
    ]
  },

  "instructions_to_main_agent": [
    "Update /app/frontend/src/App.css: hapus styling CRA default (.App-header center, logo spin) agar tidak mengganggu layout enterprise.",
    "Update /app/frontend/src/index.css: ganti token :root sesuai design_tokens.css_variables_index_css.root_hsl_tokens + tambahkan font import dan custom tokens.",
    "Gunakan shadcn/ui components sebagai dasar (Button, Card, Table, Dialog, Sheet, DropdownMenu, Command, Tabs, ScrollArea, Pagination, Calendar).",
    "Pastikan sidebar menyembunyikan modul nonaktif dan item tanpa permission (backend tetap enforce).",
    "Semua tombol/inputs/menu items/row expanders/CTA wajib punya data-testid kebab-case.",
    "Bahasa Indonesia untuk semua label, helper text, empty state, dan error.",
    "Jangan gunakan gradient besar; jika butuh aksen, gunakan strip tipis di header dashboard saja (<20% viewport).",
    "Jangan gunakan transition: all; gunakan transition-colors saja pada elemen interaktif."
  ],

  "GENERAL_UI_UX_DESIGN_GUIDELINES": [
    "- You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms",
    "- You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text",
    "- NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json",
    "",
    " **GRADIENT RESTRICTION RULE**",
    "NEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc",
    "NEVER use dark gradients for logo, testimonial, footer etc",
    "NEVER let gradients cover more than 20% of the viewport.",
    "NEVER apply gradients to text-heavy content or reading areas.",
    "NEVER use gradients on small UI elements (<100px width).",
    "NEVER stack multiple gradient layers in the same viewport.",
    "",
    "**ENFORCEMENT RULE:**",
    "    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors",
    "",
    "**How and where to use:**",
    "   • Section backgrounds (not content backgrounds)",
    "   • Hero section header content. Eg: dark to light to dark color",
    "   • Decorative overlays and accent elements only",
    "   • Hero section with 2-3 mild color",
    "   • Gradients creation can be done for any angle say horizontal, vertical or diagonal",
    "",
    "- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc",
    "",
    "</Font Guidelines>",
    "",
    "- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead.",
    "",
    "- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.",
    "",
    "- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.",
    "",
    "- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly",
    "    Eg: - if it implies playful/energetic, choose a colorful scheme",
    "           - if it implies monochrome/minimal, choose a black–white/neutral scheme",
    "",
    "**Component Reuse:**",
    "\t- Prioritize using pre-existing components from src/components/ui when applicable",
    "\t- Create new components that match the style and conventions of existing components when needed",
    "\t- Examine existing components to understand the project's component patterns before creating new ones",
    "",
    "**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component",
    "",
    "**Best Practices:**",
    "\t- Use Shadcn/UI as the primary component library for consistency and accessibility",
    "\t- Import path: ./components/[component-name]",
    "",
    "**Export Conventions:**",
    "\t- Components MUST use named exports (export const ComponentName = ...)",
    "\t- Pages MUST use default exports (export default function PageName() {...})",
    "",
    "**Toasts:**",
    "  - Use `sonner` for toasts\"",
    "  - Sonner component are located in `/app/src/components/ui/sonner.tsx`",
    "",
    "Use 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals."
  ]
}
