import { Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/utils";

const DAY_MS = 24 * 60 * 60 * 1000;
const TICK_MS = 250; // "тридцать суток за десять секунд" — docs/05-pitch.md

function daysBetween(from: string, to: string): number {
  return Math.round((new Date(to).getTime() - new Date(from).getTime()) / DAY_MS);
}

function addDays(iso: string, days: number): string {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** "Машина времени": прокручивает диапазон [from, to] и на каждом тике
 * сообщает родителю текущую дату, чтобы тот перезапросил `/gantt` на эту
 * дату — так весь период проигрывается, а не просто выбирается точка. */
export function TimeMachineSlider({
  from,
  to,
  currentDate,
  onChange,
}: {
  from: string;
  to: string;
  currentDate: string;
  onChange: (date: string) => void;
}) {
  const totalDays = Math.max(daysBetween(from, to), 1);
  const currentDay = Math.min(Math.max(daysBetween(from, currentDate), 0), totalDays);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const nextDay = daysBetween(from, currentDate) + 1;
      if (nextDay > totalDays) {
        setPlaying(false);
        return;
      }
      onChange(addDays(from, nextDay));
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [playing, currentDate, from, totalDays, onChange]);

  return (
    <div className="flex items-center gap-3">
      <Button variant="outline" size="icon" onClick={() => setPlaying((p) => !p)} title={playing ? "Пауза" : "Играть"}>
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => {
          setPlaying(false);
          onChange(from);
        }}
        title="Сначала"
      >
        <RotateCcw className="h-4 w-4" />
      </Button>
      <input
        type="range"
        min={0}
        max={totalDays}
        value={currentDay}
        onChange={(e) => {
          setPlaying(false);
          onChange(addDays(from, Number(e.target.value)));
        }}
        className="h-1.5 flex-1 cursor-pointer accent-text"
      />
      <span className="tabular w-20 shrink-0 text-right text-sm text-text-muted">{formatDate(currentDate)}</span>
    </div>
  );
}
