import { Check, Trash2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useUpdateZones } from "@/api/hooks";
import type { ZoneIn } from "@/api/types";

const WIDTH = 960;
const HEIGHT = 540;

/** Разметка зон полигонами мышью прямо на кадре: клик добавляет точку,
 * двойной клик (или Enter) замыкает полигон — от 3 точек. Реального кадра
 * с бэкенда браузер получить не может (нет файлового сервера в контракте
 * API), поэтому рисуем поверх той же системы координат, что и настоящий
 * кадр (см. FrameCanvas на /live) — разметка 1:1 переносится в детекцию. */
export function ZoneDrawStep({ cameraId }: { cameraId: string }) {
  const [zones, setZones] = useState<ZoneIn[]>([]);
  const [currentPoints, setCurrentPoints] = useState<[number, number][]>([]);
  const [pendingTitle, setPendingTitle] = useState("");
  const updateZones = useUpdateZones(cameraId);

  function handleSvgClick(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.round(((e.clientX - rect.left) / rect.width) * WIDTH);
    const y = Math.round(((e.clientY - rect.top) / rect.height) * HEIGHT);
    setCurrentPoints((prev) => [...prev, [x, y]]);
  }

  function finishZone() {
    if (currentPoints.length < 3) return;
    const zoneId = `Z-${(zones.length + 1).toString().padStart(2, "0")}`;
    setZones((prev) => [
      ...prev,
      { zone_id: zoneId, title: pendingTitle || zoneId, polygon: currentPoints },
    ]);
    setCurrentPoints([]);
    setPendingTitle("");
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        Кликайте по кадру, чтобы добавлять точки полигона зоны. Минимум 3 точки, затем «Завершить
        зону».
      </p>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        onClick={handleSvgClick}
        className="w-full cursor-crosshair rounded border border-border bg-bg"
        style={{ aspectRatio: `${WIDTH} / ${HEIGHT}` }}
      >
        <rect width={WIDTH} height={HEIGHT} className="fill-bg" />

        {zones.map((zone) => (
          <g key={zone.zone_id}>
            <polygon
              points={zone.polygon.map((p) => p.join(",")).join(" ")}
              fill="hsl(var(--status-green) / 0.12)"
              stroke="hsl(var(--status-green) / 0.6)"
              strokeWidth={1.5}
            />
            <text x={zone.polygon[0][0] + 6} y={zone.polygon[0][1] + 16} className="fill-text text-[12px]">
              {zone.title}
            </text>
          </g>
        ))}

        {currentPoints.length > 0 && (
          <g>
            <polyline
              points={currentPoints.map((p) => p.join(",")).join(" ")}
              fill="none"
              stroke="hsl(var(--text) / 0.6)"
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
            {currentPoints.map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r={3.5} fill="hsl(var(--text))" />
            ))}
          </g>
        )}
      </svg>

      {currentPoints.length > 0 && (
        <div className="flex items-center gap-2">
          <Input
            placeholder="Название зоны"
            value={pendingTitle}
            onChange={(e) => setPendingTitle(e.target.value)}
            className="max-w-xs"
          />
          <Button onClick={finishZone} disabled={currentPoints.length < 3}>
            <Check className="h-4 w-4" />
            Завершить зону ({currentPoints.length} точ.)
          </Button>
          <Button variant="ghost" onClick={() => setCurrentPoints([])}>
            <X className="h-4 w-4" />
            Отменить
          </Button>
        </div>
      )}

      {zones.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {zones.map((zone) => (
            <div
              key={zone.zone_id}
              className="flex items-center justify-between rounded border border-border px-3 py-1.5 text-sm"
            >
              <span>
                {zone.title} <span className="text-text-muted">({zone.zone_id})</span>
              </span>
              <button
                onClick={() => setZones((prev) => prev.filter((z) => z.zone_id !== zone.zone_id))}
                className="text-text-muted hover:text-status-red"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={() => updateZones.mutate(zones)} disabled={zones.length === 0 || updateZones.isPending}>
          {updateZones.isPending ? "Сохраняю…" : "Сохранить зоны"}
        </Button>
        {updateZones.isSuccess && <span className="text-sm text-status-green">Сохранено</span>}
        {updateZones.isError && (
          <span className="text-sm text-status-red">Не удалось сохранить — бэкенд недоступен.</span>
        )}
      </div>
    </div>
  );
}
