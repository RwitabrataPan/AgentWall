# AgentWall API Reference

---

## Top-Level API

### `protect_agent`

```python
from agentwall import protect_agent

wall = protect_agent(
    agent,
    *,
    goal: str | None = None,
    db: Database | None = None,
    engine: SecurityEngine | None = None,
) -> ProtectedAgent
```

Wraps any agent object for tool interception. Returns a `ProtectedAgent`.

| Parameter | Description |
|-----------|-------------|
| `agent` | Any object with a `run()` method (or any framework agent) |
| `goal` | User's stated objective. Omit to set later via `wall.set_goal()` |
| `db` | `Database` instance. Default: `~/.agentwall/data.db` |
| `engine` | `SecurityEngine` instance. Default: auto-constructed from DB config |

### `protect_tool`

```python
from agentwall import protect_tool

safe_fn = protect_tool(
    fn: Callable,
    *,
    tool_type: ToolType,
    session_id: str,
    goal_ref: list[str],
    interceptor: ToolInterceptor,
    action: ToolAction | None = None,
    resource_category: ResourceCategory = ResourceCategory.UNKNOWN,
) -> Callable
```

Wraps a single callable. Lower-level than `ProtectedAgent.protect_tool()`.

---

## ProtectedAgent

```python
from agentwall.interceptors.agent import ProtectedAgent

wall = ProtectedAgent(agent, *, goal=None, db=None, engine=None)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `wall.session_id` | `str` | UUID of the active session |
| `wall.goal` | `str` | Current goal (`_goal_ref[0]`) |

### Methods

```python
wall.set_goal(goal: str) -> None
```
Updates `_goal_ref[0]`, persists to DB, closes active goal segment, opens new segment.

```python
wall.maybe_infer_goal(new_input: str) -> bool
```
Sets or transitions goal from `new_input`. Used by framework inference patches on every invoke/kickoff. Returns `True` if goal changed. Applies two-signal transition heuristic (token overlap + resource overlap).

```python
wall.protect_tool(
    fn: Callable,
    *,
    tool_type: ToolType,
    action: ToolAction | None = None,
    resource_category: ResourceCategory = ResourceCategory.UNKNOWN,
) -> Callable
```
Wraps a callable with interception. Returns wrapped function.

```python
wall.run(*args, **kwargs) -> Any
```
Delegates to the wrapped agent's `run()`. Raises `RuntimeError` in framework integrations (use framework-native run methods).

```python
wall.end_session() -> None
wall.close() -> None  # alias
```
Marks session as ended in DB.

**Context manager:**

```python
with protect_agent(agent, goal="...") as wall:
    wall.protect_tool(fn, tool_type=ToolType.FILESYSTEM)
    agent.run()
```

---

## Framework Integrations

### OpenAI Agents SDK

```python
from agentwall.integrations.openai_agents import protect_openai_agent

wall, protected_agent = protect_openai_agent(
    agent: Agent,
    *,
    goal: str | None = None,
    tool_type_map: dict[str, ToolType] | None = None,
    action_map: dict[str, ToolAction] | None = None,
    resource_category_map: dict[str, ResourceCategory] | None = None,
    db: Database | None = None,
    engine: SecurityEngine | None = None,
) -> tuple[ProtectedAgent, Agent]
```

Returns `(wall, protected_agent)`. Pass `protected_agent` to `Runner.run()`.

When `goal` is omitted, an `InputGuardrail` is injected to infer goal from the first `Runner.run()` input.

### LangChain

```python
from agentwall.integrations.langchain import protect_langchain_agent

wall = protect_langchain_agent(
    executor: AgentExecutor,
    *,
    goal: str | None = None,
    tool_type_map: dict[str, ToolType] | None = None,
    action_map: dict[str, ToolAction] | None = None,
    resource_category_map: dict[str, ResourceCategory] | None = None,
    db: Database | None = None,
    engine: SecurityEngine | None = None,
) -> ProtectedAgent
```

Mutates `executor.tools` in-place. Returns `wall`. Run `executor.invoke()` normally.

When `goal` is omitted, patches `executor.invoke` to capture the first invocation input.

Supports both sync (`@tool def`) and async (`@tool async def`) LangChain tools.

### CrewAI

```python
from agentwall.integrations.crewai import protect_crewai_crew

