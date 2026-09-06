import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { classLabel } from "@/lib/labels";
import { cn, formatNumber, formatRub } from "@/lib/utils";
import type { UtilizationRowOut } from "@/api/types";

export function UtilizationTable({ rows }: { rows: UtilizationRowOut[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>КИТ по единицам техники</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <THead>
            <TR>
              <TH>Зона</TH>
              <TH>Класс</TH>
              <TH className="text-right">Присутствие, ч</TH>
              <TH className="text-right">Работа, ч</TH>
              <TH className="text-right">Простой, ч</TH>
              <TH className="text-right">КИТ</TH>
              <TH className="text-right">Стоимость простоя</TH>
            </TR>
          </THead>
          <TBody>
            {rows.map((row) => (
              <TR key={`${row.zone_id}-${row.cls}`}>
                <TD className="text-text-muted">{row.zone_id}</TD>
                <TD>{classLabel(row.cls)}</TD>
                <TD className="text-right">{formatNumber(row.mh_present)}</TD>
                <TD className="text-right">{formatNumber(row.mh_active)}</TD>
                <TD className="text-right">{formatNumber(row.mh_idle)}</TD>
                <TD
                  className={cn(
                    "text-right font-medium",
                    row.utilization < 0.5 && "text-status-red",
                    row.utilization >= 0.5 && row.utilization < 0.75 && "text-status-yellow",
                    row.utilization >= 0.75 && "text-status-green",
                  )}
                >
                  {formatNumber(row.utilization * 100, 0)}%
                </TD>
                <TD className="text-right">{formatRub(row.idle_cost_rub)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}
