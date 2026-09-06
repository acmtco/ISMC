import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

/** Индикатор доверия к данным (quality.score / evidence.confidence) —
 * единственное место, где цвет несёт смысл "можно ли верить числам ниже". */
export function ConfidenceMeter({ value, label = "Доверие к данным" }: { value: number; label?: string }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.7 ? "bg-status-green" : value >= 0.5 ? "bg-status-yellow" : "bg-status-red";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted">{label}</span>
      <Progress value={pct} className="w-24" indicatorClassName={color} />
      <span className={cn("tabular text-xs font-medium", value < 0.5 && "text-status-red")}>{pct}%</span>
    </div>
  );
}
