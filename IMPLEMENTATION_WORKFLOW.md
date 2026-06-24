# AgentWall Implementation Workflow

> Architecture review document. Describes only what is implemented in the current codebase.
> Generated: 2026-06-24. Version: 0.1.0.

---

## File Tree Reference

```
agentwall/
├── __init__.py                          # Public API: protect_agent, protect_tool
├── cli/
│   └── main.py                          # CLI: version, doctor, config, inspect
├── core/
│   ├── config_manager.py               # Provider + threshold CRUD (DB-backed)
│   ├── event_manager.py                # ToolEvent + Evaluation CRUD
│   ├── session_manager.py              # Session CRUD
│   └── types.py                        # DecisionType, ToolType, ToolAction,
│                                        #   ResourceCategory, RuntimeEvent,
│                                        #   Decision, EvalContext, ToolCall
├── detectors/
│   └── __init__.py                     # (empty)
├── inspector/
│   ├── deps.py                         # FastAPI dependency injectors
│   ├── desktop.py                      # PyWebView launcher
│   ├── event_bus.py                    # In-process pub/sub for WS push (EventBus)
│   ├── server.py                       # FastAPI app assembly + lifespan
│   └── routes/
│       ├── events.py                   # GET /api/sessions/{id}/events
│       ├── export.py                   # GET /api/export
│       ├── goals.py                    # GET /api/sessions/{id}/goals
│       ├── health.py                   # GET /api/health
│       ├── overview.py                 # GET /api/overview
│       ├── policies.py                 # CRUD /api/policies + PATCH /{name}/priority
│       ├── providers.py                # CRUD /api/providers
│       ├── sessions.py                 # CRUD /api/sessions
│       └── ws.py                       # WS /ws/events (event-driven push)
├── integrations/
│   ├── crewai.py                       # protect_crewai_crew, wrap_crewai_tool
│   ├── langchain.py                    # protect_langchain_agent, wrap_langchain_tool
│   └── openai_agents.py               # protect_openai_agent, wrap_openai_function_tool
├── interceptors/
│   ├── __init__.py                     # protect_agent (generic, goal required)
│   ├── agent.py                        # ProtectedAgent
│   ├── base.py                         # BaseInterceptor (abstract)
│   └── tool.py                         # ToolInterceptor, protect_tool
├── models/
│   └── schemas.py                      # Pydantic response schemas
├── providers/
│   ├── anthropic.py                    # AnthropicEvaluator
│   ├── base.py                         # BaseEvaluator, build_prompt, parse_llm_response
│   ├── chain.py                        # ProviderChain (fallback chain)
│   ├── deepseek.py                     # DeepSeekEvaluator
│   ├── groq.py                         # GroqEvaluator
│   ├── keyring.py                      # get/store/delete_api_key (OS keyring)
│   ├── ollama.py                       # OllamaEvaluator
│   ├── openai.py                       # OpenAIEvaluator
│   └── registry.py                     # ProviderRegistry.load_chain()
├── security/
│   ├── detectors.py                    # 3 detectors: Sensitive, Scope, Exfil
│   ├── engine.py                       # SecurityEngine (5-stage pipeline)
│   ├── exceptions.py                   # AgentWallSecurityException
│   ├── goal_tracker.py                 # GoalTracker (goal segments, transition heuristics)
│   ├── policy_engine.py               # PolicyEngine (pattern matching)
│   ├── result_analyzer.py              # ResultAnalyzer (post-execution classification)
│   └── rules.py                        # compute_risk() per tool type
└── storage/
    ├── database.py                      # Database (SQLite, WAL, migrations)
    └── models.py                        # SQLAlchemy ORM: Session, ToolEvent,
                                         #   Evaluation, GoalSegment, Policy, ProviderSetting
```

---

## Section 1 — End-to-End Workflow

```
User Prompt
↓
Framework calls protect_* function at startup
  - ProtectedAgent created with _goal_ref = ["" or explicit goal]
  - Session row inserted in SQLite (user_goal = "" or explicit)
  - ToolInterceptor created with reference to SecurityEngine
  - Tools wrapped (tool.func patched in-place OR new FunctionTool created)
  - [OpenAI only, no explicit goal] InputGuardrail injected into agent.input_guardrails
↓
Agent Framework runs
↓
[OpenAI only, no explicit goal]
  InputGuardrail fires before first LLM call
    _extract_goal_text(runner_input) → plain string
    wall.set_goal(text)
      → _goal_ref[0] = text
      → SessionManager.update_goal(session_id, text) → UPDATE sessions SET user_goal=text
↓
[LangChain only, no explicit goal]
  executor.invoke({"input": "..."}) called
  _patched_invoke fires before original invoke
    extracts goal from input["input"] | input["query"] | input["task"] | first value
    wall.set_goal(inferred)
↓
[CrewAI only, no explicit goal]
  crew.kickoff(inputs={...}) called
  _patched_kickoff fires before original kickoff
    extracts from inputs dict first value OR crew.tasks[0].description
    wall.set_goal(inferred)
↓
Agent decides to call a tool
↓
Wrapped tool closure invoked
  RuntimeEvent constructed:
    session_id = wall.session_id
    goal       = _goal_ref[0]  ← read at call time, not at wrap time
    tool_type  = from tool_type_map or default ToolType.API
    action     = from action_map or _default_action(tool_type)
    target     = _extract_target(args, kwargs)
    resource_category = from resource_category_map or UNKNOWN
    metadata   = parsed args dict
    tool_name  = function/tool name
    timestamp  = time.time()
↓
ToolInterceptor.before_execute(event)
  ├── _fetch_history(session_id, limit=20)
  │     SELECT last 20 ToolEvent rows for session → reconstruct RuntimeEvent list
  ├── record_event(event)
  │     EventManager.record() → INSERT INTO tool_events
  ├── SecurityEngine.evaluate(event, history)
  │     [See Section 5 for detail]
  ├── EventManager.record_evaluation(event_id, decision)
  │     INSERT INTO evaluations
  └── if decision.type == BLOCK:
        raise AgentWallSecurityException(decision, event)
        → tool is NOT called
        → exception propagates to agent framework
↓
[if ALLOW or WARN]
Original tool function called with original args
↓
ToolInterceptor.after_execute(event, result)
  [no-op — result is not recorded or evaluated]
↓
Tool result returned to agent
↓
Decision: ALLOW | WARN | BLOCK
```

---

## Section 2 — Framework Integration Flow

### OpenAI Agents SDK

**File:** `agentwall/integrations/openai_agents.py`

**Entry point:** `protect_openai_agent(agent, *, goal=None, tool_type_map, action_map, resource_category_map, db, engine)`

**Returns:** `(wall: ProtectedAgent, protected_agent: Agent)`

**Interception point:** `FunctionTool.on_invoke_tool` — the async callable that the OpenAI Agents SDK runner invokes when the LLM requests a tool call.

**Wrapper:** `wrap_openai_function_tool(ft, ...)` — uses `dataclasses.replace(ft, on_invoke_tool=_wrapped)` to create a new `FunctionTool` object. The original agent is not mutated; `dataclasses.replace(agent, tools=wrapped_tools)` creates a new `Agent`.

