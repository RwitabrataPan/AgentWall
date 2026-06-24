import { useEffect, useState } from "react";
import { api, type Session, type ToolEvent } from "../api/client";
import { DecisionBadge, RiskBar } from "../components/Badge";

interface Props {
  sessionId: string;
  onBack: () => void;
  refreshTick: number;
}

export function TimelinePage({ sessionId, onBack, refreshTick }: Props) {
  const [session, setSession] = useState<Session | null>(null);
  const [events, setEvents] = useState<ToolEvent[]>([]);
  const [selected, setSelected] = useState<ToolEvent | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getSession(sessionId).then(setSession).catch(() => {});
    api.getEvents(sessionId)
      .then((evs) => {
        setEvents(evs);
        setSelected((prev) => prev ? evs.find((e) => e.id === prev.id) ?? evs[evs.length - 1] ?? null : null);
      })
      .catch((e) => setErr(String(e)));
  }, [sessionId, refreshTick]);

  const exportJson = () => { window.open(api.exportUrl("json", sessionId), "_blank"); };
  const exportCsv  = () => { window.open(api.exportUrl("csv",  sessionId), "_blank"); };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-3 shrink-0">
        <button
          onClick={onBack}
          className="text-gray-400 hover:text-white text-sm transition-colors"
        >
          ← Sessions
        </button>
        {session && (
          <>
            <span className="text-gray-700">|</span>
            <span className="text-sm font-medium text-white truncate max-w-md">{session.user_goal}</span>
            <span className="text-xs text-gray-600 font-mono ml-1">{session.id.slice(0, 8)}…</span>
          </>
        )}
        <div className="ml-auto flex gap-2">
          <ExportBtn label="JSON" onClick={exportJson} />
          <ExportBtn label="CSV"  onClick={exportCsv} />
        </div>
      </div>

      {err && <p className="px-4 py-2 text-red-400 text-sm">{err}</p>}

      <div className="flex flex-1 overflow-hidden">
        {/* Event list */}
        <div className="w-80 border-r border-gray-800 overflow-y-auto shrink-0">
          {events.length === 0 ? (
            <p className="p-4 text-gray-500 text-sm">No tool calls yet.</p>
          ) : (
            <ul className="divide-y divide-gray-800">
              {events.map((e) => {
                const decision = e.evaluation?.decision ?? "pending";
                const active = selected?.id === e.id;
                return (
                  <li
                    key={e.id}
                    onClick={() => setSelected(e)}
                    className={`px-4 py-3 cursor-pointer transition-colors ${
                      active ? "bg-gray-800 border-l-2 border-blue-500" : "hover:bg-gray-850"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <DecisionBadge decision={decision} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-mono text-white truncate">{e.tool_name}</p>
                        {e.target && (
                          <p className="text-xs text-gray-500 truncate mt-0.5">{e.target}</p>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-gray-600 mt-1">
                      {new Date(e.timestamp * 1000).toLocaleTimeString()}
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Evaluation details panel */}
        <div className="flex-1 overflow-y-auto p-6">
          {selected ? (
            <EvalDetails event={selected} />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-600 text-sm">
              Select a tool call to view evaluation details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EvalDetails({ event }: { event: ToolEvent }) {
  const ev = event.evaluation;
  return (
    <div className="space-y-5 max-w-2xl">
      {/* Tool call header */}
      <div>
        <h2 className="text-base font-mono font-semibold text-white">{event.tool_name}</h2>
        <div className="flex flex-wrap gap-3 mt-2 text-xs text-gray-500">
          {event.tool_type && <Chip label="type" value={event.tool_type} />}
          {event.action     && <Chip label="action" value={event.action} />}
          {event.resource_category && <Chip label="category" value={event.resource_category} />}
        </div>
      </div>

      {/* Target */}
      {event.target && (
        <Field label="Target">
          <code className="text-sm text-blue-300 break-all">{event.target}</code>
        </Field>
      )}

      {/* Arguments */}
      <Field label="Arguments">
        <pre className="text-xs text-gray-400 bg-gray-900 p-3 rounded overflow-x-auto border border-gray-800">
          {JSON.stringify(event.arguments, null, 2)}
        </pre>
      </Field>

      {/* Evaluation */}
      {ev ? (
        <>
          <div className="border-t border-gray-800 pt-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Evaluation
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Decision">
                <DecisionBadge decision={ev.decision} />
              </Field>
              <Field label="Risk Score">
                <RiskBar score={ev.risk_score} />
              </Field>
              {ev.alignment_score != null && (
                <Field label="Alignment Score">
                  <RiskBar score={ev.alignment_score} />
                </Field>
              )}
              <Field label="LLM Used">
                <span className={`text-xs ${ev.llm_used ? "text-purple-400" : "text-gray-500"}`}>
                  {ev.llm_used ? "Yes" : "No"}
                </span>
              </Field>
            </div>
          </div>

          <Field label="Reason">
            <p className="text-sm text-gray-300">{ev.reason}</p>
          </Field>

          {ev.detector_hits && ev.detector_hits.length > 0 && (
            <Field label="Triggered Detectors">
              <div className="flex flex-wrap gap-2">
                {ev.detector_hits.map((d) => (
                  <span key={d} className="text-xs bg-orange-950 text-orange-400 border border-orange-800 px-2 py-0.5 rounded">
                    {d}
                  </span>
                ))}
              </div>
            </Field>
          )}

          {ev.policy_matched && (
            <Field label="Policy Matched">
              <span className="text-xs text-yellow-400 font-mono">{ev.policy_matched}</span>
            </Field>
          )}
        </>
      ) : (
        <p className="text-sm text-gray-500">No evaluation recorded.</p>
      )}

      <p className="text-xs text-gray-600">
        {new Date(event.timestamp * 1000).toLocaleString()}
      </p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-medium text-gray-500 mb-1">{label}</p>
      {children}
    </div>
  );
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <span className="bg-gray-800 text-gray-400 px-2 py-0.5 rounded">
      <span className="text-gray-600">{label}:</span> {value}
    </span>
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
