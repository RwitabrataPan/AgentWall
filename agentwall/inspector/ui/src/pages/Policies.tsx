import { useEffect, useState } from "react";
import { api, type Policy } from "../api/client";

const DEFAULT_CONFIG = JSON.stringify(
  { description: "", rules: [{ tool_type: "filesystem", pattern: "*/.ssh/*", decision: "block", reason: "SSH key access" }] },
  null,
  2,
);

export function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [modal, setModal] = useState<null | "create" | Policy>(null);
  const [formName, setFormName] = useState("");
  const [formConfig, setFormConfig] = useState(DEFAULT_CONFIG);
  const [configErr, setConfigErr] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.getPolicies().then(setPolicies).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, []);

  const openCreate = () => {
    setFormName("");
    setFormConfig(DEFAULT_CONFIG);
    setConfigErr(null);
    setModal("create");
  };

  const openEdit = (p: Policy) => {
    setFormName(p.name);
    setFormConfig(JSON.stringify(p.config, null, 2));
    setConfigErr(null);
    setModal(p);
  };

  const parseConfig = (): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(formConfig);
      setConfigErr(null);
      return parsed;
    } catch (e) {
      setConfigErr(`Invalid JSON: ${e}`);
      return null;
    }
  };

  const save = async () => {
    const config = parseConfig();
    if (!config) return;
    try {
      if (modal === "create") {
        if (!formName.trim()) { setConfigErr("Name required"); return; }
        await api.createPolicy(formName.trim(), config);
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
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500 text-sm">
                  No policies. Click + Add Policy to create one.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Create / Edit modal */}
      {modal !== null && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setModal(null)}>
          <div
            className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-lg shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-semibold text-white mb-4">
              {modal === "create" ? "Create Policy" : `Edit: ${(modal as Policy).name}`}
            </h3>

            {modal === "create" && (
              <label className="block mb-3">
                <span className="text-xs text-gray-400">Name</span>
                <input
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="my-policy"
                  className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600"
                />
              </label>
            )}

            <label className="block">
              <span className="text-xs text-gray-400">Config (JSON)</span>
              <textarea
                value={formConfig}
                onChange={(e) => setFormConfig(e.target.value)}
                rows={12}
                className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-200 font-mono placeholder-gray-600 resize-y"
              />
            </label>

            {configErr && <p className="mt-2 text-xs text-red-400">{configErr}</p>}

            <div className="flex gap-2 justify-end mt-4">
              <Btn onClick={() => setModal(null)} label="Cancel" />
              <Btn onClick={save} label="Save" variant="blue" />
            </div>
          </div>
        </div>
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
