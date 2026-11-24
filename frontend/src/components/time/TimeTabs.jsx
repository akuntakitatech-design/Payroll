import React from "react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

/**
 * Sub-navigasi di dalam modul (tanpa menambah menu baru di sidebar).
 * items: [{ to, label, icon, end }]
 */
export const TimeTabs = ({ items = [], className, testId = "time-module-tabs" }) => (
  <nav
    data-testid={testId}
    className={cn("flex gap-1.5 overflow-x-auto border-b border-border bg-card px-4 py-2 sm:px-6", className)}
    aria-label="Navigasi modul"
  >
    {items.filter(Boolean).map((item) => (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.end !== false}
        data-testid={item.testId || `time-tab-${item.to.split("/").pop()}`}
        className={({ isActive }) =>
          cn(
            "inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-transparent px-3 py-1.5 text-[13px] font-semibold transition-[background-color,color,box-shadow,border-color] duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
            isActive
              ? "border-[hsl(var(--primary-active))] bg-[image:var(--gradient-primary)] text-white shadow-[var(--shadow-button-primary)]"
              : "text-ink-2 hover:bg-[hsl(var(--surface-2))] hover:text-ink-1"
          )
        }
      >
        {item.icon && <item.icon className="h-4 w-4" strokeWidth={1.75} />}
        {item.label}
      </NavLink>
    ))}
  </nav>
);

export default TimeTabs;
