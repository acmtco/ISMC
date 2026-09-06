import { CheckCircle2, FileSpreadsheet, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useImportSchedule } from "@/api/hooks";
import type { ScheduleImportResult } from "@/api/types";

export function ScheduleImportStep({
  objectId,
  onImported,
}: {
  objectId: string;
  onImported: (result: ScheduleImportResult) => void;
}) {
  const importSchedule = useImportSchedule(objectId);
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState<ScheduleImportResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    if (!/\.(xlsx|xml)$/i.test(file.name)) return;
    try {
      const imported = await importSchedule.mutateAsync(file);
      setResult(imported);
      onImported(imported);
    } catch {
      // ошибка отражена ниже через importSchedule.isError
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        Перетащите файл графика (XLSX или MS Project XML) — колонки определятся автоматически
        (нечёткое сопоставление заголовков).
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files[0];
          if (file) void handleFile(file);
        }}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded border-2 border-dashed px-6 py-12 text-center transition-colors",
          dragOver ? "border-text/50 bg-surface-hover" : "border-border bg-surface",
        )}
      >
        <UploadCloud className="h-8 w-8 text-text-muted" />
        <div className="text-sm">Перетащите файл сюда или нажмите, чтобы выбрать</div>
        <div className="text-xs text-text-muted">.xlsx, .xml</div>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xml"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
      </div>

      {importSchedule.isPending && <p className="text-sm text-text-muted">Импортирую…</p>}
      {importSchedule.isError && (
        <p className="text-sm text-status-red">
          Не удалось импортировать. Бэкенд недоступен или файл не распознан.
        </p>
      )}

      {result && (
        <Card>
          <CardContent className="flex items-center gap-3 pt-4">
            <CheckCircle2 className="h-5 w-5 text-status-green" />
            <div>
              <div className="text-sm font-medium">Импортировано работ: {result.imported_count}</div>
              <div className="mt-1 flex flex-wrap gap-2">
                {result.works.slice(0, 6).map((w) => (
                  <span
                    key={w.work_id}
                    className="flex items-center gap-1 rounded bg-surface-hover px-2 py-0.5 text-xs text-text-muted"
                  >
                    <FileSpreadsheet className="h-3 w-3" />
                    {w.name}
                  </span>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
