import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { classLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { DetectedObjectOut } from "@/api/types";

interface ClassSummary {
  cls: string;
  active: number;
  idle: number;
  parked: number;
  total: number;
}

function summarize(objects: DetectedObjectOut[]): ClassSummary[] {
  const byClass = new Map<string, ClassSummary>();
  for (const obj of objects) {
    const row = byClass.get(obj.cls) ?? { cls: obj.cls, active: 0, idle: 0, parked: 0, total: 0 };
    row.total += 1;
    if (obj.state === "active") row.active += 1;
    else if (obj.state === "idle") row.idle += 1;
    else if (obj.state === "parked") row.parked += 1;
    byClass.set(obj.cls, row);
  }
  return [...byClass.values()].sort((a, b) => b.total - a.total);
}

export function NowPanel({ objects }: { objects: DetectedObjectOut[] }) {
  const rows = summarize(objects);

  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Сейчас на площадке</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-text-muted">Техника не зафиксирована.</CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Сейчас на площадке</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {rows.map((row) => (
          <div key={row.cls} className="flex items-center justify-between">
            <div>
              <div className="text-sm">{classLabel(row.cls)}</div>
              <div className="text-3xl font-semibold tabular">{row.total}</div>
            </div>
            <div className="flex gap-3 text-right text-xs">
              <div>
                <div className={cn("tabular text-lg font-semibold", row.active > 0 && "text-status-green")}>
                  {row.active}
                </div>
                <div className="text-text-muted">работает</div>
              </div>
              <div>
                <div className={cn("tabular text-lg font-semibold", row.idle > 0 && "text-status-yellow")}>
                  {row.idle}
                </div>
                <div className="text-text-muted">простой</div>
              </div>
              <div>
                <div className="tabular text-lg font-semibold text-text-muted">{row.parked}</div>
                <div className="text-text-muted">на приколе</div>
              </div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
