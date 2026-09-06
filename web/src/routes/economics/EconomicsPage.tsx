import { Download } from "lucide-react";

import { DemoBanner } from "@/components/DemoBanner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useEconomics } from "@/api/hooks";
import { DEMO_OBJECT_ID } from "@/api/demo-data";
import { classLabel } from "@/lib/labels";
import { formatRub } from "@/lib/utils";
import type { EconomicsOut } from "@/api/types";

import { TopLossesChart } from "./TopLossesChart";
import { UtilizationTable } from "./UtilizationTable";

const PERIOD_FROM = "2026-09-01";
const PERIOD_TO = "2026-09-30";

function exportCsv(economics: EconomicsOut) {
  const header = ["Зона", "Класс", "Присутствие ч", "Работа ч", "Простой ч", "КИТ", "Стоимость простоя ₽"];
  const rows = economics.by_class.map((r) => [
    r.zone_id,
    classLabel(r.cls),
    r.mh_present,
    r.mh_active,
    r.mh_idle,
    r.utilization,
    r.idle_cost_rub,
  ]);
  const csv = [header, ...rows].map((row) => row.join(";")).join("\n");
  // BOM (U+FEFF) — иначе Excel открывает кириллицу в UTF-8 CSV как кракозябры.
  const blob = new Blob([String.fromCharCode(0xfeff), csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `economics-${economics.object_id}-${economics.period.from}-${economics.period.to}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function EconomicsPage() {
  const objectId = DEMO_OBJECT_ID;
  const economics = useEconomics(objectId, PERIOD_FROM, PERIOD_TO);
  const data = economics.data?.data;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Экономика</h1>
        {data && (
          <Button variant="outline" onClick={() => exportCsv(data)}>
            <Download className="h-4 w-4" />
            Экспорт отчёта
          </Button>
        )}
      </div>
      <DemoBanner isDemo={Boolean(economics.data?.isDemo)} />

      {economics.isLoading && <div className="text-sm text-text-muted">Загрузка…</div>}

      {data && (
        <div className="flex flex-col gap-4">
          <Card>
            <CardContent className="flex items-center justify-between pt-4">
              <div>
                <div className="text-xs text-text-muted">
                  Потери от простоя, {data.period.from} – {data.period.to}
                </div>
                <div className="text-4xl font-semibold tabular text-status-red">
                  {formatRub(data.total_idle_cost_rub)}
                </div>
              </div>
            </CardContent>
          </Card>

          <TopLossesChart rows={data.by_class} />
          <UtilizationTable rows={data.by_class} />
        </div>
      )}
    </div>
  );
}
