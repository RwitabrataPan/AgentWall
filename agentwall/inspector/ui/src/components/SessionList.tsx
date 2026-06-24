import type { Session } from "../api/client";

interface Props {
  sessions: Session[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function SessionList({ sessions, selectedId, onSelect }: Props) {
  if (sessions.length === 0) {
    return (
      <div className="p-6 text-gray-400 text-sm">
        No sessions yet. Run an agent with AgentWall protection to see sessions here.
      </div>
    );
  }

  return (
    <ul className="divide-y divide-gray-800">
      {sessions.map((s) => (
        <li
          key={s.id}
          onClick={() => onSelect(s.id)}
          className={`px-4 py-3 cursor-pointer hover:bg-gray-800 transition-colors ${
            selectedId === s.id ? "bg-gray-800 border-l-2 border-blue-500" : ""
          }`}
        >
          <p className="text-sm font-medium text-white truncate">{s.user_goal}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {new Date(s.created_at * 1000).toLocaleString()}
            {s.ended_at && (
              <span className="ml-2 text-gray-600">ended</span>
            )}
          </p>
        </li>
      ))}
    </ul>
  );
}
