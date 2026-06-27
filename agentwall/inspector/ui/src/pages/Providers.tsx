import { useEffect, useState } from "react";
import { api, type Provider, type ProviderTestResult } from "../api/client";

const PROVIDER_NAMES = ["openai", "anthropic", "groq", "deepseek", "ollama"];

const MODELS: Record<string, string[]> = {
  openai:    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  anthropic: ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
  groq:      ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"],
  deepseek:  ["deepseek-chat", "deepseek-reasoner"],
  ollama:    ["llama3.2", "llama3.1", "mistral", "gemma2", "phi3"],
};

const NO_KEY = new Set(["ollama"]);

interface Props {
  refreshTick: number;
}

export function ProvidersPage({ refreshTick }: Props) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [testing, setTesting] = useState<Record<string, ProviderTestResult | "loading">>({});
  const [editRow, setEditRow] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<{ model: string; priority: number; enabled: boolean }>({
    model: "", priority: 0, enabled: true,
  });
  const [keyModal, setKeyModal] = useState<string | null>(null);
  const [keyValue, setKeyValue] = useState("");
  const [keyMsg, setKeyMsg] = useState<string | null>(null);
  const [addModal, setAddModal] = useState(false);
  const [addForm, setAddForm] = useState({ provider: "openai", model: "gpt-4o-mini", priority: 1, enabled: true, api_key: "" });
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.getProviders().then((data) => { setProviders(data); setErr(null); }).catch((e) => setErr(String(e)));
  useEffect(() => { load(); }, [refreshTick]);

  const startEdit = (p: Provider) => {
    setEditRow(p.provider);
    setEditForm({ model: p.model, priority: p.priority, enabled: p.enabled });
  };

  const saveEdit = async (provider: string) => {
    try {
      await api.updateProvider(provider, editForm);
      setEditRow(null);
      load();
    } catch (e) { setErr(String(e)); }
  };

  const testProvider = async (provider: string) => {
    setTesting((t) => ({ ...t, [provider]: "loading" }));
    const result = await api.testProvider(provider).catch((e) => ({
      provider, model: "", healthy: false, latency_ms: null, error: String(e),
    }));
    setTesting((t) => ({ ...t, [provider]: result }));
  };

  const saveKey = async () => {
    if (!keyModal) return;
    try {
      await api.updateProviderKey(keyModal, keyValue);
      setKeyMsg("API key saved to OS keyring.");
      setKeyValue("");
    } catch (e) { setKeyMsg(`Error: ${e}`); }
  };

  const deleteProvider = async (provider: string) => {
    if (!confirm(`Delete ${provider}?`)) return;
    try { await api.deleteProvider(provider); load(); }
    catch (e) { setErr(String(e)); }
  };

  const addProvider = async () => {
    try {
      await api.updateProvider(addForm.provider, { model: addForm.model, priority: addForm.priority, enabled: addForm.enabled });
      if (addForm.api_key && !NO_KEY.has(addForm.provider)) {
        await api.updateProviderKey(addForm.provider, addForm.api_key);
      }
      setAddModal(false);
      setAddForm({ provider: "openai", model: "gpt-4o-mini", priority: 1, enabled: true, api_key: "" });
      load();
    } catch (e) { setErr(String(e)); }
  };

  const testResult = (p: string): ProviderTestResult | null =>
    testing[p] && testing[p] !== "loading" ? testing[p] as ProviderTestResult : null;

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-3 border-b border-gray-800 flex items-center justify-between shrink-0">
        <h1 className="text-sm font-semibold text-white">Providers</h1>
        <button
          onClick={() => setAddModal(true)}
          className="px-3 py-1 text-xs bg-blue-700 hover:bg-blue-600 text-white rounded transition-colors"
        >
          + Add Provider
        </button>
      </div>

      {err && <p className="px-6 py-2 text-red-400 text-sm">{err}</p>}

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 border-b border-gray-800">
              <th className="px-4 py-2 text-left font-medium">Provider</th>
              <th className="px-4 py-2 text-left font-medium">Model</th>
              <th className="px-4 py-2 text-left font-medium">Priority</th>
              <th className="px-4 py-2 text-left font-medium">Status</th>
              <th className="px-4 py-2 text-left font-medium">Health</th>
              <th className="px-4 py-2 text-left font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => {
              const isEditing = editRow === p.provider;
              const tr = testResult(p.provider);
              const isLoading = testing[p.provider] === "loading";
              return (
                <tr key={p.provider} className="border-b border-gray-800">
                  <td className="px-4 py-3 font-mono text-white">{p.provider}</td>
                  <td className="px-4 py-3 text-gray-300">
                    {isEditing ? (
                      <select
                        value={editForm.model}
                        onChange={(e) => setEditForm((f) => ({ ...f, model: e.target.value }))}
                        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white"
                      >
                        {(MODELS[p.provider] ?? []).map((m) => (
                          <option key={m} value={m}>{m}</option>
                        ))}
                      </select>
                    ) : p.model}
                  </td>
                  <td className="px-4 py-3 text-gray-400">
                    {isEditing ? (
                      <input
                        type="number"
                        value={editForm.priority}
                        onChange={(e) => setEditForm((f) => ({ ...f, priority: +e.target.value }))}
                        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white w-16"
                      />
                    ) : p.priority}
                  </td>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <button
                        onClick={() => setEditForm((f) => ({ ...f, enabled: !f.enabled }))}
                        className={`text-xs px-2 py-0.5 rounded border ${editForm.enabled ? "text-green-400 border-green-800 bg-green-950" : "text-gray-500 border-gray-700 bg-gray-900"}`}
                      >
                        {editForm.enabled ? "enabled" : "disabled"}
                      </button>
                    ) : (
                      <span className={`text-xs ${p.enabled ? "text-green-400" : "text-gray-500"}`}>
                        {p.enabled ? "enabled" : "disabled"}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {isLoading ? (
                      <span className="text-gray-500">testing…</span>
                    ) : tr ? (
                      tr.healthy
                        ? <span className="text-green-400">OK {tr.latency_ms != null && `(${tr.latency_ms.toFixed(0)}ms)`}</span>
                        : <span className="text-red-400" title={tr.error ?? ""}>{tr.error?.slice(0, 40)}</span>
                    ) : (
                      <span className="text-gray-700">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 flex-wrap">
                      {isEditing ? (
                        <>
                          <Btn onClick={() => saveEdit(p.provider)} label="Save" variant="blue" />
                          <Btn onClick={() => setEditRow(null)} label="Cancel" />
                        </>
                      ) : (
                        <>
                          <Btn onClick={() => startEdit(p)} label="Edit" />
                          {!NO_KEY.has(p.provider) && (
                            <Btn onClick={() => { setKeyModal(p.provider); setKeyMsg(null); }} label="Key" />
                          )}
                          <Btn onClick={() => testProvider(p.provider)} label="Test" />
                          <Btn onClick={() => deleteProvider(p.provider)} label="Delete" variant="red" />
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
            {providers.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500 text-sm">
                  No providers configured. Click + Add Provider.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* API Key modal */}
      {keyModal && (
        <Modal title={`Update API Key — ${keyModal}`} onClose={() => setKeyModal(null)}>
          <p className="text-xs text-gray-500 mb-3">Stored in OS keyring. Never written to disk.</p>
          <input
            type="password"
            value={keyValue}
            onChange={(e) => setKeyValue(e.target.value)}
            placeholder="sk-..."
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 mb-3"
            onKeyDown={(e) => e.key === "Enter" && saveKey()}
          />
          {keyMsg && <p className={`text-xs mb-3 ${keyMsg.startsWith("Error") ? "text-red-400" : "text-green-400"}`}>{keyMsg}</p>}
          <div className="flex gap-2 justify-end">
            <Btn onClick={() => setKeyModal(null)} label="Close" />
            <Btn onClick={saveKey} label="Save Key" variant="blue" />
          </div>
        </Modal>
      )}

      {/* Add provider modal */}
      {addModal && (
        <Modal title="Add Provider" onClose={() => setAddModal(false)}>
          <div className="space-y-3">
            <label className="block">
              <span className="text-xs text-gray-400">Provider</span>
              <select
                value={addForm.provider}
                onChange={(e) => setAddForm((f) => ({ ...f, provider: e.target.value, model: MODELS[e.target.value]?.[0] ?? "" }))}
                className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-2 py-2 text-sm text-white"
              >
                {PROVIDER_NAMES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Model</span>
              <select
                value={addForm.model}
                onChange={(e) => setAddForm((f) => ({ ...f, model: e.target.value }))}
                className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-2 py-2 text-sm text-white"
              >
                {(MODELS[addForm.provider] ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Priority</span>
              <input
                type="number"
                value={addForm.priority}
                onChange={(e) => setAddForm((f) => ({ ...f, priority: +e.target.value }))}
                className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-2 py-2 text-sm text-white"
              />
            </label>
            {!NO_KEY.has(addForm.provider) && (
              <label className="block">
                <span className="text-xs text-gray-400">API Key (stored in OS keyring)</span>
                <input
                  type="password"
                  value={addForm.api_key}
                  onChange={(e) => setAddForm((f) => ({ ...f, api_key: e.target.value }))}
                  placeholder="sk-..."
                  className="block w-full mt-1 bg-gray-800 border border-gray-700 rounded px-2 py-2 text-sm text-white placeholder-gray-600"
                />
              </label>
            )}
          </div>
          <div className="flex gap-2 justify-end mt-4">
            <Btn onClick={() => setAddModal(false)} label="Cancel" />
            <Btn onClick={addProvider} label="Add Provider" variant="blue" />
          </div>
        </Modal>
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

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-white mb-4">{title}</h3>
        {children}
      </div>
    </div>
  );
}
