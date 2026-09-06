import { WifiOff } from "lucide-react";

export function DemoBanner({ isDemo }: { isDemo: boolean }) {
  if (!isDemo) return null;
  return (
    <div className="mb-4 flex items-center gap-2 rounded border border-status-yellow/30 bg-status-yellow/10 px-3 py-2 text-xs text-status-yellow">
      <WifiOff className="h-3.5 w-3.5" />
      Бэкенд недоступен — показаны демонстрационные данные.
    </div>
  );
}
