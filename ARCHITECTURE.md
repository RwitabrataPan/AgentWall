# AgentWall Architecture

This document describes the implemented architecture of AgentWall v0.2.5.

---

## Overview

```
User Goal (explicit or inferred)
  └─ Auto Instrumentation Layer (agentwall.auto)
  │      OR
  └─ protect_*(agent, goal=..., db=None, engine=None)
         │
         ├─ ProtectedAgent (session lifecycle, goal tracking)
         │       └─ ToolInterceptor (per-call interception)
         │               └─ SecurityEngine (evaluation pipeline)
         │                       ├─ Detectors (incl. GoalDriftDetector)
         │                       ├─ Rule Engine
         │                       ├─ Policy Engine
         │                       └─ ProviderChain (LLM, optional)
         │
         └─ EventManager → SQLite (~/.agentwall/data.db)
```

---

## Auto Instrumentation Layer

`agentwall/auto.py`. Activated by `import agentwall` unless `AGENTWALL_AUTO=0`.

### LangChain Patching

Patches `AgentExecutor.__init__`. When any `AgentExecutor` is created:
1. Calls `protect_langchain_agent(self, db=..., engine=...)` to wrap all tools
2. Sets `self._aw_auto_protected = True` (idempotency guard)
3. Registers `weakref.finalize(executor, wall.end_session)` for automatic session cleanup
4. Registers `atexit` handler as fallback

### CrewAI Patching

Patches `Crew.__init__`. Same pattern as LangChain.

### OpenAI Agents SDK Patching

Patches `Runner.run` classmethod. Each `Runner.run()` invocation:
1. Creates a new `(wall, protected_agent)` pair for the run
2. Infers goal from the input string
3. Runs the original `Runner.run(protected, input, **kwargs)`
4. Calls `wall.end_session()` in `finally`

