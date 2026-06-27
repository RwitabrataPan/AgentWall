import { useEffect, useState } from "react";
import { api, type Policy, type PolicyTemplate, type PolicyTestResult } from "../api/client";

const TOOL_TYPES = ["filesystem", "terminal", "browser", "api", "database", "email", "general"];
const DECISIONS = ["block", "warn", "allow"];

const EMPTY_RULE = {
  tool_type: "filesystem",
  pattern: "",
  decision: "block",
  reason: "",
  action: "",
  resource_category: "",
};

function buildConfig(name: string, description: string, rules: typeof EMPTY_RULE[]): Record<string, unknown> {
  return {
    description,
    rules: rules.map((r) => {
      const rule: Record<string, string> = {
        tool_type: r.tool_type,
        decision: r.decision,
        reason: r.reason,
      };
      if (r.pattern) rule.pattern = r.pattern;
      if (r.action) rule.action = r.action;
      if (r.resource_category) rule.resource_category = r.resource_category;
      return rule;
    }),
  };
}

interface BuilderState {
  name: string;
  description: string;
  priority: number;
  rules: typeof EMPTY_RULE[];
  jsonMode: boolean;
  rawJson: string;
}

function defaultBuilder(): BuilderState {
  return {
    name: "",
    description: "",
    priority: 0,
    rules: [{ ...EMPTY_RULE }],
    jsonMode: false,
    rawJson: "",
  };
}

function builderFromPolicy(p: Policy): BuilderState {
  const cfg = p.config as { description?: string; rules?: Record<string, string>[] };
  return {
    name: p.name,
    description: cfg.description ?? "",
    priority: p.priority,
    rules: (cfg.rules ?? []).map((r) => ({
      tool_type: r.tool_type ?? "filesystem",
      pattern: r.pattern ?? "",
      decision: r.decision ?? "block",
      reason: r.reason ?? "",
      action: r.action ?? "",
      resource_category: r.resource_category ?? "",
    })),
    jsonMode: false,
    rawJson: JSON.stringify(p.config, null, 2),
  };
}

