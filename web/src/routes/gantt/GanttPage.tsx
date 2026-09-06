import { useState } from "react";

import { DemoBanner } from "@/components/DemoBanner";
import { Card, CardContent } from "@/components/ui/card";
import { useGantt } from "@/api/hooks";
import { DEMO_OBJECT_ID } from "@/api/demo-data";

import { GanttChart } from "./GanttChart";
import { TimeMachineSlider } from "./TimeMachineSlider";

const PERIOD_FROM = "2026-09-01";
const PERIOD_TO = "2026-09-30";

export function GanttPage() {
  const objectId = DEMO_OBJECT_ID;
  const [currentDate, setCurrentDate] = useState(PERIOD_TO);
  const gantt = useGantt(objectId, PERIOD_FROM, currentDate);

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">План vs факт по работам</h1>
      <DemoBanner isDemo={Boolean(gantt.data?.isDemo)} />

      <Card className="mb-4">
        <CardContent className="pt-4">
          <TimeMachineSlider
            from={PERIOD_FROM}
            to={PERIOD_TO}
            currentDate={currentDate}
            onChange={setCurrentDate}
          />
        </CardContent>
      </Card>

      {gantt.isLoading && <div className="text-sm text-text-muted">Загрузка…</div>}
      {gantt.data && gantt.data.data.works.length > 0 && <GanttChart works={gantt.data.data.works} />}
      {gantt.data && gantt.data.data.works.length === 0 && (
        <p className="text-sm text-text-muted">
          На {currentDate} нет работ, покрывающих этот период, — импортируйте график на странице «Настройка».
        </p>
      )}
    </div>
  );
}
