# AgentWall

**Behavior-based runtime security for AI agents.**

AgentWall is an SDK-first runtime security platform that sits between AI agents and tools, monitoring actions in real time to detect and prevent unsafe behavior.

Unlike prompt scanners and jailbreak detectors, AgentWall focuses on **what agents actually do**, not what users say.

---

## Why AgentWall?

Modern AI agents can:

* Read files
* Execute tools
* Access APIs
* Send emails
* Interact with external systems

A successful prompt injection often matters only because it changes agent behavior.

AgentWall detects:

* Goal Hijacking
* Tool Misuse
* Scope Expansion
* Sensitive Resource Access
* Data Exfiltration
* Unauthorized Actions
* Behavioral Drift
* Goal Drift

---

## How It Works

```text
User Goal
    ↓
AI Agent
    ↓
AgentWall Runtime
    ↓
Tool Execution
```

Before a tool executes, AgentWall evaluates:

* Current goal
* Tool being used
* Resource being accessed
* Recent tool history
* Active policies
* Risk score

AgentWall may:

* ALLOW
* WARN
* BLOCK

depending on risk and alignment.

---

## Installation

```bash
pip install agentwall-security
```

---

## Quick Start — Zero Configuration

```python
import agentwall  # auto-instruments all supported frameworks
```

That's it. No `protect_*` calls. No session management. No goal strings.

AgentWall automatically:

* Detects LangChain, OpenAI Agents SDK, and CrewAI at import time
* Instruments runtimes via lightweight patching
* Creates sessions per agent run
* Infers goals from the agent's first input
* Tracks goal transitions throughout the session
* Classifies tool types from function names and docstrings
* Evaluates runtime actions before execution
* Records audit events to `~/.agentwall/data.db`

### LangChain

```python
import agentwall

executor = AgentExecutor(agent=agent, tools=tools)
result = executor.invoke({"input": "Fix the authentication bug in login.tsx"})
```

### OpenAI Agents SDK

```python
import agentwall

result = await Runner.run(agent, "Fix the authentication bug in login.tsx")
```

### CrewAI

```python
import agentwall

result = crew.kickoff(inputs={"task": "Fix authentication bug"})
```

### Disable Auto-Instrumentation

```bash
AGENTWALL_AUTO=0 python your_script.py
```

---

## Advanced Usage

Use explicit protection functions for full manual control over sessions, goals, and tool type mappings.

```python
from agentwall.integrations.langchain import protect_langchain_agent
from agentwall.core.types import ToolType

wall = protect_langchain_agent(
    executor,
    goal="Fix the authentication bug in login.tsx",
    tool_type_map={
        "read_file": ToolType.FILESYSTEM,
        "list_directory": ToolType.FILESYSTEM,
    },
)

result = executor.invoke({"input": "Read login.tsx and find the bug."})
wall.end_session()
```

See [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) for full advanced usage examples.

---

## Key Features

### Zero Configuration

One import enables automatic protection for all supported frameworks with no code changes required.

### Automatic Goal Inference

Goals are inferred from agent inputs automatically. Goal history, transitions, and confidence are recorded throughout the session.

### Goal Drift Detection

Detects when agent actions deviate from the inferred or stated goal — a key signal for prompt injection compromise.

### Automatic Tool Classification

Tools are classified by type (filesystem, terminal, API, database, email, browser) from function names and docstrings. No manual `tool_type_map` required.

### Runtime Security

Behavior-based protection. Evaluates actions before execution. Raises `AgentWallSecurityException` on BLOCK.

### Goal Tracking

Tracks goal segments throughout a session. Detects transitions using a two-signal heuristic (token overlap + resource token overlap). Records confidence per segment.

### Policy Engine

Create custom allow/warn/block rules targeting specific tool types, actions, resource categories, and path patterns.

### Post-Execution Analysis

Classifies tool outcomes after execution. Detects sensitive data exposure, bulk data access, external transfers, and email dispatch. Audit-only — never retroactively blocks.

### Inspector

Native desktop security console. Launch with:

```bash
agentwall inspect
```

Features:

* Session Timeline
* Goal Timeline (goal segments with confidence and transition reasons)
* Security Decisions
* Risk Scores
* Detector Results
* Policy Management
* Provider Configuration
* Export (JSON/CSV)

### Provider Agnostic

Supports:

* OpenAI
* Anthropic
* Groq
* DeepSeek
* Ollama

### Framework Integrations

Supports:

* OpenAI Agents SDK
* LangChain
* CrewAI

---

## CLI

```bash
agentwall version
agentwall doctor
agentwall config
agentwall inspect
```

---

## Security Model

AgentWall focuses on:

* Runtime behavior
* Tool usage
* Resource access
* Goal alignment

AgentWall does **not** primarily operate as:

* Prompt firewall
* Jailbreak detector
* Content moderation system

It evaluates the consequences of agent actions relative to the user's stated or inferred goal.

---

## Supported Storage

Local-only architecture.

Uses:

* SQLite (`~/.agentwall/data.db`)
* OS Keyring (API keys only)
* Local FastAPI backend
* Local Inspector UI

No cloud dependency required.

---

## Architecture

```text
Auto Instrumentation Layer
    ↓
Goal Inference & Tracking
    ↓
Security Engine
    ↓
Policy Evaluation
    ↓
Risk Assessment + Goal Drift Detection
    ↓
Optional LLM Evaluation
    ↓
Decision (ALLOW / WARN / BLOCK)
    ↓
Tool Execution
    ↓
Post-Execution Analysis
```

---

## Documentation

* [Installation Guide](INSTALLATION_GUIDE.md) — installation, configuration, framework integration
* [Architecture](ARCHITECTURE.md) — internal design and component details
* [API Reference](API_REFERENCE.md) — all public APIs
* [Security Policy](SECURITY.md) — threat model and privacy
* [Testing Guide](TESTING_GUIDE.md) — running and writing tests
* [Changelog](CHANGELOG.md) — version history

---

## License

MIT License.

---

## Status

**v0.2.0**

Production-ready.

Open-source and self-hosted.
