from __future__ import annotations

import pytest

from agentwall.core.types import ToolType
from agentwall.utils.classifier import classify_tool


@pytest.mark.parametrize("name,doc,expected", [
    ("read_file", "", ToolType.FILESYSTEM),
    ("write_file", "", ToolType.FILESYSTEM),
    ("list_directory", "list files in a directory", ToolType.FILESYSTEM),
    ("run_command", "", ToolType.TERMINAL),
    ("execute_bash", "", ToolType.TERMINAL),
    ("run_shell_command", "executes shell commands", ToolType.TERMINAL),
    ("browse_web", "", ToolType.BROWSER),
    ("fetch_url", "fetch a web url", ToolType.BROWSER),
    ("query_database", "", ToolType.DATABASE),
    ("run_sql", "executes sql queries", ToolType.DATABASE),
    ("send_email", "", ToolType.EMAIL),
    ("compose_mail", "compose and send email", ToolType.EMAIL),
    ("call_api", "", ToolType.API),
    ("http_post", "", ToolType.API),
    ("unknown_tool", "", ToolType.GENERAL),
    ("do_thing", "does a thing", ToolType.GENERAL),
])
def test_classify_tool(name, doc, expected):
    assert classify_tool(name, doc) == expected


def test_classify_prefers_name_over_doc():
    # "read_file" should classify as FILESYSTEM regardless of doc
    assert classify_tool("read_file", "calls an api endpoint") == ToolType.FILESYSTEM


def test_classify_falls_back_to_doc_when_name_generic():
    assert classify_tool("do_action", "execute shell command") == ToolType.TERMINAL
