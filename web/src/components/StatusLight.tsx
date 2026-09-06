import { Badge } from "@/components/ui/badge";
import { statusLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

const DOT_COLOR: Record<string, string> = {
  green: "bg-status-green",
  yellow: "bg-status-yellow",
  red: "bg-status-red",
};

const BADGE_VARIANT: Record<string, "green" | "yellow" | "red" | "gray"> = {
  green: "green",
  yellow: "yellow",
  red: "red",
};

export function StatusDot({ status }: { status: string }) {
  return <span className={cn("inline-block h-2 w-2 rounded-full", DOT_COLOR[status] ?? "bg-status-gray")} />;
}

export function StatusLight({ status }: { status: string }) {
  return (
    <Badge variant={BADGE_VARIANT[status] ?? "gray"}>
      <StatusDot status={status} />
      {statusLabel(status)}
    </Badge>
  );
}
