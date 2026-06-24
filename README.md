# AgentWall

**AI Agent Runtime Security Platform**

AgentWall protects agentic AI systems by monitoring runtime behavior and evaluating whether agent actions align with the user's stated objective.

Not a chatbot filter. Not a prompt scanner. Not a jailbreak detector.

AgentWall detects the **consequences** of prompt injection, not the injection itself.

---

## What AgentWall Does

AgentWall sits between AI agents and tools, evaluating each tool call before execution.

```
User Goal
→ AI Agent
→ AgentWall Runtime
→ Tool Execution
```

For every tool call, AgentWall evaluates:
- What the user asked the agent to do
- What the agent is currently attempting
- Whether this action is consistent with the goal

Decision: **ALLOW**, **WARN**, or **BLOCK**.

### Behaviors Detected

| Behavior | Description |
|----------|-------------|
| Goal Hijacking | Agent pursues objective different from user goal |
| Tool Misuse | Tools invoked outside intended purpose |
| Scope Expansion | Agent accesses resources unrelated to task |
| Sensitive Resource Access | Credential files, SSH keys, system config |
| Data Exfiltration | External uploads, suspicious API calls |
| Plan Deviation | Actions inconsistent with agent instructions |
| Unauthorized Actions | Operations outside policy |

---

## Installation

```bash
pip install agentwall
```

### Framework Integrations

```bash
pip install agentwall[openai-agents]   # OpenAI Agents SDK
pip install agentwall[langchain]       # LangChain
pip install agentwall[crewai]          # CrewAI
pip install agentwall[integrations]    # All frameworks
```

---

## Quick Start

### 1. Configure a Security Provider

```bash
agentwall config
```

Follow the interactive wizard to add an LLM provider for high-risk evaluation.

### 2. Run Health Check

```bash
agentwall doctor
```

### 3. Protect Your Agent

#### OpenAI Agents SDK

```python
from agents import Agent, Runner, function_tool
from agentwall.integrations.openai_agents import protect_openai_agent
from agentwall.core.types import ToolType

@function_tool
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

agent = Agent(
    name="code-assistant",
    instructions="You help fix bugs by reading source code.",
    tools=[read_file],
    model="gpt-4o-mini",
)

wall, protected_agent = protect_openai_agent(
    agent,
    goal="Fix the authentication bug in login.tsx",
    tool_type_map={"read_file": ToolType.FILESYSTEM},
)

result = await Runner.run(protected_agent, "Read login.tsx")
wall.end_session()
```

#### LangChain

```python
from langchain_core.tools import tool
from agentwall.integrations.langchain import protect_langchain_agent
from agentwall.core.types import ToolType

@tool
def read_file(path: str) -> str:
    """Read a file."""
    with open(path) as f:
        return f.read()

executor = AgentExecutor(agent=agent, tools=[read_file])

wall = protect_langchain_agent(
    executor,
    goal="Fix login bug",
    tool_type_map={"read_file": ToolType.FILESYSTEM},
)
result = executor.invoke({"input": "Read login.tsx"})
wall.end_session()
```

#### CrewAI

```python
from crewai import Agent as CrewAgent, Task, Crew
from crewai.tools import tool
from agentwall.integrations.crewai import protect_crewai_crew
from agentwall.core.types import ToolType

@tool("Read File")
def read_file(path: str) -> str:
    """Read a file."""
    with open(path) as f:
        return f.read()

agent = CrewAgent(role="Developer", goal="Fix bugs", tools=[read_file])
task = Task(description="Fix login bug", expected_output="Fixed code", agent=agent)
crew = Crew(agents=[agent], tasks=[task])

wall = protect_crewai_crew(
    crew,
    goal="Fix login bug",
    tool_type_map={"Read File": ToolType.FILESYSTEM},
)
result = crew.kickoff()
wall.end_session()
```

#### Direct SDK (any framework)

```python
from agentwall import protect_agent, protect_tool
from agentwall.core.types import ToolType, ToolAction

wall = protect_agent(my_agent, goal="Fix login bug")

safe_read = wall.protect_tool(
    read_file,
    tool_type=ToolType.FILESYSTEM,
    action=ToolAction.READ,
)
```

---

## Goal Inference

