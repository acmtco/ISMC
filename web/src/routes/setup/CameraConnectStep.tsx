import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { CameraOut } from "@/api/types";

export interface CameraDraft {
  camera_id: string;
  title: string;
  source_kind: string;
  source_uri: string;
}

/** Создание камеры через API не предусмотрено контрактом (docs/02 §7 —
 * камеры описываются в `objects.json`); реально персистентный шаг мастера —
 * следующий (разметка зон, `POST /api/cameras/{id}/zones`) для уже
 * существующей камеры. Здесь — выбор из подключённых или локальный черновик
 * параметров подключения для передачи оператору. */
export function CameraConnectStep({
  existingCameras,
  draft,
  onChange,
}: {
  existingCameras: CameraOut[];
  draft: CameraDraft;
  onChange: (draft: CameraDraft) => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      {existingCameras.length > 0 && (
        <Card>
          <CardContent className="pt-4">
            <div className="mb-2 text-sm font-medium">Уже подключённые камеры</div>
            <div className="flex flex-col gap-2">
              {existingCameras.map((cam) => (
                <button
                  key={cam.camera_id}
                  onClick={() =>
                    onChange({
                      camera_id: cam.camera_id,
                      title: cam.title,
                      source_kind: cam.source_kind,
                      source_uri: cam.source_uri,
                    })
                  }
                  className="flex items-center justify-between rounded border border-border px-3 py-2 text-left text-sm hover:bg-surface-hover"
                >
                  <span>{cam.title || cam.camera_id}</span>
                  <span className="text-xs text-text-muted">{cam.source_kind}</span>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <p className="text-sm text-text-muted">
        Или укажите параметры подключения новой камеры (заявка передаётся оператору площадки —
        разметка зон на следующем шаге сохраняется для существующей камеры).
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Идентификатор камеры</Label>
          <Input
            value={draft.camera_id}
            onChange={(e) => onChange({ ...draft, camera_id: e.target.value })}
            placeholder="CAM-02"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Название ракурса</Label>
          <Input
            value={draft.title}
            onChange={(e) => onChange({ ...draft, title: e.target.value })}
            placeholder="Южный ракурс"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Тип источника</Label>
          <Select value={draft.source_kind} onValueChange={(v) => onChange({ ...draft, source_kind: v })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="rtsp">RTSP</SelectItem>
              <SelectItem value="hls">HLS</SelectItem>
              <SelectItem value="folder">Папка с кадрами</SelectItem>
              <SelectItem value="replay">Replay (архив)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Адрес источника</Label>
          <Input
            value={draft.source_uri}
            onChange={(e) => onChange({ ...draft, source_uri: e.target.value })}
            placeholder="rtsp://192.168.1.10/stream"
          />
        </div>
      </div>
    </div>
  );
}
