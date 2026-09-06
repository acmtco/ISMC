import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { StatusLight } from "@/components/StatusLight";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate, formatNumber } from "@/lib/utils";
import type { WorkProgressOut } from "@/api/types";

const STATUS_HEX: Record<string, string> = {
  green: "#3fb964",
  yellow: "#e0b13f",
  red: "#e0544a",
};

export function GanttChart({ works }: { works: WorkProgressOut[] }) {
  const chartData = works.map((w) => ({
    name: w.name,
    plan: Math.round(w.mh_plan_to_date * 10) / 10,
    fact: Math.round(w.mh_fact_to_date * 10) / 10,
    status: w.status,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>План vs факт, машино-часы нарастающим итогом</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={Math.max(works.length * 64, 140)}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
            <XAxis type="number" stroke="hsl(var(--text-muted))" fontSize={12} />
            <YAxis
              type="category"
              dataKey="name"
              stroke="hsl(var(--text-muted))"
              fontSize={12}
              width={160}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(var(--surface))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 6,
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="plan" name="План" fill="hsl(var(--text-muted) / 0.35)" radius={2} />
            <Bar dataKey="fact" name="Факт" radius={2}>
              {chartData.map((d) => (
                <Cell key={d.name} fill={STATUS_HEX[d.status]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        <div className="mt-4 flex flex-col gap-3">
          {works.map((w) => (
            <div
              key={w.work_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded border border-border px-3 py-2"
            >
              <div>
                <div className="text-sm font-medium">{w.name}</div>
                <div className="text-xs text-text-muted">
                  SPI {formatNumber(w.spi, 2)} · темп {formatNumber(w.rate_mh_per_day, 1)} маш.-ч/сут
                </div>
              </div>
              <div className="flex items-center gap-3">
                {w.forecast_finish && (
                  <div className="text-right text-xs">
                    <div className="text-text-muted">прогноз завершения</div>
                    <div className="tabular font-medium">{formatDate(w.forecast_finish)}</div>
                  </div>
                )}
                {w.delay_days !== null && w.delay_days !== undefined && w.delay_days > 0 && (
                  <div className="text-right text-xs">
                    <div className="text-text-muted">отставание</div>
                    <div className="tabular font-medium text-status-red">+{w.delay_days} сут</div>
                  </div>
                )}
                <StatusLight status={w.status} />
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
