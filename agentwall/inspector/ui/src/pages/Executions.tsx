import { useEffect, useState } from "react";
import { api, type Execution, type ToolEvent } from "../api/client";
import { DecisionBadge, RiskBar } from "../components/Badge";

interface Props {
  refreshTick: number;
}

function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

function fmtDuration(ex: Execution): string {
  const end = ex.finished_at ?? Date.now() / 1000;
  const secs = Math.round(end - ex.started_at);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  return `${(secs / 3600).toFixed(1)}h`;
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "running"
      ? "text-green-400 bg-green-950 border-green-800"
      : status === "completed"
      ? "text-gray-400 bg-gray-800 border-gray-700"
      : "text-red-400 bg-red-950 border-red-800";
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${cls}`}>{status}</span>
  );
}

function ExecNumber({ n }: { n: number }) {
  return <span className="text-xs font-mono text-gray-500">#{n}</span>;
}

interface DetailProps {
  execution: Execution;
}

function ExecutionDetails({ execution }: DetailProps) {
  const [events, setEvents] = useState<ToolEvent[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(true);
  const [secOpen, setSecOpen] = useState(true);

  useEffect(() => {
    if (!loaded) {
      api.getExecutionEvents(execution.id).then((evs) => {
        setEvents(evs);
        setLoaded(true);
      }).catch(() => setLoaded(true));
    }
  }, [execution.id, loaded]);

  const evals = events.map((e) => e.evaluation).filter(Boolean) as NonNullable<ToolEvent["evaluation"]>[];
  const detectorHits = [...new Set(evals.flatMap((e) => e.detector_hits ?? []))];
  const policiesMatched = [...new Set(evals.map((e) => e.policy_matched).filter(Boolean))] as string[];
  const llmUsed = evals.some((e) => e.llm_used);

  return (
    <div className="px-6 pb-6 space-y-5">
      {/* Summary grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-2">
        <InfoCell label="Goal" value={execution.goal} />
        {execution.prompt && execution.prompt !== execution.goal && (
          <InfoCell label="Prompt" value={execution.prompt} />
        )}
        {execution.framework && <InfoCell label="Framework" value={execution.framework} />}
        {execution.model && <InfoCell label="Model" value={execution.model} />}
        <InfoCell label="Started" value={fmtTime(execution.started_at)} />
        {execution.finished_at && <InfoCell label="Finished" value={fmtTime(execution.finished_at)} />}
        <InfoCell label="Duration" value={fmtDuration(execution)} />
        <InfoCell label="Status" value={<StatusBadge status={execution.status} />} />
        {execution.overall_decision && (
          <InfoCell label="Decision" value={<DecisionBadge decision={execution.overall_decision} />} />
        )}
        {execution.max_risk != null && (
          <InfoCell label="Max Risk" value={<RiskBar score={execution.max_risk} />} />
        )}
        <InfoCell label="Events" value={String(execution.event_count)} />
        <InfoCell
          label="Threats"
          value={
            execution.threat_count > 0 ? (
              <span className="text-red-400 font-medium">{execution.threat_count}</span>
            ) : (
              <span className="text-gray-500">0</span>
            )
          }
        />
      </div>

      {/* Tool Calls */}
      <section className="border border-gray-800 rounded-lg overflow-hidden">
        <button
          onClick={() => setToolsOpen((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-900 hover:bg-gray-850 text-left"
        >
          <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
            Tool Calls ({events.length})
          </span>
          <span className="text-gray-500 text-sm">{toolsOpen ? "▼" : "▶"}</span>
        </button>
        {toolsOpen && (
          <div className="divide-y divide-gray-800">
            {!loaded ? (
              <p className="px-4 py-3 text-sm text-gray-500">Loading…</p>
            ) : events.length === 0 ? (
              <p className="px-4 py-3 text-sm text-gray-500">
                No tool calls were executed during this execution.
              </p>
            ) : (
              events.map((ev) => (
                <div key={ev.id} className="px-4 py-2.5 flex items-center gap-3">
                  {ev.evaluation ? (
                    <DecisionBadge decision={ev.evaluation.decision} />
                  ) : (
                    <span className="text-xs text-gray-600 w-12">—</span>
                  )}
                  <span className="font-mono text-xs text-white">{ev.tool_name}</span>
                  {ev.target && (
                    <span className="text-xs text-gray-500 truncate max-w-xs">{ev.target}</span>
                  )}
                  {ev.evaluation && (
                    <span className="ml-auto text-xs text-gray-600">
                      risk {ev.evaluation.risk_score.toFixed(0)}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </section>

      {/* Security Evaluation */}
      <section className="border border-gray-800 rounded-lg overflow-hidden">
        <button
          onClick={() => setSecOpen((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-900 hover:bg-gray-850 text-left"
        >
          <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
            Security Evaluation
          </span>
          <span className="text-gray-500 text-sm">{secOpen ? "▼" : "▶"}</span>
        </button>
        {secOpen && (
          <div className="px-4 py-3 space-y-2">
            <EvalRow
              label="Sensitive Resource Detector"
              hit={detectorHits.some((d) => d.toLowerCase().includes("sensitive"))}
              hitDetail={detectorHits.filter((d) => d.toLowerCase().includes("sensitive")).join(", ")}
            />
            <EvalRow
              label="Goal Drift Detector"
              hit={detectorHits.some((d) => d.toLowerCase().includes("drift"))}
              hitDetail={detectorHits.filter((d) => d.toLowerCase().includes("drift")).join(", ")}
            />
            <EvalRow
              label="Data Exfiltration Detector"
              hit={detectorHits.some((d) => d.toLowerCase().includes("exfil"))}
              hitDetail={detectorHits.filter((d) => d.toLowerCase().includes("exfil")).join(", ")}
            />
            <EvalRow
              label="Scope Expansion Detector"
              hit={detectorHits.some((d) => d.toLowerCase().includes("scope"))}
              hitDetail={detectorHits.filter((d) => d.toLowerCase().includes("scope")).join(", ")}
            />
            <EvalRow
              label="Rule Engine"
              hit={false}
            />
            <EvalRow
              label="Policy Engine"
              hit={policiesMatched.length > 0}
              hitDetail={policiesMatched.join(", ")}
            />
            <div className="flex items-center gap-3 py-1">
              <span className="text-xs text-gray-400 w-52">LLM Evaluation</span>
              <span className={`text-xs ${llmUsed ? "text-purple-400" : "text-gray-600"}`}>
                {llmUsed ? "Used" : "Not Used"}
              </span>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function EvalRow({
  label,
  hit,
  hitDetail,
}: {
  label: string;
  hit: boolean;
  hitDetail?: string;
}) {
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="text-xs text-gray-400 w-52">{label}</span>
      {hit ? (
        <span className="text-xs text-orange-400">
          HIT{hitDetail ? `: ${hitDetail}` : ""}
        </span>
      ) : (
        <span className="text-xs text-green-600">PASS</span>
      )}
    </div>
  );
}

function InfoCell({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500 mb-0.5">{label}</p>
      {typeof value === "string" ? (
        <p className="text-xs text-white truncate" title={value}>
          {value}
        </p>
      ) : (
        value
      )}
    </div>
  );
}

interface CardProps {
  execution: Execution;
  index: number;
  isLatest: boolean;
}

function ExecutionCard({ execution, index, isLatest }: CardProps) {
  const [open, setOpen] = useState(isLatest);

  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden bg-gray-950">
      {/* Card header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-gray-900 transition-colors text-left"
      >
        <span className="text-gray-500 text-sm w-4">{open ? "▼" : "▶"}</span>
        <ExecNumber n={index} />
        <span className="font-medium text-white text-sm truncate flex-1">
          {execution.goal || "(no goal)"}
        </span>

        <div className="flex items-center gap-3 shrink-0 ml-2">
          {execution.framework && (
            <span className="text-xs text-gray-600 hidden md:block">{execution.framework}</span>
          )}
          <StatusBadge status={execution.status} />
          {execution.overall_decision && (
            <DecisionBadge decision={execution.overall_decision} />
          )}
          {execution.threat_count > 0 && (
            <span className="text-xs text-red-400 font-medium">{execution.threat_count} threat{execution.threat_count > 1 ? "s" : ""}</span>
          )}
          {execution.max_risk != null && (
            <span className="text-xs text-gray-600">risk {execution.max_risk.toFixed(0)}</span>
          )}
          <span className="text-xs text-gray-600 hidden lg:block">{fmtDuration(execution)}</span>
          <span className="text-xs text-gray-700 hidden xl:block">{fmtTime(execution.started_at)}</span>
        </div>
      </button>

      {open && <ExecutionDetails execution={execution} />}
    </div>
  );
}

export function ExecutionsPage({ refreshTick }: Props) {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getExecutions().then(setExecutions).catch((e) => setErr(String(e)));
  }, [refreshTick]);

  // Poll for cross-process updates (agents running in separate terminals)
  useEffect(() => {
    const id = setInterval(() => {
      api.getExecutions().then(setExecutions).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, []);

  const exportAll = () => { window.open(api.exportUrl("json"), "_blank"); };
  const exportCsv = () => { window.open(api.exportUrl("csv"), "_blank"); };

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-3 border-b border-gray-800 flex items-center justify-between shrink-0">
        <h1 className="text-sm font-semibold text-white">Executions</h1>
        <div className="flex gap-2">
          <ExportBtn label="JSON" onClick={exportAll} />
          <ExportBtn label="CSV" onClick={exportCsv} />
        </div>
      </div>

      {err && <p className="px-6 py-3 text-red-400 text-sm">{err}</p>}

      {executions.length === 0 && !err ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          No executions yet. Run an agent with AgentWall protection.
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {executions.map((ex, i) => (
            <ExecutionCard
              key={ex.id}
              execution={ex}
              index={executions.length - i}
              isLatest={i === 0}
            />
          ))}
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
