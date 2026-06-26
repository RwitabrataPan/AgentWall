# Changelog

All notable changes to AgentWall are documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

---

## [0.2.5] - 2026-06-26

### Fixed

- **Inspector Executions page shows executions from all projects**: `GET /api/executions`
  previously called `list_all()` with no project filter, mixing executions from every
  project in the shared database. It now calls `list_for_project(current_project_id)`
  using the same project-detection logic as `GET /api/overview`. Each Inspector instance
  now shows only the executions belonging to the project it was launched from.

- **Overview page never refreshes for cross-process agents**: `OverviewPage` relied
  exclusively on WebSocket `refresh` messages to trigger re-fetches. The WebSocket
  notification path (`EventBus.publish()`) is in-process only — agents running in a
  separate terminal cannot notify the Inspector's EventBus. `OverviewPage` now polls
  `GET /api/overview` every 5 seconds as a fallback, matching the existing polling
  behaviour of `ExecutionsPage`. Active Executions and Total Executions now update
  within 5 seconds of any agent event regardless of whether the agent shares the
  Inspector's process.

- **WebSocket connection not recovered after drop**: `connectEventStream` had no
  reconnect logic. If the WebSocket closed for any reason, `refreshTick` stopped
  incrementing permanently, disabling real-time updates for same-process agents.
  The function now reconnects automatically after a 3-second delay.

### Tests

- Replaced `test_list_executions_returns_all_projects` (verified wrong all-project
  behaviour) with `test_list_executions_filters_by_current_project` and
  `test_list_executions_excludes_other_projects`, which confirm project isolation at
  the API layer.
- Removed `test_executions_visible_regardless_of_inspector_cwd` and
  `test_execution_appears_regardless_of_cwd` — both verified the old cross-project
  visibility behaviour that is now intentionally absent.
- Updated `test_list_executions_newest_first` to patch
  `agentwall.core.execution_manager.detect_project_root` so the test project matches
  what the route resolves.

---

## [0.2.4] - 2026-06-26

### Fixed

- **Executions page not updating after agent run**: `ProtectedAgent.__init__` now
  publishes a refresh event via `EventBus` immediately after creating the execution
  and session. When the agent and Inspector share the same process, the Executions
  page updates in real time. `ExecutionManager.finish()` also publishes a refresh
  event so the Inspector reflects the completed status immediately.

- **Executions page stale for cross-process agents**: `ExecutionsPage` now polls
  `/api/executions` every 5 seconds in addition to responding to WebSocket refresh
  events. Executions created by agents running in separate terminals appear within
  5 seconds without any manual refresh.

- **Execution permanently stuck in "running" state after agent exits**: Three gaps
  in `ProtectedAgent` lifecycle were closed:
  - `end_session()` was not exception-safe — if `session_mgr.end()` raised a
    SQLAlchemy error, `finish()` was skipped and `self._closed` stayed `False`.
    Fix: set `self._closed = True` first (re-entry guard), then wrap each DB
    operation in its own `try/except` so `finish()` always runs.
  - Orphaned execution on `__init__` failure — `exec_mgr.create()` commits the
    `Execution` row before session creation and `GoalTracker.__init__`. If either
    raised, the committed row stayed `status="running"` with no owner to finalize
    it. Fix: wrap everything after `exec_mgr.create()` in `try/except`; call
    `finish(status="failed")` before re-raising.
  - `__exit__` always marked `"completed"` regardless of exception — the old
    signature `__exit__(self, *_)` discarded `exc_type`. Fix: correct three-argument
    signature, passes `status="failed"` when `exc_type is not None`.

### Added

- **Minimal demo script** (`examples/demo.py`): no API key required. Demonstrates
  the full execution lifecycle with protected tool calls. Run multiple times to
  build up history visible in the Inspector.

### Tests

- 5 regression tests in `test_interceptors.py`: `end_session()` idempotency,
  `finish()` called when `session_mgr.end()` raises, context manager marks
  `"failed"` on exception, context manager marks `"completed"` on success, and
  orphaned execution finalized `"failed"` when `__init__` raises after
  `exec_mgr.create()`.
- 2 regression tests in `test_inspector_routes.py`: finished execution reflected
  as `"completed"` via API, and execution visible regardless of working directory.
- 6 regression tests in `test_project_isolation.py`: default DB path, shared
  database between two `Database()` instances, 7-consecutive-run all-completed
  invariant, zero running executions after clean run, `EventBus.publish()` called
  by `finish()`, and newest-first ordering from `list_all()`.

---

## [0.2.3] - 2026-06-26

### Fixed

- **Executions page always empty**: `/api/executions` was filtering by the Inspector's
  working-directory project ID, which never matched executions created by agents running
  from a different directory. The endpoint now returns all executions across all projects,
  so the Executions page populates correctly regardless of where `agentwall inspect` is
  launched from.

