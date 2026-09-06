import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { DemoBanner } from "@/components/DemoBanner";
import { useDeviations } from "@/api/hooks";
import { DEMO_OBJECT_ID } from "@/api/demo-data";
import type { DeviationType, Severity } from "@/api/types";

import { DeviationCard } from "./DeviationCard";
import { DeviationList } from "./DeviationList";

export function DeviationsPage() {
  const objectId = DEMO_OBJECT_ID;
  const { deviationId } = useParams();
  const navigate = useNavigate();

  const [typeFilter, setTypeFilter] = useState<DeviationType | "all">("all");
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");

  const deviations = useDeviations(objectId);

  const filtered = useMemo(() => {
    const all = deviations.data?.data ?? [];
    return all.filter(
      (d) =>
        (typeFilter === "all" || d.type === typeFilter) &&
        (severityFilter === "all" || d.severity === severityFilter),
    );
  }, [deviations.data, typeFilter, severityFilter]);

  const selected = filtered.find((d) => d.deviation_id === deviationId) ?? filtered[0];

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Лента отклонений</h1>
      <DemoBanner isDemo={Boolean(deviations.data?.isDemo)} />

      {deviations.isLoading && <div className="text-sm text-text-muted">Загрузка…</div>}

      {!deviations.isLoading && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
          <DeviationList
            deviations={filtered}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            severityFilter={severityFilter}
            onSeverityFilterChange={setSeverityFilter}
            selectedId={selected?.deviation_id}
            onSelect={(id) => navigate(`/deviations/${id}`)}
          />
          {selected ? (
            <DeviationCard deviation={selected} />
          ) : (
            <p className="text-sm text-text-muted">Выберите отклонение из списка.</p>
          )}
        </div>
      )}
    </div>
  );
}
