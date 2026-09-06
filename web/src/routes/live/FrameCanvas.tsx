import { classLabel } from "@/lib/labels";
import type { DetectedObjectOut, EquipmentState, ZoneOut } from "@/api/types";

const STATE_COLOR: Record<EquipmentState, string> = {
  active: "hsl(var(--status-green))",
  idle: "hsl(var(--status-yellow))",
  parked: "hsl(var(--status-gray))",
  unknown: "hsl(var(--status-gray))",
};

/** Кадр камеры как SVG-схема: реального JPEG с бэкенда браузеру не отдать
 * без отдельного файлового сервера (вне контракта API), поэтому рисуем
 * зоны и боксы поверх той же системы координат, что и настоящий кадр —
 * тот же слой, что покажет живая картинка, когда файлы станут доступны. */
export function FrameCanvas({
  zones,
  objects,
  width = 960,
  height = 540,
}: {
  zones: ZoneOut[];
  objects: DetectedObjectOut[];
  width?: number;
  height?: number;
}) {
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full rounded border border-border bg-bg"
      style={{ aspectRatio: `${width} / ${height}` }}
    >
      <rect width={width} height={height} className="fill-bg" />

      {zones.map((zone) => {
        const points = zone.polygon.map((p) => p.join(",")).join(" ");
        return (
          <g key={zone.zone_id}>
            <polygon
              points={points}
              fill="hsl(var(--text) / 0.06)"
              stroke="hsl(var(--text) / 0.3)"
              strokeWidth={1.5}
            />
            <text
              x={zone.polygon[0][0] + 6}
              y={zone.polygon[0][1] + 16}
              className="fill-text-muted text-[11px]"
            >
              {zone.title || zone.zone_id}
            </text>
          </g>
        );
      })}

      {objects.map((obj) => {
        const [x, y, w, h] = obj.bbox;
        const color = STATE_COLOR[obj.state as EquipmentState] ?? STATE_COLOR.unknown;
        return (
          <g key={obj.track_id}>
            <rect x={x} y={y} width={w} height={h} fill="none" stroke={color} strokeWidth={2} />
            <rect x={x} y={y - 16} width={Math.max(w, 70)} height={16} fill={color} opacity={0.85} />
            <text x={x + 4} y={y - 4} className="text-[11px] font-medium" fill="hsl(var(--bg))">
              {classLabel(obj.cls)} #{obj.track_id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
