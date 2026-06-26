# Changelog

All notable changes to AgentWall are documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

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
