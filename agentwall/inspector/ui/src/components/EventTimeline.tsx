import type { ToolEvent } from "../api/client";

const DECISION_STYLES: Record<string, string> = {
  allow: "bg-green-900 text-green-300 border border-green-700",
  warn: "bg-yellow-900 text-yellow-300 border border-yellow-700",
  block: "bg-red-900 text-red-300 border border-red-700",
};

interface Props {
  events: ToolEvent[];
}

export function EventTimeline({ events }: Props) {
  if (events.length === 0) {
    return <p className="text-gray-400 text-sm p-6">No tool events for this session.</p>;
  }

  return (
    <ul className="divide-y divide-gray-800">
      {events.map((e) => {
        const decision = e.evaluation?.decision ?? "pending";
        const style = DECISION_STYLES[decision] ?? "bg-gray-700 text-gray-300";
        return (
          <li key={e.id} className="px-6 py-4">
            <div className="flex items-start gap-3">
              <span className={`text-xs font-mono px-2 py-0.5 rounded uppercase ${style}`}>
                {decision}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white font-mono">{e.tool_name}</p>
                {e.evaluation && (
                  <p className="text-xs text-gray-400 mt-0.5">
                    risk={e.evaluation.risk_score} — {e.evaluation.reason}
                    {e.evaluation.llm_used && (
                      <span className="ml-2 text-purple-400">LLM</span>
                    )}
                  </p>
                )}
                <details className="mt-1">
                  <summary className="text-xs text-gray-500 cursor-pointer">arguments</summary>
                  <pre className="text-xs text-gray-400 mt-1 bg-gray-900 p-2 rounded overflow-x-auto">
                    {JSON.stringify(e.arguments, null, 2)}
                  </pre>
                </details>
              </div>
              <span className="text-xs text-gray-600 whitespace-nowrap">
                {new Date(e.timestamp * 1000).toLocaleTimeString()}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
