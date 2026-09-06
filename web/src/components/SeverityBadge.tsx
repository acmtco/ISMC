import { Badge } from "@/components/ui/badge";
import { severityLabel } from "@/lib/labels";

const VARIANT: Record<string, "red" | "yellow" | "gray"> = {
  high: "red",
  medium: "yellow",
  low: "gray",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return <Badge variant={VARIANT[severity] ?? "gray"}>{severityLabel(severity)}</Badge>;
}
