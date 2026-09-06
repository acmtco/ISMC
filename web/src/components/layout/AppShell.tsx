import { BarChart3, Calendar, ListChecks, Radio, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

const NAV = [
  { to: "/setup", label: "Настройка", icon: Wrench },
  { to: "/live", label: "Площадка сейчас", icon: Radio },
  { to: "/gantt", label: "График", icon: Calendar },
  { to: "/deviations", label: "Отклонения", icon: ListChecks },
  { to: "/economics", label: "Экономика", icon: BarChart3 },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface">
        <div className="px-4 py-5">
          <div className="text-sm font-semibold tracking-wide">ХРОНОГРАФ</div>
          <div className="text-xs text-text-muted">видео → машино-часы</div>
        </div>
        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded px-2.5 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-surface-hover text-text"
                    : "text-text-muted hover:bg-surface-hover hover:text-text",
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-6 py-6">{children}</div>
      </main>
    </div>
  );
}
