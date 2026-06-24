export type Page = "overview" | "sessions" | "timeline" | "providers" | "policies";

const PAGES: { id: Page; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "sessions", label: "Sessions" },
  { id: "providers", label: "Providers" },
  { id: "policies", label: "Policies" },
];

interface Props {
  page: Page;
  onNav: (p: Page) => void;
  version: string;
}

export function NavBar({ page, onNav, version }: Props) {
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
            page === p.id || (page === "timeline" && p.id === "sessions")
              ? "bg-gray-700 text-white"
              : "text-gray-400 hover:text-white hover:bg-gray-800"
          }`}
        >
          {p.label}
        </button>
      ))}
      <span className="ml-auto text-xs text-gray-600 select-none">v{version}</span>
    </nav>
  );
}
