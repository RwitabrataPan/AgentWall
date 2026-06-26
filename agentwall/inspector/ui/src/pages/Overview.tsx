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

  const {
    project_name,
    active_sessions,
    total_sessions,
    active_executions,
    total_executions,
    total_events,
    threat_count,
    risk_distribution,
    avg_risk,
    current_provider,
    current_model,
    top_detectors,
    top_policies,
  } = data;

  const total_evals = risk_distribution.allow + risk_distribution.warn + risk_distribution.block;

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* Project banner */}
      {project_name && (
        <div className="flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-lg px-4 py-3">
          <span className="text-xs text-gray-500">Current Project</span>
          <span className="text-sm font-semibold text-blue-400">{project_name}</span>
          {current_provider && (
            <>
              <span className="text-gray-700 ml-auto">Provider</span>
              <span className="text-xs text-gray-400">{current_provider}</span>
              {current_model && <span className="text-xs text-gray-500">{current_model}</span>}
            </>
          )}
        </div>
      )}

      {/* Execution stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Active Executions" value={active_executions} accent="blue" />
        <StatCard label="Total Executions" value={total_executions} accent="gray" />
        <StatCard label="Tool Calls" value={total_events} accent="gray" />
        <StatCard label="Threats" value={threat_count} accent={threat_count > 0 ? "red" : "gray"} />
      </div>

      {/* Session stats (secondary) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Active Sessions" value={active_sessions} accent="gray" size="sm" />
        <StatCard label="Total Sessions" value={total_sessions} accent="gray" size="sm" />
        {avg_risk != null && (
          <StatCard label="Avg Risk Score" value={avg_risk} accent={avg_risk > 50 ? "red" : "gray"} size="sm" />
        )}
        <StatCard label="Allowed" value={risk_distribution.allow} accent="gray" size="sm" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Risk distribution */}
        <div className="lg:col-span-2 bg-gray-900 rounded-lg border border-gray-800 p-5">
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

        {/* Top detectors */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-5">
          <h2 className="text-sm font-medium text-gray-300 mb-4">Top Detectors</h2>
          {top_detectors.length === 0 ? (
            <p className="text-gray-500 text-sm">No hits yet.</p>
          ) : (
            <div className="space-y-2">
              {top_detectors.map((d) => (
                <div key={d.name} className="flex items-center gap-2">
                  <span className="text-xs text-orange-400 truncate flex-1">{d.name}</span>
                  <span className="text-xs text-gray-500 tabular-nums">{d.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Top policies */}
      {top_policies.length > 0 && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-5">
          <h2 className="text-sm font-medium text-gray-300 mb-4">Top Policies Matched</h2>
          <div className="space-y-2">
            {top_policies.map((p) => (
              <div key={p.name} className="flex items-center gap-2">
                <span className="text-xs text-yellow-400 truncate flex-1">{p.name}</span>
                <span className="text-xs text-gray-500 tabular-nums">{p.count} match{p.count !== 1 ? "es" : ""}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
  size = "lg",
}: {
  label: string;
  value: number;
  accent: string;
  size?: "lg" | "sm";
}) {
  const colors: Record<string, string> = {
    blue: "text-blue-400",
    red: "text-red-400",
    gray: "text-white",
  };
  const numClass = size === "lg" ? "text-3xl font-bold" : "text-xl font-semibold";
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`${numClass} tabular-nums ${colors[accent] ?? "text-white"}`}>{value}</p>
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