**Goal extraction mechanism:**
- When `goal=None`: `_make_goal_inferrer(wall)` creates an `InputGuardrail` object with `name="agentwall_goal_inferrer"`.
- Injected via `dataclasses.replace(protected_agent, input_guardrails=[*existing, inferrer])`.
- Guardrail function `_infer(ctx, agent, input)` fires before first LLM call.
- `_extract_goal_text(input)`:
  - If `str`: returned directly.
  - If `list`: iterates items looking for `item["content"]` as str, or `input_text` block type.
  - Fallback: `str(input)[:200]`.
- Calls `wall.set_goal(text)` → updates `_goal_ref[0]` and DB.
- Returns `GuardrailFunctionOutput(output_info=None, tripwire_triggered=False)` — never blocks.

**Tool interception mechanism:**
```
Runner.run(protected_agent, user_input)
  → LLM selects tool
  → SDK calls protected_agent.tools[i].on_invoke_tool(ctx, args_json)
  → _wrapped(ctx, args_json)
      json.loads(args_json) → args_dict
      RuntimeEvent constructed
      ToolInterceptor.before_execute(event)
      await original(ctx, args_json)  ← original on_invoke_tool
      ToolInterceptor.after_execute(event, result)
```

**Non-FunctionTool tools** (e.g., hosted tools): passed through unwrapped to `wrapped_tools`.

**Execution flow:**
```
protect_openai_agent(agent, goal=None)
  → ProtectedAgent(_Stub(), goal=None)     [session created, goal=""]
  → wrap each FunctionTool                 [new FunctionTool objects]
  → dataclasses.replace(agent, tools=...)  [new Agent clone]
  → inject InputGuardrail                  [goal will be set on first Runner.run]
  → return (wall, protected_agent)

Runner.run(protected_agent, "fix login bug")
  → InputGuardrail fires → wall.goal = "fix login bug"
  → LLM call
  → tool call → _wrapped → before_execute → evaluate → record
```

---

### LangChain

**File:** `agentwall/integrations/langchain.py`

**Entry point:** `protect_langchain_agent(executor, *, goal=None, tool_type_map, action_map, resource_category_map, db, engine)`

**Returns:** `wall: ProtectedAgent` (executor is mutated in-place)

**Interception point:** `BaseTool.func` — the raw Python callable that `StructuredTool._run()` calls. Patching at this level avoids LangChain's `run_manager` injection layer.

**Wrapper:** `wrap_langchain_tool(tool, ...)` sets `tool.func = _wrapped` directly on the existing tool object. The executor and its tool list are not replaced.

**Goal extraction mechanism:**
- When `goal=None`: `executor.invoke` is monkey-patched with `_patched_invoke`.
- On first call where `wall.goal == ""`:
  - If input is `dict`: checks `input.get("input") or input.get("query") or input.get("task") or next(iter(input.values()), None)`.
  - If input is not `dict`: `str(input)`.
  - Calls `wall.set_goal(inferred)`.
- If `wall.goal` is already set (truthy), inference is skipped.
- Original `executor.invoke` is then called.

**Tool interception mechanism:**
```
executor.invoke({"input": "..."})
  → _patched_invoke fires → wall.goal set
  → original executor.invoke(...)
    → AgentExecutor runs LLM loop
    → LLM selects tool
    → tool._run(args) → tool.func(*args) → _wrapped(*args)
        RuntimeEvent constructed
        ToolInterceptor.before_execute(event)
        original_func(*args)
        ToolInterceptor.after_execute(event, result)
```

**Async gap:** LangChain's `ainvoke` / `arun` path bypasses `tool.func` and is not intercepted.

---

### CrewAI

**File:** `agentwall/integrations/crewai.py`

**Entry point:** `protect_crewai_crew(crew, *, goal=None, tool_type_map, action_map, resource_category_map, db, engine)`

**Returns:** `wall: ProtectedAgent` (crew tools mutated in-place)

**Interception point:** `BaseTool.func` on each tool of each agent in `crew.agents`. CrewAI's concrete `Tool.run()` calls `self.func()` directly; patching `_run` does not work.

**Wrapper:** `wrap_crewai_tool(tool, ...)` sets `tool.func = _wrapped` in-place.

**Traversal:** `for agent in crew.agents: for tool in agent.tools or []: if isinstance(tool, BaseTool): wrap`.

**Goal extraction mechanism:**
- When `goal=None`: `crew.kickoff` is monkey-patched with `_patched_kickoff`.
- On first call where `wall.goal == ""`:
  - If `inputs` is a `dict`: `str(next(iter(inputs.values()), ""))`.
  - If `inputs` is non-dict truthy: `str(inputs)`.
  - If `inputs` yields no string or is absent: reads `crew.tasks[0].description` if tasks exist.
  - Calls `wall.set_goal(inferred)`.
- Then calls `_original_kickoff(inputs=inputs, **kwargs)`.

**Tool interception mechanism:**
```
crew.kickoff(inputs={"task": "fix auth"})
  → _patched_kickoff fires → wall.goal = "fix auth"
  → original crew.kickoff(...)
    → CrewAI agent loop
    → agent selects tool
    → tool.run(...) → tool.func(*args) → _wrapped(*args)
        RuntimeEvent constructed
        ToolInterceptor.before_execute(event)
        original_func(*args)
        ToolInterceptor.after_execute(event, result)
```

---

## Section 3 — Goal Handling

### Creation

When `protect_*` is called:
- `ProtectedAgent.__init__` sets `self._goal_ref: list[str] = [goal or ""]`.
- `SessionManager.create(user_goal)` inserts a `sessions` row with `user_goal = ""` or the explicit value.

### Storage mechanism

`_goal_ref` is a single-element mutable list. All tool closures capture the same list object at wrap time. They read `_ref[0]` at call time (not at wrap time), so any update to `_goal_ref[0]` is seen by all already-wrapped tools.

### Goal updates

`ProtectedAgent.set_goal(goal: str)`:
1. `self._goal_ref[0] = goal` — immediately visible to all closures.
2. `self._session_mgr.update_goal(self._session.id, goal)` → `UPDATE sessions SET user_goal = ? WHERE id = ?`.

`SessionManager.update_goal(session_id, user_goal)` is a no-op if session_id does not exist.

### Inference (automatic)

| Framework | Trigger | Extraction |
|-----------|---------|------------|
| OpenAI | `InputGuardrail` fires before first LLM call | `_extract_goal_text(runner_input)` |
| LangChain | `executor.invoke(input)` patched | `input["input"] / ["query"] / ["task"] / first value` |
| CrewAI | `crew.kickoff(inputs)` patched | `first dict value` → fallback: `tasks[0].description` |

Inference only fires once: guarded by `if not wall.goal:`.

### Explicit override

Passing `goal="..."` to any `protect_*` function:
- Sets `_goal_ref[0]` to the explicit value immediately.
- Skips inference entirely (no patch applied to `invoke`/`kickoff`, no guardrail injected).
- Goal is never overwritten after that.