wall = protect_crewai_crew(
    crew: Crew,
    *,
    goal: str | None = None,
    tool_type_map: dict[str, ToolType] | None = None,
    action_map: dict[str, ToolAction] | None = None,
    resource_category_map: dict[str, ResourceCategory] | None = None,
    db: Database | None = None,
    engine: SecurityEngine | None = None,
) -> ProtectedAgent
```

Mutates all tools on all agents in-place. Returns `wall`. Run `crew.kickoff()` normally.

When `goal` is omitted, patches `crew.kickoff` to infer from `inputs` or first task description.

---

## Types

```python
from agentwall.core.types import (
    ToolType,
    ToolAction,
    ResourceCategory,
    DecisionType,
    RuntimeEvent,
    Decision,
    EvalContext,
    ToolCall,
)
```

### ToolType

```python
class ToolType(str, Enum):
    FILESYSTEM = "filesystem"
    TERMINAL   = "terminal"
    BROWSER    = "browser"
    API        = "api"
    DATABASE   = "database"
    EMAIL      = "email"
```

### ToolAction

```python
class ToolAction(str, Enum):
    READ    = "read"
    WRITE   = "write"
    DELETE  = "delete"
    EXECUTE = "execute"
    REQUEST = "request"
    QUERY   = "query"
    SEND    = "send"
    LIST    = "list"
    CREATE  = "create"
```

### ResourceCategory

```python
class ResourceCategory(str, Enum):
    CODE        = "code"
    CONFIG      = "config"
    CREDENTIALS = "credentials"
    SYSTEM      = "system"
    NETWORK     = "network"
    USER_DATA   = "user_data"
    UNKNOWN     = "unknown"
```

### DecisionType

```python
class DecisionType(str, Enum):
    ALLOW = "allow"
    WARN  = "warn"
    BLOCK = "block"
```

### RuntimeEvent

```python
@dataclass
class RuntimeEvent:
    session_id: str
    goal: str
    tool_type: ToolType
    action: ToolAction
    target: str
    resource_category: ResourceCategory
    metadata: dict
    tool_name: str | None = None
    timestamp: float | None = None
```

### Decision

```python
@dataclass
class Decision:
    type: DecisionType
    risk_score: float
    reason: str
    alignment_score: float | None = None
    llm_used: bool = False
    detector_hits: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

---

## Exceptions

### AgentWallSecurityException

```python
from agentwall.security.exceptions import AgentWallSecurityException

try:
    result = safe_tool(path)
except AgentWallSecurityException as e:
    print(e.decision.type)       # DecisionType.BLOCK
    print(e.decision.risk_score) # float
    print(e.decision.reason)     # str
    print(e.event.tool_name)     # str
```

Raised when a tool call is blocked. Carries `decision: Decision` and `event: RuntimeEvent`.

---

## SecurityEngine

```python
from agentwall.security.engine import SecurityEngine, build_default_engine

# Auto-constructed (recommended)
engine = build_default_engine(db)

# Manual construction
engine = SecurityEngine(
    warn_threshold: float = 30.0,
    block_threshold: float = 70.0,
    provider_chain: ProviderChain | None = None,
    policy_engine: PolicyEngine | None = None,
    detectors: list[BaseDetector] | None = None,
)
```

`build_default_engine(db)`: reads thresholds from DB, constructs `ProviderChain` from configured providers, wires `PolicyEngine`. Returns ready `SecurityEngine`.

---

## ConfigManager

