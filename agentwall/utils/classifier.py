from __future__ import annotations

"""Automatic ToolType classification from function name and docstring."""

from agentwall.core.types import ToolType

# Ordered by specificity — first match wins
_PATTERNS: list[tuple[frozenset[str], ToolType]] = [
    (
        frozenset([
            "file", "directory", "folder", "path", "read_file", "write_file",
            "open_file", "save_file", "load_file", "delete_file", "copy_file",
            "move_file", "list_dir", "list_files", "filesystem", "readfile",
            "writefile", "read_text", "write_text",
        ]),
        ToolType.FILESYSTEM,
    ),
    (
        frozenset([
            "run", "exec", "execute", "shell", "bash", "subprocess", "terminal",
            "cmd", "command", "process", "run_command", "execute_command",
            "run_shell", "run_bash",
        ]),
        ToolType.TERMINAL,
    ),
    (
        frozenset([
            "browse", "web", "url", "scrape", "navigate", "click", "screenshot",
            "crawler", "browser", "open_url", "fetch_page", "get_url",
            "visit", "selenium", "playwright",
        ]),
        ToolType.BROWSER,
    ),
    (
        frozenset([
            "sql", "database", "db", "query_db", "insert_row", "select",
            "record", "table", "query_database", "run_query", "execute_sql",
            "fetch_row", "postgres", "mysql", "sqlite", "query", "queries",
        ]),
        ToolType.DATABASE,
    ),
    (
        frozenset([
            "email", "mail", "smtp", "inbox", "send_email", "send_mail",
            "outlook", "gmail", "mailing", "send_message", "compose_email",
        ]),
        ToolType.EMAIL,
    ),
    (
        frozenset([
            "api", "request", "endpoint", "webhook", "http", "rest", "graphql",
            "call_api", "fetch_api", "http_post", "http_get", "http_put",
            "http_patch", "http_request", "post_request", "get_request",
        ]),
        ToolType.API,
    ),
]


def classify_tool(name: str, doc: str = "") -> ToolType:
    """Infer ToolType from function name and docstring. Returns GENERAL if unknown.

    Name word matches score 3×, doc word matches score 1×. Highest total wins.
    Tie-breaks by pattern list order (first defined = higher priority).
    """
    name_words = set(name.lower().replace("_", " ").split())
    doc_words = set((doc or "").lower().split())

    best_type: ToolType | None = None
    best_score = 0
    for keywords, tool_type in _PATTERNS:
        score = (
            3 * sum(1 for kw in keywords if kw in name_words)
            + sum(1 for kw in keywords if kw in doc_words)
        )
        if score > best_score:
            best_score = score
            best_type = tool_type
    return best_type if best_type is not None else ToolType.GENERAL