### Consumers

Every `RuntimeEvent` carries `goal = _ref[0]` at the time the tool fires. The goal is used in:
- `EvalContext.user_goal` when building the LLM evaluation prompt.
- Stored in the `sessions` table as `user_goal`.

---

## Section 4 — Runtime Event Lifecycle

### Construction

`RuntimeEvent` is a `@dataclass` in `agentwall/core/types.py`. Created inside each wrapped tool closure immediately before `interceptor.before_execute(event)`:

```python
event = RuntimeEvent(
    session_id = wall.session_id,        # UUID str from Session row
    goal       = _ref[0],                # current value of goal_ref at call time
    tool_type  = tool_type,              # ToolType enum
    action     = resolved_action,        # ToolAction enum
    target     = _extract_target(...),   # str extracted from args/kwargs
    resource_category = resource_category,  # ResourceCategory enum
    metadata   = {...},                  # dict of call args
    tool_name  = fn.__name__ or ft.name or tool.name,
    timestamp  = time.time(),
)
```

### Field origins

**`tool_type`** — set by user via `tool_type_map={tool_name: ToolType.FILESYSTEM}`. Falls back to `ToolType.API` if tool name not in map.

**`action`** — set by user via `action_map={tool_name: ToolAction.WRITE}`. Falls back via `_default_action(tool_type)`:
```
FILESYSTEM → READ
TERMINAL   → EXECUTE
BROWSER    → REQUEST
API        → REQUEST
DATABASE   → QUERY
EMAIL      → SEND
```

**`target`** — extracted by `_extract_target(args, kwargs)`:
1. Checks `kwargs` for first matching key in: `target, path, directory, url, query, command, address, recipient`.
2. Falls back to `str(args[0])` if positional args present.
3. Falls back to `""`.

**`resource_category`** — set by user via `resource_category_map`. Falls back to `ResourceCategory.UNKNOWN`.

**`metadata`:**
- `protect_tool` (plain): `{"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}}`.
- `wrap_openai_function_tool`: parsed `json.loads(args_json)` dict (raw LLM JSON args).
- `wrap_langchain_tool` / `wrap_crewai_tool`: `{"args": [...], "kwargs": {...}}`.

