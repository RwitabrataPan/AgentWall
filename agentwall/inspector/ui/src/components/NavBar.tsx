export type Page = "overview" | "executions" | "sessions" | "timeline" | "providers" | "policies";

const PAGES: { id: Page; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "executions", label: "Executions" },
  { id: "providers", label: "Providers" },
  { id: "policies", label: "Policies" },
];

interface Props {
  page: Page;
  onNav: (p: Page) => void;
  version: string;
  projectName?: string;
  onRefresh: () => void;
  refreshing?: boolean;
}

export function NavBar({ page, onNav, version, projectName, onRefresh, refreshing = false }: Props) {
  return (
    <nav className="bg-gray-900 border-b border-gray-800 px-4 flex items-center gap-1 h-12 shrink-0">
      <span className="font-bold text-white mr-4 tracking-tight select-none">
        AgentWall <span className="text-blue-400">Inspector</span>
      </span>
      {PAGES.map((p) => (
        <button
          key={p.id}
          onClick={() => onNav(p.id)}
          className={`px-3 py-1.5 rounded text-sm transition-colors ${
            page === p.id || (page === "timeline" && p.id === "executions")
              ? "bg-gray-700 text-white"
              : "text-gray-400 hover:text-white hover:bg-gray-800"
          }`}
        >
          {p.label}
        </button>
      ))}
      {projectName && (
        <span className="ml-4 text-xs text-gray-600 select-none hidden md:block">
          <span className="text-gray-700">project: </span>
          <span className="text-gray-400">{projectName}</span>
        </span>
      )}
      <button
        onClick={onRefresh}
        disabled={refreshing}
        className="ml-auto px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-60 disabled:hover:bg-gray-800 text-gray-300 rounded border border-gray-700 transition-colors"
        title="Refresh Inspector data"
      >
        {refreshing ? "Refreshing" : "Refresh"}
      </button>
      <span className="text-xs text-gray-600 select-none">v{version}</span>
    </nav>
  );
}
