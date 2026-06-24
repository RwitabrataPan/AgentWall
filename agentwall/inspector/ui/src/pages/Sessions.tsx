import { useEffect, useState } from "react";
import { api, type Session } from "../api/client";
import { DecisionBadge, RiskBar } from "../components/Badge";

interface Props {
  onSelect: (sessionId: string) => void;
  refreshTick: number;
}

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

function duration(s: Session): string {
  const end = s.ended_at ?? Date.now() / 1000;
  const secs = Math.round(end - s.created_at);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  return `${(secs / 3600).toFixed(1)}h`;
}

export function SessionsPage({ onSelect, refreshTick }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getSessions().then(setSessions).catch((e) => setErr(String(e)));
  }, [refreshTick]);

  const exportAll = () => { window.open(api.exportUrl("json"), "_blank"); };
  const exportCsv = () => { window.open(api.exportUrl("csv"), "_blank"); };

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-3 border-b border-gray-800 flex items-center justify-between shrink-0">
        <h1 className="text-sm font-semibold text-white">Sessions</h1>
        <div className="flex gap-2">
          <ExportBtn label="JSON" onClick={exportAll} />
          <ExportBtn label="CSV"  onClick={exportCsv} />
        </div>
      </div>

      {err && <p className="px-6 py-3 text-red-400 text-sm">{err}</p>}

      {sessions.length === 0 && !err ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          No sessions. Run an agent with AgentWall protection.
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 border-b border-gray-800">
                <th className="px-4 py-2 text-left font-medium">Goal</th>
                <th className="px-4 py-2 text-left font-medium">Session ID</th>
                <th className="px-4 py-2 text-left font-medium">Started</th>
                <th className="px-4 py-2 text-left font-medium">Duration</th>
                <th className="px-4 py-2 text-left font-medium">Events</th>
                <th className="px-4 py-2 text-left font-medium">Max Risk</th>
                <th className="px-4 py-2 text-left font-medium">Threats</th>
                <th className="px-4 py-2 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => onSelect(s.id)}
                  className="border-b border-gray-800 hover:bg-gray-800 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 text-white max-w-xs truncate">{s.user_goal}</td>
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs">{s.id.slice(0, 8)}…</td>
                  <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">{fmt(s.created_at)}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{duration(s)}</td>
                  <td className="px-4 py-3 text-gray-300 tabular-nums">{s.event_count}</td>
                  <td className="px-4 py-3">
                    {s.max_risk != null ? <RiskBar score={s.max_risk} /> : <span className="text-gray-600 text-xs">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {s.threat_count > 0
                      ? <span className="text-red-400 text-xs font-medium">{s.threat_count}</span>
                      : <span className="text-gray-600 text-xs">0</span>}
                  </td>
                  <td className="px-4 py-3">
                    {s.ended_at
                      ? <span className="text-xs text-gray-500">ended</span>
                      : <span className="text-xs text-green-400">active</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ExportBtn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded border border-gray-700 transition-colors"
    >
      Export {label}
    </button>
  );
}