```python
from agentwall.core.config_manager import ConfigManager

mgr = ConfigManager(db)

mgr.set_provider(provider: str, model: str, priority: int = 0) -> None
mgr.get_provider(provider: str) -> ProviderSetting | None
mgr.list_providers_ordered() -> list[ProviderSetting]
mgr.remove_provider(provider: str) -> None
mgr.set_thresholds(low: float, high: float) -> None
mgr.get_thresholds() -> dict  # {"low_threshold": float, "high_threshold": float}
```

---

## Database

```python
from agentwall.storage.database import Database

db = Database()                    # ~/.agentwall/data.db
db = Database(path=Path("my.db")) # custom path

db.close()
```

---

## Inspector REST API

Base URL: `http://127.0.0.1:8080/api`

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sessions` | List sessions with summary (event_count, max_risk, threat_count) |
| GET | `/api/sessions/{id}` | Get session |
| POST | `/api/sessions/{id}/end` | Mark session ended |
| GET | `/api/sessions/{id}/events` | Tool events with evaluations |
| GET | `/api/sessions/{id}/goals` | Goal segments ordered by started_at |

### Policies

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/policies` | List policies ordered by priority DESC |
| POST | `/api/policies` | Create policy (body: `{name, config, priority=0}`) |
| PUT | `/api/policies/{name}` | Update policy config |
| PATCH | `/api/policies/{name}/priority` | Set priority (body: `{priority}`) |
| POST | `/api/policies/{name}/enable` | Enable policy |
| POST | `/api/policies/{name}/disable` | Disable policy |
| DELETE | `/api/policies/{name}` | Delete policy |

### Providers & Config

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/providers` | Configured providers |
| POST | `/api/providers` | Add/update provider |
| DELETE | `/api/providers/{name}` | Remove provider |
| GET | `/api/config/thresholds` | Current thresholds |
| PUT | `/api/config/thresholds` | Update thresholds |

### Export & Misc

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/overview` | Aggregate counts and risk distribution |
| GET | `/api/export` | Export events as JSON (default) or CSV (`?format=csv`). Filter by `?session_id=...` |
| GET | `/api/health` | Health check |
| WS | `/ws/events` | Event-driven WebSocket push. Sends `{"type":"refresh"}` after each tool call. Sends `{"type":"ping"}` every 30s idle. |

Full interactive docs: `http://127.0.0.1:8080/api/docs` when Inspector is running.

---

## ResultAnalyzer

```python
from agentwall.security.result_analyzer import ResultAnalyzer, ResultClassification, AnalysisResult

analysis = ResultAnalyzer().analyze(event, result)
```

`analyze(event: RuntimeEvent, result: Any) -> AnalysisResult` dispatches by `event.tool_type`.

### ResultClassification

```python
class ResultClassification(str, Enum):
    NORMAL                 = "normal"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"
    BULK_DATA_ACCESS        = "bulk_data_access"
    EXTERNAL_TRANSFER       = "external_transfer"
    EMAIL_DISPATCH          = "email_dispatch"
```

### AnalysisResult

```python
@dataclass
class AnalysisResult:
    classification: ResultClassification
    detector_hits: list[str]    # label strings
    post_risk: float            # 0-100, audit signal only — never used to block
    metadata: dict              # hashes, counts, lengths — never actual content
```

Post-execution analysis **never retroactively blocks**. Pre-execution decision is final.

---

## GoalTracker

```python
from agentwall.security.goal_tracker import GoalTracker

tracker = GoalTracker(session_id, db, goal_ref)
tracker.set_goal("new goal", reason="user_update")   # closes active segment, opens new
tracker.maybe_infer("Fix login API")                  # True if goal changed
```

Transition heuristic: full token overlap < 0.4 **AND** resource token overlap < 0.4. Action verbs and stop words stripped before resource comparison.

Thread-safe: `set_goal()` and `maybe_infer()` acquire `threading.RLock`.

### GoalSegmentSchema (Inspector response)

```python
class GoalSegmentSchema(BaseModel):
    id: str
    session_id: str
    goal_text: str
    started_at: float
    ended_at: float | None       # None = active segment
    transition_reason: str       # "initial" | "user_update" | "inference" | "heuristic_transition"
```
