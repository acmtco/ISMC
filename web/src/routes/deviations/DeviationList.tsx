import { SeverityBadge } from "@/components/SeverityBadge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn, formatDate } from "@/lib/utils";
import { DEVIATION_TYPE_LABELS } from "@/lib/labels";
import type { DeviationOut, DeviationType, Severity } from "@/api/types";

const TYPE_OPTIONS: Array<{ value: DeviationType | "all"; label: string }> = [
  { value: "all", label: "Все типы" },
  ...(Object.entries(DEVIATION_TYPE_LABELS) as Array<[DeviationType, string]>).map(([value, label]) => ({
    value,
    label,
  })),
];

const SEVERITY_TABS: Array<{ value: Severity | "all"; label: string }> = [
  { value: "all", label: "Все" },
  { value: "high", label: "Высокая" },
  { value: "medium", label: "Средняя" },
  { value: "low", label: "Низкая" },
];

export function DeviationList({
  deviations,
  typeFilter,
  onTypeFilterChange,
  severityFilter,
  onSeverityFilterChange,
  selectedId,
  onSelect,
}: {
  deviations: DeviationOut[];
  typeFilter: DeviationType | "all";
  onTypeFilterChange: (v: DeviationType | "all") => void;
  severityFilter: Severity | "all";
  onSeverityFilterChange: (v: Severity | "all") => void;
  selectedId: string | undefined;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <Select value={typeFilter} onValueChange={(v) => onTypeFilterChange(v as DeviationType | "all")}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TYPE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Tabs value={severityFilter} onValueChange={(v) => onSeverityFilterChange(v as Severity | "all")}>
          <TabsList>
            {SEVERITY_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div className="flex flex-col gap-1.5">
        {deviations.length === 0 && (
          <p className="px-2 py-4 text-sm text-text-muted">Отклонений не найдено.</p>
        )}
        {deviations.map((d) => (
          <button
            key={d.deviation_id}
            onClick={() => onSelect(d.deviation_id)}
            className={cn(
              "flex flex-col gap-1 rounded border px-3 py-2 text-left transition-colors",
              d.deviation_id === selectedId
                ? "border-text/30 bg-surface-hover"
                : "border-border bg-surface hover:bg-surface-hover",
            )}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{d.deviation_id}</span>
              <SeverityBadge severity={d.severity} />
            </div>
            <div className="text-xs text-text-muted">
              {DEVIATION_TYPE_LABELS[d.type]} · {d.zone_id} · {formatDate(d.period.to)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
