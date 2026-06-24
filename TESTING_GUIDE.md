# AgentWall Testing Guide

---

## Running Tests

```bash
# All tests
pytest tests/

# Verbose
pytest tests/ -v

# Unit tests only
pytest tests/ --ignore=tests/integration/

# Integration tests only
pytest tests/integration/

# Single test file
pytest tests/test_security_engine.py -v

# Single test
pytest tests/test_security_engine.py::test_allow_low_risk -v

# Filter by name pattern
pytest tests/ -k "engine" -v
```

---

## Test Organization

```
tests/
├── conftest.py                    # Shared fixtures
├── test_cli.py                    # CLI command behavior
├── test_config_manager.py         # ConfigManager: providers, thresholds
├── test_detectors.py              # SensitiveResource, ScopeExpansion, DataExfiltration detectors
├── test_engine_defaults.py        # build_default_engine(), EvalContext history, protect_agent goal
├── test_event_manager.py          # EventManager: record, retrieve, history
├── test_goal_inference.py         # Goal inference per framework
├── test_goal_tracker.py           # GoalTracker: segments, transitions, heuristics
├── test_inspector_desktop.py      # Inspector launch (mocked PyWebView)
├── test_interceptors.py           # ToolInterceptor, protect_tool
├── test_event_bus.py              # EventBus pub/sub, async delivery, thread-safe publish
├── test_inspector_routes.py       # Inspector REST API: sessions, events, goals, policies, export
├── test_parse_robust.py           # parse_llm_response: nested JSON, fences, prose embedding
├── test_policy_engine.py          # Policy matching, rule evaluation
├── test_policy_priority.py        # Policy priority ordering, set_priority, schema
├── test_post_execution.py         # after_execute: result analysis, persistence, security model
├── test_provider_keyring.py       # OS keyring store/get/delete
├── test_providers.py              # BaseEvaluator, build_prompt, parse_llm_response
├── test_registry.py               # ProviderRegistry, load_chain
├── test_result_analyzer.py        # ResultAnalyzer: all tool types, classifications, metadata rules
├── test_security_engine.py        # SecurityEngine threshold routing, LLM escalation
├── test_security_rules.py         # Risk scoring rules
├── test_session_manager.py        # Session create/end/update
├── test_storage.py                # Database schema, models
└── integration/
    ├── test_crewai_integration.py          # CrewAI tool wrapping, sync+async
    ├── test_langchain_integration.py       # LangChain tool wrapping, sync+async
    └── test_openai_agents_integration.py   # OpenAI Agents SDK wrapping, goal inference
```

**Current count: 267 tests, all passing.**

---

## Fixtures

### `db` (conftest.py)

Creates an isolated temporary SQLite database for each test. Cleans up after the test.

```python
def test_something(db):
    session = SessionManager(db).create("test goal")
    ...
```

The `db` fixture uses `tempfile.mkdtemp(prefix="agentwall_test_")` to avoid Windows `tmp_path` permission issues.

### Manual DB (for tests not using the fixture)

```python
import tempfile, shutil
from pathlib import Path
from agentwall.storage.database import Database

def _make_db():
    tmpdir = tempfile.mkdtemp(prefix="aw_test_")
    return Database(path=Path(tmpdir) / "test.db"), tmpdir

def test_something():
    db, tmpdir = _make_db()
    try:
        ...
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
```

---

## Writing Tests

### Unit tests

Test a single component in isolation. Mock external dependencies (LLM providers, OS keyring) using `unittest.mock.MagicMock` or `patch`.

```python
from unittest.mock import MagicMock, patch
from agentwall.security.engine import SecurityEngine
from agentwall.core.types import DecisionType, ToolType, ToolAction, ResourceCategory, RuntimeEvent

def test_allow_low_risk():
    engine = SecurityEngine(
        warn_threshold=30.0,
        block_threshold=70.0,
        detectors=[],  # disable all detectors
    )
    event = RuntimeEvent(
        session_id="s1", goal="fix bug",
        tool_type=ToolType.FILESYSTEM, action=ToolAction.READ,
        target="/app/login.tsx", resource_category=ResourceCategory.CODE,
        metadata={}, tool_name="read_file",
    )
    decision = engine.evaluate(event, [])
    assert decision.type == DecisionType.ALLOW
```

### Integration tests

Test real framework dispatch paths. Use `langchain_core.tools.tool`, `agents.FunctionTool`, `crewai.tools.tool` — no mocks.

```python
from langchain_core.tools import tool
from agentwall.integrations.langchain import wrap_langchain_tool
from agentwall.core.types import ToolType

def test_wrap_intercepts(db):
    @tool
    def read_file(path: str) -> str:
        """Read a file."""
        return f"contents:{path}"

    session = SessionManager(db).create("test")
    engine = SecurityEngine(detectors=[])
    interceptor = ToolInterceptor(db, engine)

    wrap_langchain_tool(read_file, tool_type=ToolType.FILESYSTEM,
                        session_id=session.id, goal="test", interceptor=interceptor)

    result = read_file.run("/app/main.py")
    assert "contents:" in result
```

### Keyring tests

Keyring tests use in-memory mock backends via `keyring.set_keyring()`. See `tests/test_provider_keyring.py` for pattern.

### LLM provider tests

Provider tests mock the SDK client to avoid real API calls. See `tests/test_providers.py`.

---

## Platform Notes

### Windows

`pytest`'s built-in `tmp_path` fixture fails on some Windows configurations with `PermissionError: [WinError 5]`. All AgentWall tests use `tempfile.mkdtemp()` instead. Do not use `tmp_path` in new tests.

### asyncio

Tests using `async def` require `@pytest.mark.asyncio`. `asyncio_mode = "strict"` is set in `pyproject.toml`. This means all async tests must be explicitly marked.

---

## Coverage

To run with coverage:

```bash
pip install pytest-cov
pytest tests/ --cov=agentwall --cov-report=term-missing
```

---

## CI

The test suite is designed to run without any external services:
- No real LLM calls (mocked)
- No real keyring backends (mocked in keyring tests)
- No network access required
- All tests use isolated temporary databases

Integration tests require the framework packages (`openai-agents`, `langchain-core`, `crewai`). Install with:

```bash
pip install agentwall[dev,integrations]
```
