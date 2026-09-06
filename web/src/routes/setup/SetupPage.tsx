import { Check } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useObjectDetail } from "@/api/hooks";
import { DEMO_OBJECT_ID } from "@/api/demo-data";

import { CameraConnectStep, type CameraDraft } from "./CameraConnectStep";
import { ScheduleImportStep } from "./ScheduleImportStep";
import { ZoneDrawStep } from "./ZoneDrawStep";

const STEPS = ["Импорт графика", "Подключение камеры", "Разметка зон"];

export function SetupPage() {
  const objectId = DEMO_OBJECT_ID;
  const detail = useObjectDetail(objectId);
  const [step, setStep] = useState(0);
  const [cameraDraft, setCameraDraft] = useState<CameraDraft>({
    camera_id: detail.data?.data.cameras?.[0]?.camera_id ?? "",
    title: "",
    source_kind: "replay",
    source_uri: "",
  });

  const cameras = detail.data?.data.cameras ?? [];

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Настройка объекта</h1>

      <div className="mb-6 flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <button
              onClick={() => setStep(i)}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium",
                i === step
                  ? "border-text bg-text text-bg"
                  : i < step
                    ? "border-status-green/50 bg-status-green/15 text-status-green"
                    : "border-border text-text-muted",
              )}
            >
              {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </button>
            <span className={cn("text-sm", i === step ? "text-text" : "text-text-muted")}>{label}</span>
            {i < STEPS.length - 1 && <div className="mx-2 h-px w-8 bg-border" />}
          </div>
        ))}
      </div>

      <Card>
        <CardContent className="pt-5">
          {step === 0 && <ScheduleImportStep objectId={objectId} onImported={() => setStep(1)} />}
          {step === 1 && (
            <CameraConnectStep existingCameras={cameras} draft={cameraDraft} onChange={setCameraDraft} />
          )}
          {step === 2 && <ZoneDrawStep cameraId={cameraDraft.camera_id || "CAM-01"} />}

          <div className="mt-6 flex justify-between border-t border-border pt-4">
            <Button variant="outline" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
              Назад
            </Button>
            {step < STEPS.length - 1 && (
              <Button onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}>Далее</Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