- **Inspector process not exiting on window close**: Closing the PyWebView window set
  `uvicorn.server.should_exit = True` and joined the server thread, but non-daemon threads
  left by the WebView2 runtime (on Windows) blocked interpreter shutdown. Added `os._exit(0)`
  after the graceful-stop sequence so the terminal returns immediately with no Ctrl+C required.

### Tests

- Added `ExecutionManager` dependency override to `_client()` in the inspector route test
  fixture so execution-manager queries always hit the isolated test database.
- Added 7 regression tests for the executions API: empty list, cross-project visibility,
  newest-first ordering, single-execution fetch, 404 on missing ID, CWD-mismatch regression,
  and session linkage.
- Updated 2 existing desktop tests to mock `os._exit` so they survive the new shutdown path.
- Added `test_launch_desktop_exits_process_after_window_close` to verify `os._exit(0)` is
  called after the window closes.

---

## [0.2.2] - 2026-06-26

### Fixed

- **Project reuse bug**: `ExecutionManager.get_or_create_project()` now performs a true get-or-create.
  Previously, unresolved path variants of the same directory produced different hash IDs, causing
  every call to attempt a fresh INSERT and hit `UNIQUE constraint failed: projects.root`.
  The fix normalises the path with `.resolve()` before hashing, and catches `IntegrityError` to
  fall back to the existing row for concurrent callers — no `IntegrityError` is ever surfaced.

### Tests

- Added regression tests: path normalisation, no-duplicate-row invariant, concurrent get-or-create
  (8 threads), and IntegrityError fallback simulation.

---

## [0.2.1] - 2026-06-26

### Added

**Project Isolation**
- Automatic project detection from git root (falls back to CWD)
- Every session and execution is scoped to its project — projects never share history
- New `projects` and `executions` tables with automatic migration for existing databases
- `GET /api/project` endpoint returns current project (name, root, ID)

**Execution-Centric Inspector**
- New `Executions` page replaces Sessions as the primary view
- Each `invoke()`/`run()`/`kickoff()` call creates one Execution card
- Latest execution auto-expands; older executions collapse
- Execution cards show: goal, framework, model, duration, status, decision, threats
- Full execution details panel with collapsible Tool Calls and Security Evaluation sections
- `GET /api/executions` and `GET /api/executions/{id}` endpoints

**Policy Builder**
- Visual form builder with fields: Name, Description, Tool Type, Pattern, Decision, Reason
- Six built-in policy templates: Block SSH Keys, Protect .env Files, Protect AWS Credentials, Prevent Database Dumps, Prevent External Uploads, Warn Before Email
- JSON mode toggle for advanced editing
- Policy test sandbox: simulate evaluation against any tool/target before saving
- `GET /api/policies/templates` and `POST /api/policies/test` endpoints

**Inspector Improvements**
- Project name displayed in NavBar and Overview
- Overview shows: current project, active/total executions, avg risk, top detectors, top policies
- Execution details panel shows complete evaluation breakdown without requiring a tool call selection
- Graceful Inspector shutdown: closing the PyWebView window now stops uvicorn and returns the terminal immediately — no Ctrl+C required

### Changed

- `ProtectedAgent.__init__` accepts optional `framework` and `execution_id` parameters (backward compatible)
- `SessionManager.create` accepts optional `project_id` and `execution_id` (backward compatible)
- Overview API response extended with `project_id`, `project_name`, execution counts, `avg_risk`, `top_detectors`, `top_policies`

### Fixed

- Inspector window close leaving orphaned uvicorn process / blocked terminal

---

## [0.2.0] - 2026-06-26

### Added

**Zero-Configuration Mode**
- `import agentwall` now auto-instruments LangChain `AgentExecutor`, CrewAI `Crew`, and OpenAI Agents SDK `Runner` — no explicit `protect_*` calls required
- `agentwall.auto` module handles framework detection and patching at import time
- Auto session lifecycle: sessions end via `weakref.finalize` (GC) and `atexit` handler
- Disable with `AGENTWALL_AUTO=0` environment variable

**Automatic Tool Classification**
- `agentwall.utils.classifier.classify_tool(name, doc)` infers `ToolType` from function name and docstring
- Covers FILESYSTEM, TERMINAL, BROWSER, DATABASE, EMAIL, API with keyword matching
- Falls back to `ToolType.GENERAL` (new enum value) when classification is uncertain
- All `protect_*` functions now auto-classify tools when no `tool_type_map` is provided

**Goal Drift Detection**
- New `GoalDriftDetector` security detector — compares tool actions against stated goal text
- Detects: credential access off code goal, unexpected email, system access off goal, sensitive target patterns
- Added to default detector pipeline in `SecurityEngine`

**Continuous Goal Tracking (GoalTracker v2)**
- `infer_initial_goal(text, confidence)` — explicit initial goal setter
- `infer_runtime_goal(event)` — post-execution hook; synthesizes new goal from high-signal events
- `detect_transition(new_goal)` — public API for transition check
- `detect_goal_drift(event)` — public API returning drift signals
- `create_goal_segment(goal, reason, confidence)` — explicit segment creation
- `confidence` field added to `GoalSegment` model, DB, and API schema