`goal` is optional in all `protect_*` functions. When omitted, AgentWall infers the goal automatically:

| Framework | Inference trigger | Source |
|-----------|------------------|--------|
| OpenAI Agents SDK | Before first LLM call (InputGuardrail) | `Runner.run()` input |
| LangChain | On `executor.invoke()` | `input`, `query`, `task` keys |
| CrewAI | On `crew.kickoff()` | `inputs` dict or first task description |

---

## Inspector

Launch the AgentWall Inspector to review sessions, tool calls, and security decisions:

```bash
agentwall inspect
```

Opens a native desktop window (PyWebView) with:
- Session timeline
- Tool call audit trail
- Risk scores and detector hits
- Policy management
- Provider configuration

Headless/server environments:

```bash
agentwall inspect --browser
```

---

## CLI Reference

```bash
agentwall version              # Print version
agentwall doctor               # Check installation health
agentwall config               # Interactive configuration wizard
agentwall config --provider openai --model gpt-4o-mini --priority 1
agentwall config --low-threshold 30 --high-threshold 70
agentwall config --status      # Show provider health
agentwall inspect              # Launch desktop Inspector
agentwall inspect --browser    # Open Inspector in browser
agentwall inspect --port 9090  # Custom port
```

---

## Provider Setup

AgentWall uses LLM providers to evaluate high-risk actions. API keys are stored in the OS keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service) — never in files or databases.

### Supported Providers

| Provider | Models |
|---------|--------|
| openai | gpt-4o, gpt-4o-mini, gpt-4-turbo |
| anthropic | claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5 |
| groq | llama-3.3-70b-versatile, llama-3.1-8b-instant |
| deepseek | deepseek-chat, deepseek-reasoner |
| ollama | llama3.2, mistral, gemma2 (local, no key) |

Configure via wizard:

```bash
agentwall config
```

Or non-interactively:

```bash
agentwall config --provider openai --model gpt-4o-mini --priority 1
```

Then enter the API key when prompted.

---

## Evaluation Pipeline

Every tool call passes through:

1. **Detectors** — pattern-based behavioral analysis (no LLM)
2. **Rule Engine** — risk scoring by tool type and resource category
3. **Policy Engine** — user-defined allow/warn/block rules
4. **Threshold Routing** — risk < 30 → ALLOW, risk 30-70 → WARN, risk ≥ 70 → LLM evaluation
5. **LLM Evaluation** — triggered only for high-risk events when a provider is configured

Most actions never reach the LLM. Performance is the first-class requirement.

---

## Architecture

```
protect_*(agent)
    └── ProtectedAgent
            └── ToolInterceptor
                    └── SecurityEngine
                            ├── Detectors (pattern matching, no LLM)
                            ├── Rule Engine (risk scoring)
                            ├── Policy Engine (user policies)
                            └── ProviderChain (LLM evaluation, optional)
                    └── EventManager → SQLite
```

Storage: local SQLite at `~/.agentwall/data.db`. No cloud, no external services.

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed documentation.

---

## Security Model

AgentWall evaluates **behavioral deviation**, not prompt content. It asks:

> Is this tool call consistent with what the user asked the agent to do?

**Example:**

- Goal: `Fix login page bug`
- Expected: read `login.tsx`, read `auth.ts`
- Unexpected: read `~/.ssh/id_rsa` → **BLOCKED**

See [SECURITY.md](SECURITY.md) for full threat model.

---

## Known Limitations

- First 3-5 tool calls in a session have limited scope expansion detection (ScopeExpansionDetector requires history)
- `ProtectedAgent.run()` raises when used with framework integrations (use framework-native run methods)
- LLM evaluation requires a configured provider; without one, risk ≥ threshold → BLOCK
- Post-execution analysis classifies tool results (sensitive content, bulk data, transfers) but never retroactively blocks — pre-execution decision is final

See [IMPLEMENTATION_WORKFLOW.md](IMPLEMENTATION_WORKFLOW.md) Section 14 for full list.

---

## Release Status

**v0.1.0 — Alpha**

AgentWall is functional and tested. Not yet recommended for production workloads.

See [CHANGELOG.md](CHANGELOG.md) for version history.

---

## License

MIT License. See [LICENSE](LICENSE).
