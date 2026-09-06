import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { DeviationsPage } from "@/routes/deviations/DeviationsPage";
import { EconomicsPage } from "@/routes/economics/EconomicsPage";
import { GanttPage } from "@/routes/gantt/GanttPage";
import { LivePage } from "@/routes/live/LivePage";
import { SetupPage } from "@/routes/setup/SetupPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/live" replace />} />
        <Route path="/setup" element={<SetupPage />} />
        <Route path="/live" element={<LivePage />} />
        <Route path="/gantt" element={<GanttPage />} />
        <Route path="/deviations" element={<DeviationsPage />} />
        <Route path="/deviations/:deviationId" element={<DeviationsPage />} />
        <Route path="/economics" element={<EconomicsPage />} />
        <Route path="*" element={<Navigate to="/live" replace />} />
      </Routes>
    </AppShell>
  );
}
