import { DemoBanner } from "@/components/DemoBanner";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLiveState, useObjectDetail } from "@/api/hooks";
import { DEMO_OBJECT_ID } from "@/api/demo-data";
import { formatDateTime } from "@/lib/utils";

import { FrameCanvas } from "./FrameCanvas";
import { NowPanel } from "./NowPanel";

export function LivePage() {
  const objectId = DEMO_OBJECT_ID;
  const detail = useObjectDetail(objectId);
  const live = useLiveState(objectId, { refetchIntervalMs: 20_000 });

  const isDemo = Boolean(detail.data?.isDemo || live.data?.isDemo);
  const cameras = detail.data?.data.cameras ?? [];
  const liveCameras = live.data?.data.cameras ?? [];

  if (detail.isLoading || live.isLoading) {
    return <div className="text-sm text-text-muted">Загрузка…</div>;
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Площадка сейчас</h1>
        {live.data && <ConfidenceMeter value={liveCameras[0]?.quality.score ?? 0} />}
      </div>
      <DemoBanner isDemo={isDemo} />

      {cameras.map((camera) => {
        const frame = liveCameras.find((c) => c.camera_id === camera.camera_id);
        return (
          <div key={camera.camera_id} className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle>{camera.title || camera.camera_id}</CardTitle>
                {frame && <span className="text-xs text-text-muted">{formatDateTime(frame.ts)}</span>}
              </CardHeader>
              <CardContent>
                <FrameCanvas zones={camera.zones ?? []} objects={frame?.objects ?? []} />
                {frame?.quality.night && (
                  <p className="mt-2 text-xs text-status-gray">Ночной кадр — низкая освещённость.</p>
                )}
              </CardContent>
            </Card>
            <NowPanel objects={frame?.objects ?? []} />
          </div>
        );
      })}

      {cameras.length === 0 && (
        <p className="text-sm text-text-muted">У объекта пока нет подключённых камер.</p>
      )}
    </div>
  );
}
