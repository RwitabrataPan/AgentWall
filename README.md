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

## Key Features

### Runtime Security

Behavior-based protection for AI agents.

### Goal Tracking

Automatically infers and tracks goals throughout a session.

### Policy Engine

Create custom allow/warn/block rules.

### Post-Execution Analysis

Classifies tool outcomes and records security-relevant findings without storing sensitive outputs.

### Inspector

Native desktop security console powered by PyWebView.

Launch with:

```bash
agentwall inspect
```

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

## Installation

```bash
pip install agentwall-security
```

---

## Quick Start

### OpenAI Agents SDK

```python
from agentwall import protect_agent

agent = protect_agent(agent)

result = await Runner.run(
    agent,
    "Build a FastAPI CRUD API"
)
```

### LangChain

```python
from agentwall.integrations import protect_langchain_agent

executor = protect_langchain_agent(executor)
```

### CrewAI

```python
from agentwall.integrations import protect_crewai_crew

crew = protect_crewai_crew(crew)
```

---

## Inspector

Launch the desktop Inspector:

```bash
agentwall inspect
```

Features:

* Session Timeline
* Security Decisions
* Risk Scores
* Goal Segments
* Detector Results
* Policy Management
* Provider Configuration
* Export (JSON/CSV)

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

Instead it evaluates the consequences of agent actions.

---

## Supported Storage

Local-only architecture.

Uses:

* SQLite
* OS Keyring
* Local FastAPI backend
* Local Inspector UI

No cloud dependency required.

---

## Architecture

```text
Goal Tracking
        ↓
Security Engine
        ↓
Policy Evaluation
        ↓
Risk Assessment
        ↓
Optional LLM Evaluation
        ↓
Decision
        ↓
Tool Execution
        ↓
Post-Execution Analysis
```

---

## Documentation

* Installation Guide
* Architecture Guide
* API Reference
* Security Guide
* Testing Guide

See the repository documentation for details.

---

## License

MIT License.

---

## Status

**v0.1.0**

Production-ready initial release.

Open-source and self-hosted.
