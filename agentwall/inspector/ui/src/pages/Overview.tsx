import { useEffect, useState } from "react";
import { api, type Overview } from "../api/client";

interface Props { refreshTick: number }

export function OverviewPage({ refreshTick }: Props) {
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getOverview().then(setData).catch((e) => setErr(String(e)));
  }, [refreshTick]);

  if (err) return <div className="p-6 text-red-400 text-sm">{err}</div>;
  if (!data) return <div className="p-6 text-gray-500 text-sm">Loading…</div>;

  const { active_sessions, total_sessions, total_events, threat_count, risk_distribution } = data;
  const total_evals = risk_distribution.allow + risk_distribution.warn + risk_distribution.block;

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <h1 className="text-lg font-semibold text-white">Overview</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Active Sessions" value={active_sessions} accent="blue" />
        <StatCard label="Total Sessions" value={total_sessions} accent="gray" />
        <StatCard label="Security Events" value={total_events} accent="gray" />
        <StatCard label="Threats" value={threat_count} accent={threat_count > 0 ? "red" : "gray"} />
      </div>

      {/* Risk distribution */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-5">
        <h2 className="text-sm font-medium text-gray-300 mb-4">Risk Distribution</h2>
        {total_evals === 0 ? (
          <p className="text-gray-500 text-sm">No evaluations yet.</p>
        ) : (
          <div className="space-y-3">
            <DistRow label="Allow" count={risk_distribution.allow} total={total_evals} color="bg-green-500" />
            <DistRow label="Warn"  count={risk_distribution.warn}  total={total_evals} color="bg-yellow-500" />
            <DistRow label="Block" count={risk_distribution.block} total={total_evals} color="bg-red-500" />
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, accent }: { label: string; value: number; accent: string }) {
  const colors: Record<string, string> = {
    blue: "text-blue-400",
    red: "text-red-400",
    gray: "text-white",
  };
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-3xl font-bold tabular-nums ${colors[accent] ?? "text-white"}`}>{value}</p>
    </div>
  );
}

function DistRow({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400 w-10">{label}</span>
      <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 tabular-nums w-16 text-right">
        {count} ({pct.toFixed(0)}%)
      </span>
    </div>
  );
}