function TestPanel({
  config,
  onClose,
}: {
  config: Record<string, unknown>;
  onClose: () => void;
}) {
  const [toolType, setToolType] = useState("filesystem");
  const [target, setTarget] = useState("");
  const [action, setAction] = useState("");
  const [result, setResult] = useState<PolicyTestResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    setErr(null);
    try {
      const r = await api.testPolicy(config, toolType, target, action || undefined);
      setResult(r);
    } catch (e) {
      setErr(String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-white mb-4">Test Policy</h3>

        <label className="block mb-3">
          <span className="text-xs text-gray-400">Tool Type</span>
          <select
            value={toolType}
            onChange={(e) => setToolType(e.target.value)}
            className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white"
          >
            {TOOL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>

        <label className="block mb-3">
          <span className="text-xs text-gray-400">Target / Path</span>
          <input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder="/home/user/.ssh/id_rsa"
            className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600"
          />
        </label>

        <label className="block mb-4">
          <span className="text-xs text-gray-400">Action (optional)</span>
          <input
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="read, write, execute…"
            className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600"
          />
        </label>

        {err && <p className="mb-3 text-xs text-red-400">{err}</p>}

        {result && (
          <div className={`mb-4 p-3 rounded border text-xs ${result.matched ? "border-orange-800 bg-orange-950" : "border-green-800 bg-green-950"}`}>
            {result.matched ? (
              <>
                <p className="font-semibold text-orange-400 mb-1">
                  MATCHED → {result.decision?.toUpperCase()}
                </p>
                {result.reason && <p className="text-gray-300">Reason: {result.reason}</p>}
                {result.rule_index != null && <p className="text-gray-500 mt-1">Rule #{result.rule_index + 1}</p>}
              </>
            ) : (
              <p className="font-semibold text-green-400">No match — event would pass through</p>
            )}
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <Btn onClick={onClose} label="Close" />
          <Btn onClick={run} label={running ? "Testing…" : "Run Test"} variant="blue" />
        </div>
      </div>
    </div>
  );
}

interface Props {
  refreshTick: number;
}

export function PoliciesPage({ refreshTick }: Props) {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [templates, setTemplates] = useState<PolicyTemplate[]>([]);
  const [modal, setModal] = useState<null | "create" | Policy>(null);
  const [builder, setBuilder] = useState<BuilderState>(defaultBuilder());
  const [configErr, setConfigErr] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [testConfig, setTestConfig] = useState<Record<string, unknown> | null>(null);

  const load = () => api.getPolicies().then((data) => { setPolicies(data); setErr(null); }).catch((e) => setErr(String(e)));
  useEffect(() => {
    load();
    api.getPolicyTemplates().then(setTemplates).catch(() => {});
  }, [refreshTick]);

  const openCreate = () => {
    setBuilder(defaultBuilder());
    setConfigErr(null);
    setModal("create");
  };

  const openEdit = (p: Policy) => {
    setBuilder(builderFromPolicy(p));
    setConfigErr(null);
    setModal(p);
  };

  const applyTemplate = (tpl: PolicyTemplate) => {
    const cfg = tpl.config as { description?: string; rules?: Record<string, string>[] };
    setBuilder((b) => ({
      ...b,
      name: b.name || tpl.name,
      description: cfg.description ?? tpl.description,
      rules: (cfg.rules ?? []).map((r) => ({
        tool_type: r.tool_type ?? "filesystem",
        pattern: r.pattern ?? "",
        decision: r.decision ?? "block",
        reason: r.reason ?? "",
        action: r.action ?? "",
        resource_category: r.resource_category ?? "",
      })),
      rawJson: JSON.stringify(tpl.config, null, 2),
    }));
  };

  const getConfig = (): Record<string, unknown> | null => {
    if (builder.jsonMode) {
      try {
        const parsed = JSON.parse(builder.rawJson);
        setConfigErr(null);
        return parsed;
      } catch (e) {
        setConfigErr(`Invalid JSON: ${e}`);
        return null;
      }
    }
    return buildConfig(builder.name, builder.description, builder.rules);
  };

  const save = async () => {
    const config = getConfig();
    if (!config) return;
    try {
      if (modal === "create") {
        if (!builder.name.trim()) { setConfigErr("Name required"); return; }
        await api.createPolicy(builder.name.trim(), config, builder.priority);
      } else {
        await api.updatePolicy((modal as Policy).name, config);
      }
      setModal(null);
      load();
    } catch (e) { setErr(String(e)); }
  };

  const toggle = async (p: Policy) => {
    try {
      await (p.enabled ? api.disablePolicy(p.name) : api.enablePolicy(p.name));
      load();
    } catch (e) { setErr(String(e)); }
  };

  const del = async (p: Policy) => {
    if (!confirm(`Delete policy "${p.name}"?`)) return;
    try { await api.deletePolicy(p.name); load(); }
    catch (e) { setErr(String(e)); }
  };

  const ruleCount = (p: Policy) =>
    Array.isArray((p.config as { rules?: unknown[] }).rules) ? (p.config as { rules: unknown[] }).rules.length : 0;

  const updateRule = (i: number, field: string, val: string) => {
    setBuilder((b) => {
      const rules = [...b.rules];
      rules[i] = { ...rules[i], [field]: val };
      return { ...b, rules };
    });
  };

  const addRule = () => setBuilder((b) => ({ ...b, rules: [...b.rules, { ...EMPTY_RULE }] }));
  const removeRule = (i: number) =>
    setBuilder((b) => ({ ...b, rules: b.rules.filter((_, idx) => idx !== i) }));

  const syncJsonFromBuilder = () => {
    const cfg = buildConfig(builder.name, builder.description, builder.rules);
    setBuilder((b) => ({ ...b, rawJson: JSON.stringify(cfg, null, 2) }));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-3 border-b border-gray-800 flex items-center justify-between shrink-0">
        <h1 className="text-sm font-semibold text-white">Policies</h1>
        <button
          onClick={openCreate}
          className="px-3 py-1 text-xs bg-blue-700 hover:bg-blue-600 text-white rounded transition-colors"
        >
          + Add Policy
        </button>
      </div>

      {err && <p className="px-6 py-2 text-red-400 text-sm">{err}</p>}

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 border-b border-gray-800">
              <th className="px-4 py-2 text-left font-medium">Name</th>
              <th className="px-4 py-2 text-left font-medium">Status</th>
              <th className="px-4 py-2 text-left font-medium">Rules</th>
              <th className="px-4 py-2 text-left font-medium">Priority</th>
              <th className="px-4 py-2 text-left font-medium">Created</th>
              <th className="px-4 py-2 text-left font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {policies.map((p) => (
              <tr key={p.id} className="border-b border-gray-800 hover:bg-gray-900 transition-colors">
                <td className="px-4 py-3 font-medium text-white">{p.name}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs ${p.enabled ? "text-green-400" : "text-gray-600"}`}>
                    {p.enabled ? "enabled" : "disabled"}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-400 tabular-nums">{ruleCount(p)}</td>
                <td className="px-4 py-3 text-gray-500 tabular-nums">{p.priority}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {new Date(p.created_at * 1000).toLocaleDateString()}
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-1 flex-wrap">
                    <Btn onClick={() => openEdit(p)} label="Edit" />
                    <Btn
                      onClick={() => toggle(p)}
                      label={p.enabled ? "Disable" : "Enable"}
                      variant={p.enabled ? "gray" : "blue"}
                    />
                    <Btn onClick={() => del(p)} label="Delete" variant="red" />
                  </div>
                </td>
              </tr>
            ))}
            {policies.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500 text-sm">
                  No policies. Click + Add Policy to create one.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Policy modal */}
      {modal !== null && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setModal(null)}>
          <div
            className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-2xl shadow-xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white">
                {modal === "create" ? "Create Policy" : `Edit: ${(modal as Policy).name}`}
              </h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    if (!builder.jsonMode) syncJsonFromBuilder();
                    setBuilder((b) => ({ ...b, jsonMode: !b.jsonMode }));
                  }}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  {builder.jsonMode ? "Visual Mode" : "JSON Mode"}
                </button>
              </div>
            </div>

            {!builder.jsonMode ? (
              <>
                {/* Template selector */}
                {templates.length > 0 && (
                  <div className="mb-4">
                    <span className="text-xs text-gray-400 block mb-1">Template</span>
                    <div className="flex flex-wrap gap-1">
                      {templates.map((tpl) => (
                        <button
                          key={tpl.name}
                          onClick={() => applyTemplate(tpl)}
                          className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 rounded transition-colors"
                        >
                          {tpl.name}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Name + description */}
                {modal === "create" && (
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    <label className="block">
                      <span className="text-xs text-gray-400">Name *</span>
                      <input
                        value={builder.name}
                        onChange={(e) => setBuilder((b) => ({ ...b, name: e.target.value }))}
                        placeholder="my-policy"
                        className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600"
                      />
                    </label>
                    <label className="block">
                      <span className="text-xs text-gray-400">Priority (higher = evaluated first)</span>
                      <input
                        type="number"
                        value={builder.priority}
                        onChange={(e) => setBuilder((b) => ({ ...b, priority: Number(e.target.value) }))}
                        className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white"
                      />
                    </label>
                  </div>
                )}

                <label className="block mb-4">
                  <span className="text-xs text-gray-400">Description</span>
                  <input
                    value={builder.description}
                    onChange={(e) => setBuilder((b) => ({ ...b, description: e.target.value }))}
                    placeholder="What this policy does"
                    className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600"
                  />
                </label>

                {/* Rules */}
                <div className="mb-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-400">Rules</span>
                    <button
                      onClick={addRule}
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      + Add Rule
                    </button>
                  </div>
                  <div className="space-y-3">
                    {builder.rules.map((rule, i) => (
                      <div key={i} className="bg-gray-800 border border-gray-700 rounded p-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-gray-500">Rule {i + 1}</span>
                          {builder.rules.length > 1 && (
                            <button
                              onClick={() => removeRule(i)}
                              className="text-xs text-red-500 hover:text-red-400"
                            >
                              Remove
                            </button>
                          )}
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="text-xs text-gray-500 block mb-1">Tool Type</label>
                            <select
                              value={rule.tool_type}
                              onChange={(e) => updateRule(i, "tool_type", e.target.value)}
                              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-white"
                            >
                              {TOOL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                            </select>
                          </div>
                          <div>
                            <label className="text-xs text-gray-500 block mb-1">Decision</label>
                            <select
                              value={rule.decision}
                              onChange={(e) => updateRule(i, "decision", e.target.value)}
                              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-white"
                            >
                              {DECISIONS.map((d) => <option key={d} value={d}>{d}</option>)}
                            </select>
                          </div>
                        </div>
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Pattern (glob on target path)</label>
                          <input
                            value={rule.pattern}
                            onChange={(e) => updateRule(i, "pattern", e.target.value)}
                            placeholder="*/.ssh/id_* or **/secrets/**"
                            className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-white placeholder-gray-700"
                          />
                        </div>
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Reason</label>
                          <input
                            value={rule.reason}
                            onChange={(e) => updateRule(i, "reason", e.target.value)}
                            placeholder="Why this is blocked/warned"
                            className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-white placeholder-gray-700"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <label className="block mb-4">
                <span className="text-xs text-gray-400">Config (JSON)</span>
                <textarea
                  value={builder.rawJson}
                  onChange={(e) => setBuilder((b) => ({ ...b, rawJson: e.target.value }))}
                  rows={14}
                  className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-200 font-mono placeholder-gray-600 resize-y"
                />
              </label>
            )}

            {configErr && <p className="mt-2 text-xs text-red-400">{configErr}</p>}

            <div className="flex gap-2 justify-between mt-4">
              <Btn
                onClick={() => {
                  const cfg = getConfig();
                  if (cfg) setTestConfig(cfg);
                }}
                label="Test Policy"
                variant="gray"
              />
              <div className="flex gap-2">
                <Btn onClick={() => setModal(null)} label="Cancel" />
                <Btn onClick={save} label="Save" variant="blue" />
              </div>
            </div>
          </div>
        </div>
      )}

      {testConfig && (
        <TestPanel config={testConfig} onClose={() => setTestConfig(null)} />
      )}
    </div>
  );
}

function Btn({ onClick, label, variant = "gray" }: { onClick: () => void; label: string; variant?: "gray" | "blue" | "red" }) {
  const c = variant === "blue" ? "bg-blue-700 hover:bg-blue-600 text-white border-blue-700"
    : variant === "red"  ? "bg-red-950 hover:bg-red-900 text-red-400 border-red-800"
    : "bg-gray-800 hover:bg-gray-700 text-gray-300 border-gray-700";
  return (
    <button onClick={onClick} className={`px-2 py-1 text-xs rounded border transition-colors ${c}`}>
      {label}
    </button>
  );
}
