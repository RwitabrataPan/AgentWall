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
├── conftest.py                        # Shared fixtures; sets AGENTWALL_AUTO=0
├── test_auto_instrumentation.py       # Zero-config auto mode: idempotency, GoalTracker v2 API
├── test_cli.py                        # CLI command behavior
├── test_config_manager.py             # ConfigManager: providers, thresholds
├── test_detectors.py                  # SensitiveResource, ScopeExpansion, DataExfiltration detectors
├── test_engine_defaults.py            # build_default_engine(), EvalContext history, protect_agent goal
├── test_event_bus.py                  # EventBus pub/sub, async delivery, thread-safe publish
├── test_event_manager.py              # EventManager: record, retrieve, history
├── test_goal_drift_detector.py        # GoalDriftDetector: all signal types
├── test_goal_inference.py             # Goal inference per framework
├── test_goal_tracker.py               # GoalTracker: segments, transitions, heuristics
├── test_inspector_desktop.py          # Inspector launch (mocked PyWebView)
├── test_inspector_routes.py           # Inspector REST API: sessions, events, goals, policies, export
├── test_interceptors.py               # ToolInterceptor, protect_tool
├── test_parse_robust.py               # parse_llm_response: nested JSON, fences, prose embedding
├── test_policy_engine.py              # Policy matching, rule evaluation
├── test_policy_priority.py            # Policy priority ordering, set_priority, schema
├── test_post_execution.py             # after_execute: result analysis, persistence, security model
├── test_provider_keyring.py           # OS keyring store/get/delete
├── test_providers.py                  # BaseEvaluator, build_prompt, parse_llm_response
├── test_registry.py                   # ProviderRegistry, load_chain
├── test_result_analyzer.py            # ResultAnalyzer: all tool types, classifications, metadata rules
├── test_security_engine.py            # SecurityEngine threshold routing, LLM escalation
├── test_security_rules.py             # Risk scoring rules
├── test_session_manager.py            # Session create/end/update
├── test_storage.py                    # Database schema, models
├── test_tool_classifier.py            # classify_tool(): all ToolType values + GENERAL fallback
└── integration/
    ├── test_crewai_integration.py              # CrewAI tool wrapping, idempotency, sync+async
    ├── test_langchain_integration.py           # LangChain tool wrapping, idempotency, sync+async
    └── test_openai_agents_integration.py       # OpenAI Agents SDK wrapping, goal inference
```

**Current count: 301 tests, all passing.**

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

`conftest.py` also sets `AGENTWALL_AUTO=0` **before** any agentwall import to prevent zero-config auto-instrumentation from conflicting with explicit `protect_*` calls in tests:

```python
# conftest.py
import os
os.environ["AGENTWALL_AUTO"] = "0"

from agentwall.storage.database import Database
```

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

### GoalTracker v2 tests

Test the new GoalTracker public API introduced in v0.2.0:

```python
from agentwall.security.goal_tracker import GoalTracker
from agentwall.core.session_manager import SessionManager

def test_infer_initial_goal(db):
    session = SessionManager(db).create("")
    ref = [""]
    tracker = GoalTracker(session.id, db, ref)

    changed = tracker.infer_initial_goal("Fix login bug")
    assert changed is True
    assert ref[0] == "Fix login bug"

    # Second call does NOT override an already-set goal
    changed2 = tracker.infer_initial_goal("Something else")
    assert changed2 is False
```

### GoalDriftDetector tests

```python
from agentwall.security.detectors import GoalDriftDetector
from agentwall.core.types import ResourceCategory, RuntimeEvent, ToolAction, ToolType

def test_credential_drift():
    det = GoalDriftDetector()
    event = RuntimeEvent(
        session_id="s1", goal="fix login bug",
        tool_type=ToolType.FILESYSTEM, action=ToolAction.READ,
        target=".env", resource_category=ResourceCategory.CREDENTIALS,
        metadata={}, tool_name="read_file",
    )
    hits = det.detect(event, [])
    assert "goal_drift:credential_access_off_goal" in hits
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

### Tool classifier tests

```python
from agentwall.core.types import ToolType
from agentwall.utils.classifier import classify_tool

def test_filesystem_classification():
    assert classify_tool("read_file", "") == ToolType.FILESYSTEM
    assert classify_tool("write_file", "") == ToolType.FILESYSTEM

def test_general_fallback():
    assert classify_tool("do_thing", "does a thing") == ToolType.GENERAL
```

### Keyring tests

Keyring tests use in-memory mock backends via `keyring.set_keyring()`. See `tests/test_provider_keyring.py` for pattern.

### LLM provider tests

Provider tests mock the SDK client to avoid real API calls. See `tests/test_providers.py`.

---

## Auto-Instrumentation Tests

`tests/test_auto_instrumentation.py` covers the zero-config module behavior:

- `test_wrap_langchain_tool_idempotent` — wrapping same tool twice skips second wrap
- `test_wrap_crewai_tool_idempotent` — same for CrewAI
- `test_auto_setup_disabled_by_env` — `AGENTWALL_AUTO=0` disables setup
- `test_goal_tracker_infer_initial_goal` — sets goal once, ignores second call
- `test_goal_tracker_detect_transition` — returns True for significantly different goals
- `test_goal_tracker_create_goal_segment` — creates segment with confidence
- `test_goal_tracker_infer_runtime_goal_no_drift` — no change for on-goal events
- `test_goal_tracker_infer_runtime_goal_credential_drift` — creates new segment on drift signal

---

## Platform Notes

### Windows

`pytest`'s built-in `tmp_path` fixture fails on some Windows configurations with `PermissionError: [WinError 5]`. All AgentWall tests use `tempfile.mkdtemp()` instead. Do not use `tmp_path` in new tests.

### asyncio

Tests using `async def` require `@pytest.mark.asyncio`. `asyncio_mode = "strict"` is set in `pyproject.toml`. This means all async tests must be explicitly marked.

### Auto-Mode Isolation

`conftest.py` sets `os.environ["AGENTWALL_AUTO"] = "0"` before importing any agentwall module. This prevents the zero-config auto-instrumentation from patching framework internals during tests, which would cause `_aw_wrapped` idempotency checks to skip wrapping in explicit `protect_*` integration tests.

If you write tests that specifically test auto-mode behavior, use `monkeypatch.delenv("AGENTWALL_AUTO")` and reload the module in your test.

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
- Auto-instrumentation disabled via `AGENTWALL_AUTO=0` in conftest

Integration tests require the framework packages (`openai-agents`, `langchain-core`, `crewai`). Install with:

```bash
pip install agentwall-security[dev,integrations]
```