One session per `Runner.run()` call (OpenAI's per-run model, not per-agent).

### Idempotency

Tools marked with `_aw_wrapped = True` on the wrapped function (LangChain/CrewAI). Already-wrapped tools are skipped. Prevents double-interception when explicit `protect_*` is also called.

### Session Lifecycle

- `weakref.finalize(agent_obj, wall.end_session)` — closes session when agent object is garbage collected
- `atexit.register(...)` — closes all open sessions on process exit

---

## Entry Points

### `protect_agent(agent, *, goal=None, db=None, engine=None)`

Defined in `agentwall/interceptors/__init__.py`. Thin wrapper over `ProtectedAgent`.

### `protect_openai_agent(agent, *, goal=None, ...)`

Defined in `agentwall/integrations/openai_agents.py`. Returns `(wall, protected_agent)`. Wraps `FunctionTool.on_invoke_tool`. Injects `InputGuardrail` for goal inference when `goal` is omitted. Auto-classifies tools when `tool_type_map` is omitted.

### `protect_langchain_agent(executor, *, goal=None, ...)`

Defined in `agentwall/integrations/langchain.py`. Patches `tool.func` (sync tools) or `tool.coroutine` (async tools) in-place. Patches `executor.invoke` for goal inference. Auto-classifies tools when `tool_type_map` is omitted.

### `protect_crewai_crew(crew, *, goal=None, ...)`

Defined in `agentwall/integrations/crewai.py`. Patches `tool.func` for all tools on all agents. Patches `crew.kickoff` for goal inference. Auto-classifies tools when `tool_type_map` is omitted.

---

## Automatic Tool Classification

`agentwall/utils/classifier.py`. Called by all `protect_*` functions when `tool_type_map` is omitted.

```python
classify_tool(name: str, doc: str = "") -> ToolType
```

**Algorithm:** Word-level scoring. Split name on `_` and spaces. Name-word matches score 3×; docstring-word matches score 1×. Sum scores per `ToolType` pattern set. Return highest-scoring type, or `ToolType.GENERAL` if all scores are zero.

**Pattern sets:**

| ToolType | Keywords (sample) |
|----------|------------------|
| FILESYSTEM | file, directory, path, read_file, write_file |
| TERMINAL | run, exec, shell, bash, command |
| BROWSER | browse, web, url, scrape, navigate |
| DATABASE | sql, database, query, queries |
| EMAIL | email, mail, smtp, send_email |
| API | api, http, request, endpoint, webhook |
| GENERAL | (fallback — no keyword match) |

---

## Engine Construction

`build_default_engine(db)` in `agentwall/security/engine.py`:

```python
thresholds = ConfigManager(db).get_thresholds()   # from DB, fallback 30/70
chain = ProviderRegistry(db).load_chain()          # raises ValueError if no providers
engine = SecurityEngine(
    warn_threshold=thresholds["low_threshold"],
    block_threshold=thresholds["high_threshold"],
    provider_chain=chain,
    policy_engine=PolicyEngine(db),
)
```

Called automatically when `engine=None` is passed to any `protect_*` function.

---

## Interception Flow

```
tool.func(*args, **kwargs) called by agent
    │
    ├─ RuntimeEvent constructed (session_id, goal, tool_type, action, target, metadata)
    │
    ├─ ToolInterceptor.before_execute(event)
    │       ├─ EventManager.record(event) → INSERT tool_events
    │       ├─ _event_id_map[id(event)] = db_event.id   ← links event to after_execute
    │       ├─ _fetch_history(session_id, limit=20) → SELECT tool_events
    │       ├─ SecurityEngine.evaluate(event, history) → Decision
    │       ├─ EventManager.record_evaluation(event_id, decision) → INSERT evaluations
    │       └─ if BLOCK → raise AgentWallSecurityException
    │
    ├─ original_func(*args, **kwargs)   ← only if not blocked
    │
    └─ ToolInterceptor.after_execute(event, result)
            ├─ event_id = _event_id_map.pop(id(event))
            ├─ ResultAnalyzer.analyze(event, result) → AnalysisResult
            └─ EventManager.update_evaluation_post(event_id, analysis) → UPDATE evaluations
```

`_event_id_map` keyed by `id(runtime_event)` — unique per object, safe for sequential calls.

---

## Evaluation Pipeline

### Stage 1: Detectors

All detectors live in `agentwall/security/detectors.py`. Each returns `list[str]` hit labels. Each unique hit adds `10.0` to the risk score.

**SensitiveResourceDetector**
- Matches `event.target` against credential file patterns (`.ssh/`, `.env`, `id_rsa`, `credentials`, etc.)
- No history required.

**ScopeExpansionDetector**
- Requires ≥ 3 prior events.
- Hits `new_tool_type_introduced` when `event.tool_type` not seen in prior history.
- Hits `privilege_escalation` when `event.resource_category` is CREDENTIALS or SYSTEM and no prior event accessed those categories.
- At ≥ 5 prior events: hits `unrelated_resource_access` when a single tool_type dominates history at ≥ 70% share and the current event uses a different tool_type.

**DataExfiltrationDetector**
- Matches against external upload/send patterns (FTP, S3, SMTP, webhook, exfil keywords).
- No history required.

**GoalDriftDetector** *(v0.2.0)*
- Compares tool action characteristics against the current goal text. Returns empty list when goal is empty.
- `goal_drift:credential_access_off_goal` — `resource_category == CREDENTIALS` AND goal contains code-work keywords AND goal has no credential/auth/secret/key/token keywords.
- `goal_drift:sensitive_target_off_goal` — target matches `_CRED_TARGETS` patterns AND goal contains code-work keywords AND `resource_category != CREDENTIALS` (prevents double-hit with above).
- `goal_drift:unexpected_email` — `tool_type == EMAIL` AND `action == SEND` AND goal has no email/send/notify/report/upload/export keywords.
- `goal_drift:system_access_off_goal` — `resource_category == SYSTEM` AND goal contains code-work keywords AND goal has no system/config/setup/install/deploy keywords.

### Stage 2: Rule Engine

`agentwall/security/rules.py`. Computes a `float` risk score from `RuntimeEvent`.

Base risk by `(tool_type, action)` from `_RULE_MAP`. Category bonus from `_category_bonus(resource_category)`. Total risk += unique detector hits × 10.0, clamped to 100.0.

High-risk combinations (examples): TERMINAL.EXECUTE = 55.0, FILESYSTEM.DELETE on CREDENTIALS = 55+20=75.0, EMAIL.SEND = 50.0. GENERAL type = 10.0 base.

### Stage 3: Policy Engine

`agentwall/security/policy_engine.py`. Evaluates user-defined `Policy` objects from the DB.

Policies evaluated in **descending `priority` order** (higher priority first). Within the same priority, creation order (ascending) is used. First matching rule within each policy wins. Short-circuits stages 4 and 5.

Rule conditions (all optional, ANDed): `tool_type`, `action`, `target_pattern` (glob), `resource_category`, `risk_above`.

### Stage 4: Threshold Routing

```
risk < warn_threshold  → Decision(ALLOW, risk, "low risk")
risk < block_threshold → Decision(WARN,  risk, "elevated risk")
risk ≥ block_threshold → escalate to Stage 5
```

### Stage 5: LLM Evaluation

Only when `SecurityEngine._chain is not None`.

`EvalContext` built with:
- `user_goal`: `event.goal`
- `tool_call`: `ToolCall(name, arguments, session_id)`
- `recent_history`: last N events from `history` converted to `ToolCall` objects

`ProviderChain.evaluate(ctx)` tries evaluators in priority order. Each evaluator calls `build_prompt(ctx)` and parses the JSON response (`decision`, `reason`, `alignment_score`).

If all evaluators fail: `Decision(BLOCK, 100.0, "All providers failed")`.

If no chain: `Decision(BLOCK, risk, "high risk — no LLM evaluator configured")`.

---

## Goal Inference

### Mechanism

`_goal_ref: list[str]` — single-element mutable list shared by all tool closures. Closures read `_ref[0]` at call time.

When goal is inferred:
1. `wall.set_goal(inferred)` called
2. `_goal_ref[0] = inferred`
3. `SessionManager.update_goal(session_id, inferred)` → DB update

All already-wrapped tools see the update on next call.

### Per Framework

**OpenAI Agents SDK**: `InputGuardrail` injected into `agent.input_guardrails`. Fires before first LLM call. Receives raw `Runner.run()` input string. Calls `wall.maybe_infer_goal(text)`.

**LangChain**: `executor.invoke` patched. Extracts from `input`, `query`, `task` keys or first dict value. Calls `wall.maybe_infer_goal(inferred)`.

**CrewAI**: `crew.kickoff` patched. Extracts from `inputs` dict first value. Falls back to `tasks[0].description`. Calls `wall.maybe_infer_goal(inferred)`.

### GoalTracker v2

`agentwall/security/goal_tracker.py`. Owned by `ProtectedAgent`.

**New in v0.2.0:**

`infer_initial_goal(text, confidence=0.9)` — sets goal if empty. Does not override an existing goal. Returns `True` if goal was set.

`infer_runtime_goal(event)` — post-execution hook. Runs `GoalDriftDetector` on the event. If drift signals found, synthesizes a human-readable candidate goal description and opens a new goal segment with `confidence=0.7` and `reason="runtime_inference"`. Returns `True` if goal changed.

`detect_transition(new_goal)` — public wrapper for the two-signal heuristic.

`detect_goal_drift(event)` — public wrapper for `GoalDriftDetector.detect()`.

`create_goal_segment(goal, reason, confidence)` — explicit segment creation API.

**Confidence values:**

| Source | Confidence |
|--------|-----------|
| Explicit `goal="..."` | 1.0 |
| Inferred from first input (`maybe_infer` / `infer_initial_goal`) | 0.9 |
| Heuristic transition (`maybe_infer` on later inputs) | 0.8 |
| Runtime inference from drift signals (`infer_runtime_goal`) | 0.7 |

**Transition heuristic** (`_is_transition`) — two-signal, no LLM:
```
full_overlap  = |tokens(A) ∩ tokens(B)| / max(|A|, |B|)
resource_A    = tokens(A) − action_verbs − stop_words
resource_B    = tokens(B) − action_verbs − stop_words
res_overlap   = |resource_A ∩ resource_B| / max(|resource_A|, |resource_B|)
transition    = full_overlap < 0.4 AND res_overlap < 0.4
```

Thread-safe: `set_goal()` and `maybe_infer()` hold `threading.RLock`.

---

## Provider Architecture

### BaseEvaluator

`agentwall/providers/base.py`. Abstract class with:
- `evaluate(ctx: EvalContext) -> Decision`
- `health_check() -> ProviderStatus`
- `build_prompt(ctx) -> str` (shared)
- `parse_llm_response(text, fallback_score) -> Decision` (shared) — handles flat JSON, nested `{"decision": {"type": "block"}}`, markdown fences, and JSON embedded in prose via balanced-brace extraction

### Evaluators

| Class | SDK | Key source |
|-------|-----|-----------|
| `OpenAIEvaluator` | `openai.OpenAI` | OS keyring |
| `AnthropicEvaluator` | `anthropic.Anthropic` | OS keyring |
| `GroqEvaluator` | `openai.OpenAI(base_url=groq)` | OS keyring |
| `DeepSeekEvaluator` | `openai.OpenAI(base_url=deepseek)` | OS keyring |
| `OllamaEvaluator` | `httpx.post` | None |

### ProviderChain

`agentwall/providers/chain.py`. Tries evaluators in `priority` order. On exception, continues to next. Returns failure decision if all raise.

### ProviderRegistry

`agentwall/providers/registry.py`. Reads `ProviderSetting` rows from DB ordered by priority. Instantiates evaluators with keys from OS keyring. Returns `ProviderChain`. Raises `ValueError` if no providers configured.

---

## Storage Architecture

SQLite at `~/.agentwall/data.db`. WAL journal mode. Foreign keys enabled.

### Schema

```sql
sessions (id TEXT PK, user_goal TEXT, created_at REAL, ended_at REAL, meta JSON)

tool_events (
    id INTEGER PK AUTOINCREMENT,
    session_id TEXT FK sessions.id,
    tool_name TEXT, arguments JSON, timestamp REAL,
    tool_type TEXT, action TEXT, target TEXT, resource_category TEXT
)

evaluations (
    id INTEGER PK AUTOINCREMENT,
    event_id INTEGER FK tool_events.id,
    decision TEXT, risk_score REAL, reason TEXT,
    llm_used BOOL, alignment_score REAL,
    detector_hits JSON, policy_matched TEXT,
    -- post-execution analysis (populated by ResultAnalyzer via after_execute)
    post_execution_risk REAL,
    result_classification TEXT,
    result_detector_hits JSON,
    result_metadata JSON
)

goal_segments (
    id TEXT PK,                          -- UUID
    session_id TEXT FK sessions.id,
    goal_text TEXT,
    started_at REAL,
    ended_at REAL,                       -- NULL while active
    transition_reason TEXT,              -- "initial" | "user_update" | "inference" |
                                         --   "heuristic_transition" | "runtime_inference"
    confidence REAL DEFAULT 1.0          -- added in v0.2.0
)

policies (id INTEGER PK AUTOINCREMENT, name TEXT UNIQUE, enabled BOOL, config JSON, created_at REAL, priority INTEGER DEFAULT 0)

provider_settings (provider TEXT PK, model TEXT, priority INTEGER, enabled BOOL, config JSON)
```

`policies` table also stores `thresholds` as a special row (name=`"thresholds"`, config=`{low_threshold, high_threshold}`).

New columns are added via `ALTER TABLE` migrations in `Database._migrate()`. `goal_segments.confidence` added via migration in v0.2.0.

---

## Inspector Architecture

### Launch Flow

```
agentwall inspect
  → launch_desktop(host, port)
      ├─ daemon thread: _run_server_thread() → uvicorn + FastAPI
      ├─ _wait_for_server() → poll /api/health up to 15s
      └─ webview.start() → blocks until window closed
```

`--browser` flag: skip PyWebView, use `webbrowser.open()`.

### Backend

FastAPI app in `agentwall/inspector/server.py`. `StaticFiles` mounted at `/` from `agentwall/inspector/ui/dist/` when present.

Routers: sessions, events, goals, evaluations, policies, providers, config, health, WebSocket.

`GET /api/sessions/{session_id}/goals` — returns list of `GoalSegmentSchema` ordered by `started_at`. Includes `confidence` field on each segment.

`EvaluationSchema` in `agentwall/models/schemas.py` includes post-execution fields: `post_execution_risk`, `result_classification`, `result_detector_hits`, `result_metadata`.

### Frontend

Built React app at `agentwall/inspector/ui/dist/`.

5 pages: Overview, Sessions, Timeline, Providers, Policies.

The Timeline page displays goal segments including confidence scores and transition reasons.

### Real-time Updates

`/ws/events` WebSocket: **event-driven push** via in-process `EventBus` (`agentwall/inspector/event_bus.py`).

```
tool call recorded (ToolInterceptor.before_execute)
    → EventBus.publish()                   # thread-safe, call_soon_threadsafe
    → asyncio queue per WS subscriber
    → ws_events() sends {"type": "refresh"}
    → UI re-fetches sessions/events

after_execute (ResultAnalyzer result)
    → EventBus.publish()                   # second push for post-execution fields
```

No SQLite polling. No external infrastructure. `EventBus` is a no-op when no WS clients are connected or when Inspector is not running (SDK-only mode). Idle connections receive `{"type": "ping"}` every 30s.

---

## Framework Integration Architecture

### OpenAI Agents SDK

`FunctionTool` is an immutable dataclass. AgentWall uses `dataclasses.replace(ft, on_invoke_tool=_wrapped)` to create a new tool. All wrapped tools collected into a new `Agent` via `dataclasses.replace(agent, tools=wrapped_tools)`. Original agent unchanged.

Auto-classification: when `tool_type_map` is omitted, `classify_tool(ft.name, ft.description)` determines `ToolType` for each function tool.

### LangChain

`StructuredTool` is mutable. AgentWall patches `tool.func` (sync tools) or `tool.coroutine` (async tools) in-place. `executor.tools` list is not replaced — the tool objects themselves are mutated.

Idempotency: `_aw_wrapped = True` is set on the wrapped function. `wrap_langchain_tool` skips tools where `getattr(tool.func, "_aw_wrapped", False)` is True.

Auto-classification: when `tool_type_map` is omitted, `classify_tool(tool.name, tool.description)` determines `ToolType`.

### CrewAI

`BaseTool` subclass is mutable. AgentWall patches `tool.func` in-place. Both `run()` (sync) and `arun()` (async) dispatch via `self.func` in the concrete `Tool` class.

Idempotency: same `_aw_wrapped` marker as LangChain.

Auto-classification: when `tool_type_map` is omitted, `classify_tool(tool.name, tool.description)` determines `ToolType`.
