import { useEffect, useState } from "react";
import { api, connectEventStream } from "./api/client";
import { NavBar, type Page } from "./components/NavBar";
import { OverviewPage } from "./pages/Overview";
import { SessionsPage } from "./pages/Sessions";
import { TimelinePage } from "./pages/Timeline";
import { ProvidersPage } from "./pages/Providers";
import { PoliciesPage } from "./pages/Policies";

export default function App() {
  const [version, setVersion] = useState("…");
  const [page, setPage] = useState<Page>("overview");
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    api.health().then((h) => setVersion(h.version)).catch(() => {});
    const disconnect = connectEventStream(() => setRefreshTick((t) => t + 1));
    return disconnect;
  }, []);

  const goToTimeline = (sessionId: string) => {
    setSelectedSession(sessionId);
    setPage("timeline");
  };

  const goBack = () => setPage("sessions");

  return (
    <div className="h-screen bg-gray-950 text-white flex flex-col overflow-hidden">
      <NavBar page={page} onNav={setPage} version={version} />
      <div className="flex-1 overflow-hidden">
        {page === "overview" && <div className="h-full overflow-y-auto"><OverviewPage refreshTick={refreshTick} /></div>}
        {(page === "sessions" || (page === "timeline" && !selectedSession)) && (
          <SessionsPage onSelect={goToTimeline} refreshTick={refreshTick} />
        )}
        {page === "timeline" && selectedSession && (
          <TimelinePage sessionId={selectedSession} onBack={goBack} refreshTick={refreshTick} />
        )}
        {page === "providers" && <div className="h-full overflow-hidden flex flex-col"><ProvidersPage /></div>}
        {page === "policies"  && <div className="h-full overflow-hidden flex flex-col"><PoliciesPage /></div>}
      </div>
    </div>
  );
}
