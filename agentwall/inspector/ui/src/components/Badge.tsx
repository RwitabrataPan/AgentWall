import type { DecisionType } from "../api/client";

const STYLES: Record<string, string> = {
  allow: "bg-green-950 text-green-400 border border-green-800",
  warn: "bg-yellow-950 text-yellow-400 border border-yellow-800",
  block: "bg-red-950 text-red-400 border border-red-800",
};

export function DecisionBadge({ decision }: { decision: DecisionType | string }) {
  return (
    <span className={`text-xs font-mono px-2 py-0.5 rounded uppercase ${STYLES[decision] ?? "bg-gray-800 text-gray-400"}`}>
      {decision}
    </span>
  );
}

export function RiskBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = score >= 70 ? "bg-red-500" : score >= 30 ? "bg-yellow-500" : "bg-green-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 tabular-nums">{score.toFixed(0)}</span>
    </div>
  );
}
