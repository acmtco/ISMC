import { Camera, FileDown } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useCreateAct } from "@/api/hooks";
import { classLabel, deviationTypeLabel } from "@/lib/labels";
import { formatDateTime } from "@/lib/utils";
import type { DeviationOut } from "@/api/types";

import { DisagreeDialog } from "./DisagreeDialog";

function planFactChartData(dev: DeviationOut) {
  const keys = new Set([...Object.keys(dev.observed ?? {}), ...Object.keys(dev.expected ?? {})]);
  return [...keys].map((key) => ({
    name: classLabel(key),
    план: (dev.expected as Record<string, number>)?.[key] ?? 0,
    факт: (dev.observed as Record<string, number>)?.[key] ?? 0,
  }));
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function DeviationCard({ deviation }: { deviation: DeviationOut }) {
  const createAct = useCreateAct(deviation.deviation_id);
  const chartData = planFactChartData(deviation);
  const acted = deviation.status === "acted";

  return (
    <Card>
      <CardHeader className="flex-col items-start gap-2">
        <div className="flex w-full items-center justify-between">
          <CardTitle className="text-base text-text">
            {deviation.deviation_id} · {deviationTypeLabel(deviation.type)}
          </CardTitle>
          <SeverityBadge severity={deviation.severity} />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
          <span>зона {deviation.zone_id}</span>
          {deviation.work_id && <span>работа {deviation.work_id}</span>}
          <span>
            {deviation.period.from} – {deviation.period.to}
          </span>
          <span>обнаружено {formatDateTime(deviation.detected_at)}</span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={Math.max(chartData.length * 48, 80)}>
            <BarChart data={chartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
              <XAxis type="number" stroke="hsl(var(--text-muted))" fontSize={12} />
              <YAxis type="category" dataKey="name" stroke="hsl(var(--text-muted))" fontSize={12} width={140} />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--surface))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="план" fill="hsl(var(--text-muted) / 0.35)" radius={2} />
              <Bar dataKey="факт" fill="hsl(var(--status-red))" radius={2} />
            </BarChart>
          </ResponsiveContainer>
        )}

        <p className="text-sm leading-relaxed">{deviation.explanation}</p>

        <div className="rounded border border-border bg-bg px-3 py-2 text-sm">
          <span className="text-text-muted">Рекомендация: </span>
          {deviation.recommendation}
        </div>

        {(deviation.evidence.frames ?? []).length > 0 && (
          <div>
            <div className="mb-1.5 text-xs text-text-muted">Кадры-улики</div>
            <div className="flex flex-wrap gap-2">
              {(deviation.evidence.frames ?? []).map((frame) => (
                <div
                  key={frame}
                  className="flex items-center gap-1.5 rounded border border-border bg-bg px-2 py-1.5 text-xs text-text-muted"
                  title={frame}
                >
                  <Camera className="h-3.5 w-3.5" />
                  {frame.split("/").pop()}
                </div>
              ))}
            </div>
          </div>
        )}

        <Separator />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <ConfidenceMeter value={deviation.evidence.confidence} label="Уверенность" />
          <div className="flex items-center gap-2">
            {acted && <Badge variant="gray">акт сформирован</Badge>}
            {createAct.isError && (
              <span className="text-xs text-status-red">
                Недоступно без бэкенда — акт формирует сервер.
              </span>
            )}
            <DisagreeDialog deviationId={deviation.deviation_id} />
            <Button
              onClick={async () => {
                try {
                  const blob = await createAct.mutateAsync();
                  downloadBlob(blob, `act-${deviation.deviation_id}.pdf`);
                } catch {
                  // ошибка уже отражена через createAct.isError выше
                }
              }}
              disabled={createAct.isPending}
            >
              <FileDown className="h-4 w-4" />
              {createAct.isPending ? "Формирую…" : "Сформировать акт"}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