**Schema & Storage**
- `GoalSegment.confidence` (REAL, default 1.0) added via migration
- `GoalSegmentSchema` exposes `confidence` field
- `EventManager.create_goal_segment` accepts `confidence` parameter

**Double-Wrap Prevention**
- `wrap_langchain_tool`, `wrap_crewai_tool`, `protect_tool` mark wrapped functions with `_aw_wrapped = True`
- Subsequent wrapping calls on already-wrapped tools are silently skipped

**New Top-Level Exports**
- `ToolType`, `ToolAction`, `ResourceCategory`, `AgentWallSecurityException` now importable from `agentwall` directly

### Changed
- `set_goal` / `maybe_infer` in `GoalTracker` now propagate `confidence` to DB
- All integrations auto-classify tool type when not in `tool_type_map`

### Known Limitations
- Async LangChain `ainvoke` tested via coroutine patching; direct `ainvoke` coverage is best-effort
- DB path is fixed at `~/.agentwall/data.db` — no per-account or env-var override yet
- Graceful inspector shutdown (closing the PyWebView window ends the process cleanly, but `Ctrl-C` may leave a zombie uvicorn thread)
- No built-in test coverage report; use `pytest --cov=agentwall`
- Goal transition heuristic is token-overlap only; LLM-assisted disambiguation is a future enhancement

---

## [0.1.2] - 2026-06-24

### Fixed

#### Version Management

- Fixed CLI version reporting.
- Package version now resolves from installed package metadata.
- Eliminated version mismatch between PyPI package metadata and CLI output.

#### Documentation

- Updated installation instructions to use:

```bash
pip install agentwall-security
```

- Clarified optional dependency installation.
- Improved Inspector documentation.
- Improved LLM evaluation documentation.
- Fixed README and installation guide inconsistencies.

#### Packaging

- Verified wheel and source distribution contents.
- Corrected package metadata consistency.
- Confirmed clean installation from PyPI in a fresh environment.

---

## [0.1.1] - 2026-06-24

### Fixed

#### Documentation

- Corrected installation guide formatting.
- Updated package installation examples.
- Improved framework integration examples.
- Fixed PyPI documentation rendering issues.

#### Release Hygiene

- Repository cleanup and packaging audit completed.
- Removed stale documentation references.
- Improved release readiness documentation.

---

## [0.1.0] - 2026-06-24

Initial public release.

### Added

#### Runtime Security Engine

- Multi-stage runtime security evaluation pipeline:
  - Detectors
  - Rules
  - Policies
  - Threshold evaluation
  - Optional LLM evaluation
- Sensitive Resource Detection
- Scope Expansion Detection
- Data Exfiltration Detection

#### Policy Engine

- User-defined allow, warn, and block policies.
- Runtime policy enforcement.
- Policy priority support.
- Dynamic policy updates.

#### Goal Tracking

- Dynamic goal tracking across agent sessions.
- Goal inference from framework entry points.
- Goal transition detection.
- Goal segmentation and persistence.

#### Post-Execution Analysis

- Tool output classification.
- Sensitive data exposure detection.
- Bulk data access detection.
- External transfer detection.
- Email dispatch detection.

#### Inspector

##### Backend

- FastAPI-powered Inspector API.
- Session management APIs.
- Event streaming support.
- Policy management APIs.
- Goal tracking APIs.

##### Frontend

- React-based Inspector UI.
- Session timeline visualization.
- Policy management interface.
- Provider management interface.
- Security event monitoring.

##### Desktop Support

- PyWebView desktop application.
- Browser mode support.

#### Framework Integrations

##### OpenAI Agents SDK

- Agent protection wrapper.
- Tool interception.
- Goal inference support.

##### LangChain

- AgentExecutor protection.
- Tool interception.
- Goal inference support.

##### CrewAI

- Crew protection wrapper.
- Tool interception.
- Goal inference support.

#### LLM Providers

##### OpenAI

- GPT-4o
- GPT-4o Mini
- GPT-4 Turbo
- GPT-3.5 Turbo

##### Anthropic

- Claude Opus
- Claude Sonnet
- Claude Haiku

##### Groq

- Llama models
- Gemma models

##### DeepSeek

- DeepSeek Chat
- DeepSeek Reasoner

##### Ollama

- Local inference support.

#### Storage

- SQLite-based local storage.
- Session tracking.
- Tool event tracking.
- Evaluation persistence.
- Goal persistence.
- Policy persistence.

#### Security

- OS keyring integration.
- No plaintext API key storage.
- Local-first architecture.
- Audit trail generation.

#### Command Line Interface

Commands:

```bash
agentwall version
agentwall doctor
agentwall config
agentwall inspect
```

---

## Unreleased

Nothing planned yet.
