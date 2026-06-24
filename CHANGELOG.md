# Changelog

All notable changes to AgentWall are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html)

---

## [0.1.0] — 2026-06-24

Initial release.

### Added

**Core runtime security**
- `SecurityEngine` with 5-stage evaluation pipeline: detectors → rules → policy → threshold → LLM
- `SensitiveResourceDetector`: credential file pattern matching
- `ScopeExpansionDetector`: cross-session resource drift detection
- `DataExfiltrationDetector`: external upload pattern detection
- Rule engine with per-tool-type risk scoring and resource category bonuses
- Policy engine: user-defined allow/warn/block rules with JSON conditions
- `ProviderChain`: multi-provider LLM evaluation with fallback
- `build_default_engine(db)`: auto-constructs engine from DB config (thresholds + provider chain)

**Providers**
- OpenAI (gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo)
- Anthropic (claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5)
- Groq (llama-3.3-70b-versatile, llama-3.1-8b-instant, gemma2-9b-it)
- DeepSeek (deepseek-chat, deepseek-reasoner)
- Ollama (local inference, no API key)

**Framework integrations**
- OpenAI Agents SDK: `protect_openai_agent()` with `InputGuardrail` goal inference
- LangChain: `protect_langchain_agent()` with `executor.invoke()` goal inference; async tool interception via `coroutine` patching
- CrewAI: `protect_crewai_crew()` with `crew.kickoff()` goal inference

**Interceptors**
- `ProtectedAgent`: session lifecycle management, tool wrapping, goal tracking
- `ToolInterceptor`: pre-execution evaluation, DB recording, post-execution analysis
- `protect_agent()`: top-level SDK entry point, optional goal
- `protect_tool()`: standalone tool wrapping

**Post-execution analysis**
- `ResultAnalyzer` in `agentwall/security/result_analyzer.py`
- Analyzes tool output after execution: filesystem (credential content), database (bulk rows, sensitive columns), API (confirmed transfers), email (dispatch events), terminal (credential output)
- Classifications: `NORMAL`, `SENSITIVE_DATA_EXPOSURE`, `BULK_DATA_ACCESS`, `EXTERNAL_TRANSFER`, `EMAIL_DISPATCH`
- Persists `post_execution_risk`, `result_classification`, `result_detector_hits`, `result_metadata` to evaluation row
- Storage rules enforced: no content stored — hashes, counts, type info only
- Pre-execution decision remains authoritative; post-execution NEVER retroactively blocks

**Dynamic goal tracking**
- `GoalTracker` in `agentwall/security/goal_tracker.py`
- Session goal segments: create, transition, close
- Transition detection via token-overlap heuristic (threshold 0.4)
- `ProtectedAgent.maybe_infer_goal()` replaces one-shot inference guard — enables multi-invoke transitions
- Framework inference patches updated to use `maybe_infer_goal()` on every invoke/kickoff
- Segments persist: goal text, started_at, ended_at, transition_reason
- SecurityEngine always evaluates against current active goal (via shared `_goal_ref`)

**Goal inference**
- Optional `goal` parameter in all `protect_*` functions
- Automatic inference from framework execution entry points
- Mutable `_goal_ref` shared across all wrapped tool closures

**Storage**
- SQLite at `~/.agentwall/data.db`
- Tables: `sessions`, `tool_events`, `evaluations`, `policies`, `provider_settings`, `goal_segments`
- WAL mode, foreign keys enabled

**Inspector**
- FastAPI backend with 9 router groups (added goals router)
- Built React UI (5 pages: Overview, Sessions, Timeline, Providers, Policies)
- PyWebView desktop window (`agentwall inspect`)
- Browser fallback (`agentwall inspect --browser`)
- Event-driven WebSocket push (in-process pub/sub via `EventBus`; replaces 1.5s SQLite poll)
- 30s keepalive ping on idle WS connections
- `GET /api/sessions/{id}/goals` — goal segment timeline
- `PATCH /api/policies/{name}/priority` — update policy priority
- `EvaluationSchema` extended with post-execution fields

**Policy engine**
- `priority` field on policies: higher priority evaluated first, creation-order tiebreak
- `PolicyEngine.set_priority(name, priority)` — runtime priority updates
- `PolicyEngine.create(name, config, priority=0)` — priority at creation time

**GoalTracker hardening**
- Thread-safe `set_goal()` and `maybe_infer()` via `threading.RLock`
- Two-signal transition heuristic: full token overlap AND resource token overlap (strips action verbs and stop words) — prevents pure verb changes ("Build X" → "Write X") from triggering new segments while catching true goal shifts ("Build login API" → "Create billing service")

**LLM response parsing**
- `parse_llm_response` handles nested JSON (`{"decision": {"type": "block", "risk": 90}}`)
- Strips markdown fences (` ```json ` blocks) before parsing
- Balanced-brace extraction handles arbitrarily nested JSON objects
- Fallback chain: stripped text → original text → BLOCK decision

**CLI**
- `agentwall version`
- `agentwall doctor`
- `agentwall config` (interactive wizard + flag mode)
- `agentwall inspect`

**Security**
- API keys in OS keyring only (Windows Credential Manager / macOS Keychain / Linux Secret Service)
- No secrets in SQLite, JSON, YAML, logs, or source

**EvalContext history**
- LLM evaluation receives recent tool history (up to 5 prior events) for contextual analysis

---

## Unreleased

### Known gaps for v0.2.0
- Async LangChain tool `ainvoke` full coverage (coroutine patching works; ainvoke path tested)
- Per-account DB path via environment variable
- Graceful inspector shutdown
- Test coverage reporting
- LLM-assisted goal transition disambiguation (current heuristic: token overlap only)
