# Changelog

All notable changes to AgentWall are documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

---

## [0.1.0] - 2026-06-24

Initial public release.

### Added

#### Core Runtime Security

- SecurityEngine with 5-stage evaluation pipeline:
  - Detectors
  - Rules
  - Policy
  - Threshold
  - LLM evaluation
- SensitiveResourceDetector for credential and secret file pattern matching.
- ScopeExpansionDetector for cross-session resource drift detection.
- DataExfiltrationDetector for external upload pattern detection.
- Rule engine with:
  - Per-tool-type risk scoring
  - Resource category risk bonuses
- Policy engine with user-defined allow, warn, and block rules using JSON conditions.
- ProviderChain with multi-provider LLM evaluation and automatic fallback.
- `build_default_engine(db)` helper for automatic engine construction from database configuration.

#### LLM Providers

##### OpenAI

- gpt-4o
- gpt-4o-mini
- gpt-4-turbo
- gpt-3.5-turbo

##### Anthropic

- claude-opus-4-8
- claude-sonnet-4-6
- claude-haiku-4-5

##### Groq

- llama-3.3-70b-versatile
- llama-3.1-8b-instant
- gemma2-9b-it

##### DeepSeek

- deepseek-chat
- deepseek-reasoner

##### Ollama

- Local inference support without API keys.

#### Framework Integrations

##### OpenAI Agents SDK

- `protect_openai_agent()`
- InputGuardrail goal inference support.

##### LangChain

- `protect_langchain_agent()`
- Goal inference via `executor.invoke()`.
- Async tool interception through coroutine patching.

##### CrewAI

- `protect_crewai_crew()`
- Goal inference via `crew.kickoff()`.

#### Agent & Tool Interceptors

- `ProtectedAgent`
  - Session lifecycle management
  - Tool wrapping
  - Goal tracking
- `ToolInterceptor`
  - Pre-execution evaluation
  - Database recording
  - Post-execution analysis
- `protect_agent()`
  - Top-level SDK entry point
  - Optional explicit goal support
- `protect_tool()`
  - Standalone tool protection

#### Post-Execution Analysis

- ResultAnalyzer (`agentwall/security/result_analyzer.py`)
- Tool output analysis for:
  - Filesystem activity
  - Database queries
  - API calls
  - Email operations
  - Terminal output
- Result classifications:
  - `NORMAL`
  - `SENSITIVE_DATA_EXPOSURE`
  - `BULK_DATA_ACCESS`
  - `EXTERNAL_TRANSFER`
  - `EMAIL_DISPATCH`
- Evaluation persistence:
  - `post_execution_risk`
  - `result_classification`
  - `result_detector_hits`
  - `result_metadata`
- Storage rules:
  - No sensitive content stored
  - Hashes, counts, and metadata only
- Pre-execution decisions remain authoritative.
- Post-execution analysis never retroactively blocks execution.

#### Dynamic Goal Tracking

- GoalTracker (`agentwall/security/goal_tracker.py`)
- Goal segment lifecycle:
  - Create
  - Transition
  - Close
- Dynamic goal transition detection.
- Shared mutable `_goal_ref` used across wrapped tools.
- Goal segments persist:
  - Goal text
  - Start time
  - End time
  - Transition reason
- Security evaluations always reference the currently active goal.

##### Goal Transition Improvements

- Thread-safe goal updates using `threading.RLock`.
- Two-signal transition heuristic:
  - Token overlap analysis
  - Resource token overlap analysis
- Prevents false transitions caused only by wording changes.
- Detects genuine goal shifts involving different resources or objectives.

#### Goal Inference

- Optional goal parameter supported by all `protect_*()` APIs.
- Automatic goal inference from framework execution entry points.
- Continuous inference through:
  - `ProtectedAgent.maybe_infer_goal()`
  - LangChain integrations
  - CrewAI integrations
- Replaces one-shot goal inference behavior.

#### Storage

- SQLite database at:

  `~/.agentwall/data.db`

- Tables:
  - `sessions`
  - `tool_events`
  - `evaluations`
  - `policies`
  - `provider_settings`
  - `goal_segments`
- WAL mode enabled.
- Foreign key enforcement enabled.

#### Inspector

##### Backend

- FastAPI backend with 9 router groups.
- Goals router included.
- Event-driven WebSocket updates via EventBus.
- Replaces SQLite polling architecture.
- 30-second keepalive ping support.

Endpoints:

- `GET /api/sessions/{id}/goals`
- `PATCH /api/policies/{name}/priority`

##### Frontend

Built React-based inspector UI with:

- Overview
- Sessions
- Timeline
- Providers
- Policies

##### Desktop Support

- PyWebView desktop application.
- Browser mode:

  `agentwall inspect --browser`

##### Schema Updates

- EvaluationSchema extended with post-execution analysis fields.

#### Policy Engine

- Policy priority support.
- Higher priority policies evaluated first.
- Creation order used as tiebreaker.

APIs:

- `PolicyEngine.create(name, config, priority=0)`
- `PolicyEngine.set_priority(name, priority)`

Runtime priority updates supported.

#### LLM Response Parsing

- Handles nested JSON responses.
- Supports structures such as:

  ```json
  {
    "decision": {
      "type": "block",
      "risk": 90
    }
  }
  ```

- Markdown code fences automatically stripped.
- Balanced-brace extraction for deeply nested JSON.
- Fallback sequence:
  1. Stripped text
  2. Original text
  3. Safe BLOCK decision

#### Evaluation Context History

- LLM evaluations receive recent tool execution history.
- Up to 5 previous tool events included for contextual analysis.

#### Command Line Interface

Commands:

- `agentwall version`
- `agentwall doctor`
- `agentwall config`
  - Interactive wizard
  - Flag-based configuration mode
- `agentwall inspect`

#### Security

- API keys stored exclusively in OS keyrings:
  - Windows Credential Manager
  - macOS Keychain
  - Linux Secret Service
- No secrets stored in:
  - SQLite databases
  - JSON files
  - YAML files
  - Logs
  - Source code

---

## Unreleased

### Planned for v0.2.0

#### Improvements

- Full async LangChain `ainvoke()` coverage.
- Per-account database path configuration via environment variables.
- Graceful inspector shutdown.
- Built-in test coverage reporting.
- LLM-assisted goal transition disambiguation.

#### Current Limitation

- Goal transition detection currently relies on heuristic overlap analysis rather than LLM-based reasoning.