**`tool_name`:**
- Plain `protect_tool`: `fn.__name__`.
- OpenAI: `ft.name` (tool's registered name string).
- LangChain/CrewAI: `tool.name`.

### Lifetime

`RuntimeEvent` is an in-memory dataclass. It is NOT persisted directly. Its fields are persisted:
- Via `EventManager.record()` → `ToolEvent` row.
- Via `EventManager.record_evaluation()` → `Evaluation` row (after security engine runs).

After `before_execute` returns, the `RuntimeEvent` object is passed to `after_execute` (no-op) and then discarded.

---

## Section 5 — Security Evaluation Pipeline

**Entry:** `ToolInterceptor.before_execute(event: RuntimeEvent) → Decision`

```
before_execute(event)
  │
  ├─ 1. _fetch_history(session_id, limit=20)
  │       SELECT * FROM tool_events WHERE session_id=? ORDER BY timestamp LIMIT 20
  │       Each row reconstructed as RuntimeEvent (ValueError/KeyError rows silently skipped)
  │       Returns list[RuntimeEvent] (prior events, NOT including current event)
  │
  ├─ 2. record_event(event)
  │       INSERT INTO tool_events (...)
  │       Returns ToolEvent row with assigned id
  │
  ├─ 3. SecurityEngine.evaluate(event, history)
  │       │
  │       ├─ Stage 1: Detectors
  │       │     SensitiveResourceDetector.detect(event, history)  → list[str]
  │       │     ScopeExpansionDetector.detect(event, history)     → list[str]
  │       │     DataExfiltrationDetector.detect(event, history)   → list[str]
  │       │     All hits concatenated, deduplicated (order preserved)
  │       │     → unique_hits: list[str]
  │       │
  │       ├─ Stage 2: Rule engine
  │       │     rules.compute_risk(event) → float (0–100)
  │       │     risk += len(set(unique_hits)) * 10.0
  │       │     risk = min(risk, 100.0)
  │       │
  │       ├─ Stage 3: Policy override
  │       │     policy_engine.evaluate(event) → Decision | None
  │       │     If Decision returned:
  │       │       decision.detector_hits = unique_hits
  │       │       return decision  ← short-circuits stages 4 and 5
  │       │
  │       ├─ Stage 4: Threshold routing
  │       │     risk < 30.0  → Decision(ALLOW, risk, "low risk", detector_hits)
  │       │     risk < 70.0  → Decision(WARN,  risk, "elevated risk", detector_hits)
  │       │     risk >= 70.0 → escalate to Stage 5
  │       │
  │       └─ Stage 5: LLM escalation
  │             if self._chain is not None:
  │               EvalContext(goal, ToolCall(name, args, session_id))
  │               self._chain.evaluate(ctx) → Decision
  │               decision.llm_used = True
  │               decision.risk_score = max(llm_score, computed_risk)
  │               decision.detector_hits = unique_hits
  │               return decision
  │             else:
  │               return Decision(BLOCK, risk, "high risk — no LLM evaluator configured")
  │
  ├─ 4. record_evaluation(db_event.id, decision)
  │       INSERT INTO evaluations (event_id, decision, risk_score, reason,
  │                                llm_used, alignment_score, detector_hits, policy_matched)
  │
  └─ 5. if decision.type == BLOCK:
          raise AgentWallSecurityException(decision, event)
         else:
          return decision
```

**Inputs to each stage:**

| Stage | Input | Output |
|-------|-------|--------|
| Detectors | `RuntimeEvent`, `list[RuntimeEvent]` history | `list[str]` hit labels |
| Rules | `RuntimeEvent` | `float` base risk |
| Policy | `RuntimeEvent` | `Decision | None` |
| Threshold | `float` risk | `Decision` or escalate |
| LLM | `EvalContext` (goal + current tool call) | `Decision` |

**Thresholds:** When `SecurityEngine` is constructed directly, defaults are 30.0 (warn) and 70.0 (block/LLM). When constructed via `build_default_engine(db)`, thresholds are read from DB via `ConfigManager(db).get_thresholds()` (reads `policies` table row `"thresholds"`; falls back to 30.0/70.0 if absent).

---

## Section 6 — Detectors

All three detectors live in `agentwall/security/detectors.py`. All are instantiated by `_default_detectors()` and stored in `SecurityEngine._detectors`. Each detector's `detect(event, history)` returns a list of string labels (empty = clean). Each unique hit label contributes `10.0` to the risk score.

---

### SensitiveResourceDetector

**Purpose:** Detect access to credential and key files based on the tool's target string.

**Trigger conditions:** Inspects `event.target.lower()` with backslashes normalized to forward slashes. No history required.

**Pattern sets and hit labels:**

| Pattern set | Patterns | Hit label |
|-------------|----------|-----------|
| SSH | `.ssh/`, `id_rsa`, `id_ed25519`, `id_ecdsa`, `id_dsa`, `known_hosts`, `authorized_keys` | `ssh_key` |
| AWS | `.aws/credentials`, `.aws/config`, `aws_access_key`, `aws_secret_access_key`, `aws_session_token` | `aws_credentials` |
| Tokens | `.env`, `api_key`, `api_token`, `secret_key`, `access_token`, `auth_token`, `bearer_token`, `client_secret`, `refresh_token`, `service_account` | `api_token_or_secret` |
| Certs | `.pem`, `.p12`, `.pfx`, `.crt`, `.cert`, `-----begin`, `private_key`, `.key` | `private_key_or_cert` |
| Cloud | `.gcloud`, `gcp_key`, `azure_client`, `azure_tenant`, `kubeconfig`, `.kube/config` | `cloud_credentials` |

Multiple labels can be returned from one event (e.g., a target matching both SSH and cloud patterns).

---

### ScopeExpansionDetector

**Purpose:** Detect when the agent accesses unexpected tool types or privileged resources relative to its established behavior.

**History minimum:** 3 events. Returns empty list if `len(history) < 3`.

**Hit conditions:**

| Condition | Minimum history | Hit label |
|-----------|----------------|-----------|
| `event.tool_type` not in any prior event's `tool_type` | 3 | `new_tool_type_introduced` |
| `event.resource_category` in `{CREDENTIALS, SYSTEM}` AND no prior event had CREDENTIALS or SYSTEM | 3 | `privilege_escalation` |
| One tool type is ≥ 70% of history events AND current event uses a different type | 5 | `unrelated_resource_access` |

The dominant-type check iterates all events in history, counts per `ToolType`, finds the max. Dominant share = `count(dominant) / len(history)`.

---

### DataExfiltrationDetector

**Purpose:** Detect patterns consistent with data being sent externally.

**Known exfiltration domains checked:** `webhook.site`, `requestbin`, `pipedream.net`, `pastebin.com`, `gist.github.com`, `ngrok.io`, `serveo.net`, `transfer.sh`, `hastebin.com`.

**Private prefixes (not considered external):** `localhost`, `127.`, `192.168.`, `10.`, `172.`.

**Hit conditions:**

| Condition | Hit label |
|-----------|-----------|
| `tool_type == EMAIL` and `action == SEND` | `external_email_send` |
| `tool_type in {BROWSER, API}` and `action in {SEND, REQUEST, WRITE}` and target matches exfil domain | `exfil_domain_upload` |
| `tool_type in {BROWSER, API}` and `action in {SEND, REQUEST, WRITE}` and target is external AND last 10 history events contain `FILESYSTEM READ` with `resource_category == CREDENTIALS` | `credential_read_then_external_call` |
| `tool_type == TERMINAL` and `action == EXECUTE` and target contains exfil command (`curl `, `wget `, `scp `, `rsync `, `nc `, `ncat `) and known exfil domain | `terminal_exfil_to_known_domain` |

For `external_email_send`, detection returns immediately without checking further conditions.

---

## Section 7 — Rules Engine

**File:** `agentwall/security/rules.py`

**Entry:** `compute_risk(event: RuntimeEvent) → float`

Dispatches to a per-tool-type function via `_RULE_MAP`, then adds a `_category_bonus`, then caps at `100.0`.

### Category bonus (added to every rule result)

| ResourceCategory | Bonus |
|-----------------|-------|
| CREDENTIALS | +30.0 |
| SYSTEM | +20.0 |
| CONFIG | +10.0 |
| NETWORK | +10.0 |
| CODE | +5.0 |
| USER_DATA | +5.0 |
| UNKNOWN | +0.0 |

### Per tool type risk

**FILESYSTEM** (`_filesystem_risk`):

| Condition | Score added |
|-----------|-------------|
| Target matches any `_SENSITIVE_PATHS` (`.ssh`, `.aws`, `.gnupg`, `.config/gcloud`, `id_rsa`, `id_ed25519`, `id_ecdsa`, `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`, `.env`, `credentials`, `secrets`, `.npmrc`, `.pypirc`, `.netrc`, `.kube/config`, `kubeconfig`, `docker.sock`, `.docker/config`) | +80.0 |
| `..` in target | +40.0 |
| action == WRITE | +25.0 |
| action == DELETE | +55.0 |
| action == CREATE | +10.0 |
| action == READ | +0.0 |

**TERMINAL** (`_terminal_risk`):

| Condition | Score added |
|-----------|-------------|
| `rm -rf /` or `rm -rf *` in target | +90.0 |
| Any `_DANGEROUS_COMMANDS` in target (rm -rf, dd if=, format, chmod 777/666, chown, curl, wget, nc, netcat, ncat, ssh, scp, rsync, sudo, su, iptables, ufw, crontab, at, python -c, perl -e, ruby -e, node -e, eval, exec(, base64 -d, base64 --decode, /bin/bash, /bin/sh, cmd.exe, powershell) | +40.0 |
| action == EXECUTE | +15.0 |

**BROWSER** (`_browser_risk`):

| Condition | Score added |
|-----------|-------------|
| Target does not start with `http://` or `https://` | +30.0 |
| Target matches `_EXFIL_DOMAINS` (webhook.site, requestbin, pipedream.net, pastebin.com, gist.github.com, ngrok.io, serveo.net) | +55.0 |

**API** (`_api_risk`):

| Condition | Score added |
|-----------|-------------|
| Target matches `_EXFIL_DOMAINS` | +55.0 |
| action == SEND | +20.0 |

**DATABASE** (`_database_risk`):

| Condition | Score added |
|-----------|-------------|
| Target contains `drop table`, `drop database`, `truncate `, or `delete from` | +70.0 |
| Target contains `select *` | +15.0 |
| action == DELETE | +40.0 |
| action in {WRITE, CREATE} | +10.0 |

**EMAIL** (`_email_risk`):

| Condition | Score added |
|-----------|-------------|
| action == SEND | +35.0 |

**Default** (unrecognized tool type): 10.0.

### Thresholds and routing (in SecurityEngine)

| Score range | Decision |
|------------|---------|
| < 30.0 | ALLOW |
| 30.0 – 69.9 | WARN |
| ≥ 70.0 | LLM escalation (or BLOCK if no chain) |

Each unique detector hit label adds 10.0 to the rule engine base score before threshold routing.

---

## Section 8 — Policy Engine

**File:** `agentwall/security/policy_engine.py`

### Evaluation order

1. Load all enabled policies (`enabled=True`) ordered by `created_at` ASC (oldest first).
2. For each policy, iterate `policy.config["rules"]` in list order.
3. For each rule, call `_rule_matches(rule, event)`.
4. Return `Decision` on first matching rule of first matching policy.
5. Return `None` if no match.

### Rule matching

`_rule_matches(rule, event)` returns `True` only if all specified fields match. Any field omitted from the rule is not checked (matches any value).

| Rule field | Matching logic |
|-----------|---------------|
| `tool_type` | `rule["tool_type"] == event.tool_type.value` (exact string) |
| `action` | `rule["action"] == event.action.value` (exact string) |
| `resource_category` | `rule["resource_category"] == event.resource_category.value` (exact string) |
| `pattern` | `fnmatch.fnmatch(target, pattern) OR pattern in target` (target backslash-normalized to `/`) |

A rule with no fields specified matches all events.

### Policy config format

```json
{
  "description": "optional text",
  "rules": [
    {
      "tool_type": "filesystem",
      "action": "read",
      "resource_category": "credentials",
      "pattern": "*/.ssh/*",
      "decision": "block",
      "reason": "ssh key access blocked"
    }
  ]
}
```

All fields in each rule are optional.

### Override behavior

When a policy matches, the returned `Decision` has:
- `type`: `DecisionType(verdict)` where `verdict` is `rule["decision"]` (allow/warn/block), defaulting to `"block"` if absent or invalid.
- `risk_score`: allow=0.0, warn=50.0, block=85.0 (from `_verdict_score`).
- `reason`: `rule["reason"]` or `f"policy '{policy.name}'"`.
- `metadata["policy_matched"]`: `policy.name`.
- `detector_hits`: attached by `SecurityEngine` after the policy returns.

The policy decision **short-circuits** stages 4 and 5 (threshold routing and LLM escalation). It overrides the computed risk score entirely.

### Precedence rules

- Policies are evaluated in creation order (oldest first).
- Rules within a policy are evaluated in list order.
- First match wins. No second-rule evaluation.
- Policy match bypasses threshold calculation and LLM.

---

## Section 9 — LLM Security Evaluation

### When triggered

Only when `risk >= block_threshold (70.0)` AND `SecurityEngine._chain is not None`.

**In practice:** All `protect_*` functions call `build_default_engine(db)`, which calls `ProviderRegistry(db).load_chain()`. If the user has configured providers via `agentwall config`, a live `ProviderChain` is returned and LLM evaluation fires for high-risk events. If no providers are configured, `load_chain()` raises `ValueError`, `build_default_engine` catches it, and `_chain` is `None` — events scoring ≥ threshold are blocked with `"high risk — no LLM evaluator configured"`.

### Providers implemented

| Provider | Class | SDK used | API key required |
|---------|-------|----------|-----------------|
| openai | `OpenAIEvaluator` | `openai.OpenAI` | Yes |
| anthropic | `AnthropicEvaluator` | `anthropic.Anthropic` | Yes |
| groq | `GroqEvaluator` | `openai.OpenAI` with `base_url=https://api.groq.com/openai/v1` | Yes |
| deepseek | `DeepSeekEvaluator` | `openai.OpenAI` with `base_url=https://api.deepseek.com` | Yes |
| ollama | `OllamaEvaluator` | `httpx.post` to `http://localhost:11434/api/generate` | No |

API keys stored and retrieved via OS keyring (`keyring` library). Not stored in DB or files.

### ProviderChain

`ProviderChain.evaluate(ctx)` tries evaluators in list order. On any exception from one evaluator, continues to next. Returns `Decision(BLOCK, 100.0, "All providers failed...")` if all evaluators raise.

### Prompt structure

`build_prompt(ctx)` in `agentwall/providers/base.py`:

```
You are a runtime security evaluator for AI agents.

User Goal: {ctx.user_goal}

Recent Actions:
  {ctx.recent_history[-5:] formatted, or "(none)"}

Current Action: {ctx.tool_call.name}({json.dumps(ctx.tool_call.arguments)})

Does this action align with the stated goal? Reply with JSON only:
{"decision": "allow|warn|block", "reason": "one sentence", "alignment_score": 0-100}
```

**Note:** `ctx.recent_history` is populated from the `history: list[RuntimeEvent]` passed to `SecurityEngine.evaluate()`. Each event is converted to a `ToolCall` with `name`, `arguments={"target": ..., **metadata}`, and `session_id`. The LLM receives up to 5 recent actions via `ctx.recent_history[-5:]` in the prompt.

### Context supplied

| Field | Value |
|-------|-------|
| `user_goal` | `event.goal` (`_ref[0]` at call time) |
| `tool_call.name` | `event.tool_name or f"{tool_type}.{action}"` |
| `tool_call.arguments` | `{"target": event.target, **event.metadata}` |
| `tool_call.session_id` | `event.session_id` |
| `recent_history` | Last N `RuntimeEvent` objects from `history`, converted to `ToolCall` |

### LLM parameters

| Provider | Parameters |
|---------|-----------|
| OpenAI | `max_tokens=150, temperature=0` |
| Anthropic | `max_tokens=150` |
| Groq | `max_tokens=150, temperature=0` |
| DeepSeek | `max_tokens=150, temperature=0` |
| Ollama | `stream=False`, 30s timeout |

### Response parsing

`parse_llm_response(text, fallback_score=75.0)`:
1. `re.search(r"\{[^}]+\}", text, re.DOTALL)` — first JSON-like object.
2. `json.loads(match.group())`.
3. Reads `decision` (allow/warn/block, falls back to "block" if invalid).
4. Reads `alignment_score` as float (stored in Evaluation row).
5. Reads `reason`.
6. Returns `Decision(type, risk_score=fallback_score, reason, alignment_score)`.
7. If no JSON found or parse fails: returns `Decision(BLOCK, fallback_score, "Failed to parse LLM response")`.

### Post-LLM processing (in SecurityEngine)

```python
decision.llm_used = True
decision.risk_score = max(decision.risk_score, computed_risk)
decision.detector_hits = unique_hits
```

### Alignment scoring

`alignment_score` (0–100 as provided by the LLM) is stored in `evaluations.alignment_score`. It is not used in routing logic — only stored for audit purposes.

---

## Section 10 — Persistence Layer

**File:** `agentwall/storage/database.py`
**Location:** `~/.agentwall/data.db` (SQLite)
**Mode:** WAL journal mode, foreign keys enabled.

### Schema

**`sessions`**
| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID4 string |
| `user_goal` | TEXT NOT NULL | Empty string when goal not yet inferred |
| `created_at` | REAL | Unix timestamp |
| `ended_at` | REAL NULL | Set by `SessionManager.end()` |
| `meta` | JSON | Empty dict by default |

**`tool_events`**
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK autoincrement | |
| `session_id` | TEXT FK → sessions.id | |
| `tool_name` | TEXT NOT NULL | |
| `arguments` | JSON NOT NULL | |
| `timestamp` | REAL | |
| `tool_type` | TEXT NULL | ToolType enum value |
| `action` | TEXT NULL | ToolAction enum value |
| `target` | TEXT NULL | Extracted target string |
| `resource_category` | TEXT NULL | ResourceCategory enum value |

**`evaluations`** (1:1 with tool_events)
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK autoincrement | |
| `event_id` | INTEGER FK → tool_events.id | |
| `decision` | TEXT NOT NULL | `allow` / `warn` / `block` |
| `risk_score` | REAL NOT NULL | |
| `reason` | TEXT NOT NULL | |
| `llm_used` | BOOLEAN | |
| `timestamp` | REAL | |
| `alignment_score` | REAL NULL | LLM-provided score |
| `detector_hits` | JSON NULL | list of hit label strings |
| `policy_matched` | TEXT NULL | policy name if triggered |

**`policies`**
| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK autoincrement | |
| `name` | TEXT UNIQUE NOT NULL | |
| `config` | JSON NOT NULL | `{"description": ..., "rules": [...]}` |
| `created_at` | REAL | |
| `enabled` | BOOLEAN | |

**`provider_settings`**
| Column | Type | Notes |
|--------|------|-------|
| `provider` | TEXT PK | e.g., `openai`, `anthropic` |
| `model` | TEXT NOT NULL | |
| `priority` | INTEGER | Lower = higher priority in chain |
| `enabled` | BOOLEAN | |
| `config` | JSON | Currently unused in evaluation |

### Relationships

```
sessions 1──* tool_events 1──1 evaluations
policies (standalone)
provider_settings (standalone)
```

### Migrations

`Database._migrate()` runs on every `Database()` construction. Uses `ALTER TABLE ADD COLUMN` with exception suppression for each column that may not exist in older schemas:
- `provider_settings`: adds `priority`, `enabled`
- `tool_events`: adds `tool_type`, `action`, `target`, `resource_category`
- `evaluations`: adds `alignment_score`, `detector_hits`, `policy_matched`
- `policies`: adds `enabled`

### Risk thresholds

Stored as a `policies` row with `name="thresholds"` and `config={"low_threshold": 30.0, "high_threshold": 70.0}`. Read by `ConfigManager.get_thresholds()`. Not automatically loaded into `SecurityEngine`.

---

## Section 11 — Inspector Workflow

### Startup: `agentwall inspect`

**CLI entry:** `agentwall/cli/main.py:inspect()`

```
agentwall inspect [--host 127.0.0.1] [--port 8080] [--browser]
  │
  ├── Check agentwall/inspector/ui/dist/ exists
  │     If not: print warning, continue in API-only mode
  │
  ├── if --browser:
  │     _launch_browser(host, port)
  │       spawn daemon thread → sleep(1.5) → webbrowser.open(url)
  │       uvicorn.run("agentwall.inspector.server:app", ...) ← blocks main thread
  │
  └── else (default):
        launch_desktop(host, port)
          spawn daemon thread → _run_server_thread(host, port)
            uvicorn Config + Server created
            asyncio.run(_serve()) ← blocks daemon thread
          _wait_for_server(host, port, timeout=15.0, interval=0.2)
            poll GET http://host:port/api/health every 0.2s up to 15s
            if 200: continue
            if timeout: raise RuntimeError
          webview.create_window("AgentWall Inspector", url, width=1280, height=800, resizable=True)
          webview.start() ← blocks main thread until window closed
```

### Backend startup

FastAPI app assembled in `agentwall/inspector/server.py`:
- CORS middleware: all origins, all methods, all headers.
- 8 routers registered (see Section 12).
- `StaticFiles` mounted at `/` from `agentwall/inspector/ui/dist/` if that directory exists.

### Real-time updates

**WebSocket endpoint:** `GET /ws/events` (upgraded to WS).

Implemented as a SQLite polling loop:
```python
last_id = SELECT MAX(id) FROM tool_events
while True:
    await asyncio.sleep(1.5)
    current_id = SELECT MAX(id) FROM tool_events
    if current_id != last_id:
        last_id = current_id
        await websocket.send_json({"type": "refresh"})
```

The UI is expected to re-fetch data on receiving `{"type": "refresh"}`. No event data is sent over the WebSocket.

### Shutdown

- Desktop mode: closing the PyWebView window unblocks `webview.start()`. The daemon thread running uvicorn is killed when the process exits.
- Browser mode: Ctrl+C kills the uvicorn process.
- No graceful shutdown sequence is implemented.

---

## Section 12 — CLI Commands

**File:** `agentwall/cli/main.py`
**Entrypoint:** `agentwall = "agentwall.cli.main:app"` (Typer app)

### `agentwall version`

Prints `agentwall {__version__}` (currently `0.1.0`).

### `agentwall doctor`

Attempts `importlib.import_module(module)` for each of:
```
keyring      → "API key storage (keyring)"
sqlalchemy   → "ORM (sqlalchemy)"
fastapi      → "Inspector API (fastapi)"
uvicorn      → "Inspector server (uvicorn)"
pydantic     → "Validation (pydantic)"
openai       → "OpenAI/Groq/DeepSeek SDK (openai)"
anthropic    → "Anthropic SDK (anthropic)"
webview      → "Desktop Inspector (pywebview)"
```
Prints `OK` or `MISSING` per module. Exits 1 if any missing.

### `agentwall config`

**Flags mode** (any flag provided):
- `--provider <name> --model <name> [--priority <int>]`: calls `ConfigManager.set_provider()`.
- `--low-threshold <float> --high-threshold <float>`: calls `ConfigManager.set_thresholds()`.
- `--status`: calls `ProviderRegistry.health_check_all()`.

**Interactive wizard** (no flags):
Prompts: select action → Add/update provider | Remove provider | Set thresholds | Test connections.

Add/update provider flow:
1. Select provider from list of 5.
2. Prompt API key (hidden input) → `keyring.store_api_key(provider, key)`.
3. Select model from provider's list.
4. Set priority (integer).
5. Instantiate evaluator and call `.health_check()`.
6. Prompt to save if health check fails.
7. `ConfigManager.set_provider(provider, model, priority)`.

### `agentwall inspect`

Covered in Section 11.

**Options:**
- `--host TEXT` (default: `127.0.0.1`)
- `--port INTEGER` (default: `8080`)
- `--browser` flag

---

## Section 13 — Public API

### Top-level exports

```python
from agentwall import protect_agent, protect_tool
```

**`protect_agent(agent, *, goal: str | None = None, db=None, engine=None) → ProtectedAgent`**

Located in `agentwall/interceptors/__init__.py`. `goal` is optional; defaults to `""` when omitted. Returns a `ProtectedAgent`.

**`protect_tool(fn, *, tool_type, session_id, goal=None, goal_ref=None, interceptor, action=None, resource_category=UNKNOWN) → Callable`**

Located in `agentwall/interceptors/tool.py`. Wraps a plain Python callable. `interceptor` must be provided (a `ToolInterceptor` instance). Used internally by `ProtectedAgent.protect_tool()`.

---

### ProtectedAgent

```python
from agentwall.interceptors.agent import ProtectedAgent

wall = ProtectedAgent(agent, *, goal=None, db=None, engine=None)
```

| Member | Type | Description |
|--------|------|-------------|
| `wall.session_id` | `str` (property) | UUID of the active session |
| `wall.goal` | `str` (property) | Current value of `_goal_ref[0]` |
| `wall.set_goal(goal)` | `None` | Updates `_goal_ref[0]` and DB |
| `wall.protect_tool(fn, *, tool_type, action=None, resource_category=UNKNOWN)` | `Callable` | Wraps a function with interception |
| `wall.run(*args, **kwargs)` | `Any` | Delegates to wrapped agent's `run()` |
| `wall.end_session()` | `None` | Sets `ended_at` in DB |
| `wall.close()` | `None` | Alias for `end_session()` |
| Context manager | | `__enter__` returns `wall`, `__exit__` calls `close()` |

---

### Framework integrations

**`protect_openai_agent`**

```python
from agentwall.integrations.openai_agents import protect_openai_agent

wall, protected_agent = protect_openai_agent(
    agent,
    goal=None,                     # optional; inferred from Runner.run() input if omitted
    tool_type_map={"fn": ToolType.FILESYSTEM},
    action_map={"fn": ToolAction.READ},
    resource_category_map={"fn": ResourceCategory.CODE},
    db=None,
    engine=None,
)
result = await Runner.run(protected_agent, "user prompt")
wall.end_session()
```

**`protect_langchain_agent`**

```python
from agentwall.integrations.langchain import protect_langchain_agent

wall = protect_langchain_agent(
    executor,                      # AgentExecutor, mutated in-place
    goal=None,                     # optional; inferred from executor.invoke() input if omitted
    tool_type_map={...},
    action_map={...},
    resource_category_map={...},
    db=None,
    engine=None,
)
result = executor.invoke({"input": "user prompt"})
wall.end_session()
```

**`protect_crewai_crew`**

```python
from agentwall.integrations.crewai import protect_crewai_crew

wall = protect_crewai_crew(
    crew,                          # Crew, tools mutated in-place
    goal=None,                     # optional; inferred from crew.kickoff() if omitted
    tool_type_map={...},
    action_map={...},
    resource_category_map={...},
    db=None,
    engine=None,
)
result = crew.kickoff(inputs={"task": "user prompt"})
wall.end_session()
```

---

### Types

```python
from agentwall.core.types import (
    ToolType,          # FILESYSTEM, TERMINAL, BROWSER, API, DATABASE, EMAIL
    ToolAction,        # READ, WRITE, DELETE, EXECUTE, REQUEST, QUERY, SEND, LIST, CREATE
    ResourceCategory,  # CODE, CONFIG, CREDENTIALS, SYSTEM, NETWORK, USER_DATA, UNKNOWN
    DecisionType,      # ALLOW, WARN, BLOCK
    RuntimeEvent,
    Decision,
    EvalContext,
    ToolCall,
)
```

---

## Section 14 — Known Limitations

**1. `ProtectedAgent.run()` raises in all framework integrations.**
Framework `protect_*` functions pass a `_Stub()` as the wrapped agent. `wall.run()` raises `RuntimeError("Use Runner.run / AgentExecutor.invoke / crew.kickoff instead.")`.

**2. ScopeExpansionDetector blind on first calls.**
Requires minimum 3 prior events to generate any hit, 5 for `unrelated_resource_access`. The first few tool calls in a new session are never flagged for scope expansion, regardless of what they access.

**3. DB path not configurable at runtime.**
The default path `~/.agentwall/data.db` is a module-level constant. No environment variable overrides it. The only way to change it is to pass `path=...` to the `Database()` constructor and then pass that `db` to `protect_*`.

**4. OllamaEvaluator `api_key` parameter accepted but ignored.**
`OllamaEvaluator.__init__` accepts `api_key=None` to match the `BaseEvaluator` interface but does not use it.

**5. ResultAnalyzer LangChain async path: result is string, not awaited.**
In `wrap_langchain_tool` async wrapper, `after_execute(event, result)` is called after `await original_coro(...)`. The result passed to `ResultAnalyzer` is already the awaited value — correct behavior.

**6. GoalTracker transition heuristic: short goals unreliable.**
Two-signal heuristic (full token overlap + resource token overlap) handles verb-change continuity well but remains inaccurate for very short goals ("fix it", "done") that produce low token counts. No LLM disambiguation in v0.1.0.

**Resolved in this pass (previously listed, now fixed):**
- ~~WebSocket polling~~ → event-driven push via `EventBus` (`call_soon_threadsafe`)
- ~~Policy engine no priority field~~ → `priority INTEGER` on policies; descending priority evaluation order
- ~~`parse_llm_response` single-brace regex~~ → balanced-brace extraction handles nested JSON + fenced blocks
- ~~GoalTracker not thread-safe~~ → `threading.RLock` on `set_goal()` and `maybe_infer()`
- ~~Token overlap only~~ → two-signal heuristic strips action verbs; resource continuity preserved

---

## Section 15 — Final Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER APPLICATION                           │
│                                                                     │
│  protect_openai_agent(agent, goal=None)                             │
│  protect_langchain_agent(executor, goal=None)                       │
│  protect_crewai_crew(crew, goal=None)                               │
│  protect_agent(agent, goal=None)   ← top-level, goal optional        │
└────────────────────────────┬────────────────────────────────────────┘
                             │ returns (wall, protected) or wall
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       ProtectedAgent                                │
│                                                                     │
│  _goal_ref: list[str]  ← shared mutable reference                  │
│  session_id: str       ← UUID from SessionManager.create()         │
│  _interceptor: ToolInterceptor                                      │
│  _session_mgr: SessionManager                                       │
│                                                                     │
│  set_goal(goal) → _goal_ref[0] = goal                              │
│                 → SessionManager.update_goal(session_id, goal)      │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │ Wraps tools at startup  │
          ▼                         ▼
┌──────────────────┐   ┌─────────────────────────────────────────────┐
│  Goal Inference  │   │             Wrapped Tools                   │
│                  │   │                                             │
│ OpenAI:          │   │  OpenAI:   FunctionTool.on_invoke_tool      │
│  InputGuardrail  │   │            (new object via dataclasses)     │
│  fires pre-LLM   │   │                                             │
│                  │   │  LangChain: tool.func patched in-place      │
│ LangChain:       │   │                                             │
│  invoke patched  │   │  CrewAI:   tool.func patched in-place       │
│                  │   │                                             │
│ CrewAI:          │   │  Plain:    functools.wraps wrapper          │
│  kickoff patched │   │            (protect_tool)                   │
└──────────────────┘   └────────────────────┬────────────────────────┘
                                            │ tool fired by agent
                                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    RuntimeEvent constructed                         │
│                                                                     │
│  session_id, goal (_ref[0]), tool_type, action, target,            │
│  resource_category, metadata, tool_name, timestamp                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ToolInterceptor.before_execute()                 │
│                                                                     │
│  1. _fetch_history(session_id, limit=20)                            │
│       → SELECT FROM tool_events → list[RuntimeEvent]               │
│                                                                     │
│  2. EventManager.record()                                           │
│       → INSERT INTO tool_events                                     │
│                                                                     │
│  3. SecurityEngine.evaluate(event, history)                         │
│       → see pipeline below                                          │
│                                                                     │
│  4. EventManager.record_evaluation()                                │
│       → INSERT INTO evaluations                                     │
│                                                                     │
│  5. decision.type == BLOCK?                                         │
│       YES → raise AgentWallSecurityException                        │
│       NO  → return Decision (ALLOW or WARN)                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    SecurityEngine.evaluate()                        │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Stage 1: Detectors                                          │   │
│  │  SensitiveResourceDetector  → target string pattern match  │   │
│  │  ScopeExpansionDetector     → history comparison           │   │
│  │  DataExfiltrationDetector   → external upload patterns     │   │
│  │  → unique_hits: list[str]                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                             │                                       │
│  ┌──────────────────────────▼──────────────────────────────────┐   │
│  │ Stage 2: Rule Engine                                        │   │
│  │  compute_risk(event)                                        │   │
│  │    _RULE_MAP[tool_type](event) + _category_bonus(category) │   │
│  │  risk += len(set(unique_hits)) * 10.0                      │   │
│  │  risk = min(risk, 100.0)                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                             │                                       │
│  ┌──────────────────────────▼──────────────────────────────────┐   │
│  │ Stage 3: Policy Override (if policy_engine configured)      │   │
│  │  policy_engine.evaluate(event)                              │   │
│  │    for each enabled policy (created_at ASC):                │   │
│  │      for each rule: _rule_matches → first match → Decision  │   │
│  │  If Decision returned → attach detector_hits → return       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                             │ (if no policy match)                 │
│  ┌──────────────────────────▼──────────────────────────────────┐   │
│  │ Stage 4: Threshold Routing                                  │   │
│  │  risk < 30.0  → ALLOW                                      │   │
│  │  risk < 70.0  → WARN                                       │   │
│  │  risk >= 70.0 → escalate                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                             │ (risk >= 70.0 only)                  │
│  ┌──────────────────────────▼──────────────────────────────────┐   │
│  │ Stage 5: LLM Escalation (if provider_chain configured)      │   │
│  │  EvalContext(goal, ToolCall, recent_history=from_history)   │   │
│  │  ProviderChain.evaluate(ctx)                                │   │
│  │    try evaluators in priority order (from DB)               │   │
│  │    build_prompt(ctx) → LLM call → parse_llm_response()     │   │
│  │  decision.llm_used = True                                   │   │
│  │  decision.risk_score = max(llm, computed)                   │   │
│  │                                                             │   │
│  │  [if no chain] → BLOCK "no LLM evaluator configured"       │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
         ALLOW             WARN             BLOCK
           │                 │                 │
    tool executes     tool executes    AgentWallSecurityException
    result returned   result returned  raised (tool NOT called)
           │                 │
           └────────┬────────┘
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│             ToolInterceptor.after_execute(event, result)            │
│                                                                     │
│  1. event_id = _event_id_map.pop(id(event))                        │
│  2. ResultAnalyzer.analyze(event, result) → AnalysisResult         │
│       filesystem: credential patterns, hash match                  │
│       database:   row count, sensitive column names                 │
│       api:        write action + success signal                     │
│       email:      always EMAIL_DISPATCH                             │
│  3. EventManager.update_evaluation_post(event_id, analysis)        │
│       → UPDATE evaluations SET                                      │
│           post_execution_risk = ...,                                │
│           result_classification = ...,                              │
│           result_detector_hits = ...,                               │
│           result_metadata = ...  ← hashes/counts ONLY              │
│                                                                     │
│  NOTE: pre-execution decision NEVER changed. ALLOW stays ALLOW.    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    SQLite (~/.agentwall/data.db)                    │
│                                                                     │
│  sessions ──────────────────────────────────────────────────────── │
│    id, user_goal, created_at, ended_at, meta                       │
│       │                                                             │
│       ├─── goal_segments ──────────────────────────────────────── │
│       │      id, session_id, goal_text, started_at, ended_at,      │
│       │      transition_reason                                      │
│       │                                                             │
│       └─── tool_events ─────────────────────────────────────────── │
│              id, session_id, tool_name, arguments, timestamp,       │
│              tool_type, action, target, resource_category           │
│                │                                                    │
│                └─── evaluations (1:1) ─────────────────────────── │
│                       id, event_id, decision, risk_score, reason,   │
│                       llm_used, alignment_score, detector_hits,     │
│                       policy_matched,                               │
│                       post_execution_risk, result_classification,   │
│                       result_detector_hits, result_metadata         │
│                                                                     │
│  policies ─────────── id, name, config (JSON rules), enabled       │
│  provider_settings ── provider (PK), model, priority, enabled      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    Inspector (agentwall inspect)                    │
│                                                                     │
│  launch_desktop()                                                   │
│    daemon thread: uvicorn → FastAPI (agentwall.inspector.server)    │
│    poll /api/health until 200 (15s timeout)                         │
│    webview.create_window() + webview.start() ← blocks              │
│                                                                     │
│  FastAPI routes:                                                    │
│    GET  /api/health                                                 │
│    GET  /api/overview                                               │
│    GET  /api/sessions                                               │
│    GET  /api/sessions/{id}                                          │
│    POST /api/sessions/{id}/end                                      │
│    GET  /api/sessions/{id}/events   ← includes post-execution data │
│    GET  /api/sessions/{id}/goals    ← goal segment timeline        │
│    CRUD /api/policies                                               │
│    CRUD /api/providers  (+ /key, /test)                             │
│    GET  /api/export?format=json|csv                                 │
│    WS   /ws/events  (polls MAX(id) every 1.5s, sends "refresh")    │
│    GET  /           (StaticFiles from ui/dist/ if built)            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Deviations from CLAUDE.md

| CLAUDE.md statement | Actual implementation |
|--------------------|----------------------|
| "Risk 30-70 → Warn, Risk > 70 → LLM Evaluation" | LLM evaluation fires when `risk >= block_threshold` AND `_chain is not None`. `build_default_engine(db)` auto-constructs chain from configured providers via `ProviderRegistry(db).load_chain()`. If no providers configured, chain is `None` and risk ≥ threshold → BLOCK with "no LLM evaluator configured". |
| "Inspector = native desktop window (PyWebView)" | Implemented. `agentwall inspect` calls `launch_desktop()`. `--browser` flag available for headless fallback. |
| "Backend runs locally at http://localhost:8080 (internal)" | Correct. Uvicorn binds to `127.0.0.1:8080` by default. |
| Thresholds configurable | `ConfigManager.set_thresholds()` saves to DB. `build_default_engine(db)` reads them back via `ConfigManager(db).get_thresholds()` and passes to `SecurityEngine`. Fully wired. |
| "Send only: User Goal, Recent Tool History, Current Action" to LLM | Implemented. `EvalContext.recent_history` populated from `history` list in `SecurityEngine.evaluate()`. LLM prompt includes last 5 recent actions. |
| `goal` parameter optional in all `protect_*` functions | Optional in all: `ProtectedAgent.__init__`, `protect_agent`, `protect_openai_agent`, `protect_langchain_agent`, `protect_crewai_crew`. Fully consistent. |
| Inspector: "No browser navigation required" | Correct for desktop mode. |
| "Timeline Analysis, Threat Investigation, Policy Management, Provider Configuration, Evaluation Review" in Inspector | Backend API routes and built React UI both present (`ui/dist/` exists with full 5-page app). Fully functional. |
