import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { classLabel } from "@/lib/labels";
import { formatRub } from "@/lib/utils";
import type { UtilizationRowOut } from "@/api/types";

export function TopLossesChart({ rows }: { rows: UtilizationRowOut[] }) {
  const data = [...rows]
    .sort((a, b) => b.idle_cost_rub - a.idle_cost_rub)
    .slice(0, 6)
    .map((r) => ({ name: `${classLabel(r.cls)} · ${r.zone_id}`, loss: r.idle_cost_rub }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Топ причин потерь</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={Math.max(data.length * 44, 100)}>
          <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
            <XAxis type="number" stroke="hsl(var(--text-muted))" fontSize={12} tickFormatter={(v) => formatRub(v)} />
            <YAxis type="category" dataKey="name" stroke="hsl(var(--text-muted))" fontSize={12} width={180} />
            <Tooltip
              formatter={(v: number) => formatRub(v)}
              contentStyle={{
                background: "hsl(var(--surface))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 6,
                fontSize: 12,
              }}
            />
            <Bar dataKey="loss" name="Потери" fill="hsl(var(--status-red))" radius={2} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
