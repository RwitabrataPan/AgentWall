# AgentWall

## Project Overview

AgentWall = AI Agent Runtime Security Platform.

Protects agentic AI systems. Monitors runtime behavior. Evaluates whether agent actions align with user's stated objective.

NOT chatbot. NOT prompt scanner. NOT jailbreak detector.

Detects consequences of prompt injection, not injection itself.

Behaviors AgentWall detects:

* Goal Hijacking
* Tool Misuse
* Scope Expansion
* Sensitive Resource Access
* Data Exfiltration
* Plan Deviation
* Unauthorized Actions

---

## Core Principle

AgentWall sits between AI agents and tools.

Architecture:

User Goal
→ AI Agent
→ AgentWall Runtime
→ Tool Execution

Evaluates actions before execution. May:

* Allow
* Warn
* Block

based on risk and alignment.

---

## Product Philosophy

SDK-first product. SDK = primary product. Inspector = supporting observability tool.

SDK must function completely without Inspector.

Inspector = local interface for:

* Configuration
* Auditing
* Investigation
* Observability

---

## Distribution

Repository:

Private GitHub Repository

Package:

Public PyPI Package

Installation:

pip install agentwall

Configuration:

agentwall config

Inspector:

agentwall inspect

Diagnostics:

agentwall doctor

---

## Supported Agent Frameworks

Initial integrations:

* OpenAI Agents SDK
* LangChain
* CrewAI

Design for extensibility.

---

## Supported Providers

Provider-agnostic.

Initial providers:

* OpenAI
* Anthropic
* Groq
* DeepSeek
* Ollama

All providers implement shared interface:

BaseEvaluator

OpenAIEvaluator

AnthropicEvaluator

GroqEvaluator

DeepSeekEvaluator

OllamaEvaluator

Never couple to single vendor.

---

## API Key Management

API Keys NEVER stored in:

* SQLite
* JSON
* YAML
* Source Code
* Logs

Use Python keyring only.

Secure storage:

Windows:

* Windows Credential Manager

macOS:

* Keychain

Linux:

* Secret Service

Provider config may live in SQLite. Secrets only in OS credential store.

---

## Storage Architecture

Use SQLite.

Store:

* Sessions
* Tool Events
* Evaluations
* Policies
* Provider Settings

No:

* Redis
* Kafka
* Elasticsearch
* External Databases

Keep lightweight.

---

## Runtime Security Philosophy

Target = behavioral deviation, not prompt injection.

Evaluates:

* What user asked
* What agent doing
* Whether behavior justified

Example:

Goal:
Fix login page bug

Expected:

Read login.tsx

Expected:

Read auth.ts

Unexpected:

Read ~/.ssh/id_rsa

AgentWall flags unexpected behavior.

---

## Evaluation Pipeline

Tool Call
→ Rule Engine
→ Risk Assessment
→ Optional LLM Evaluation
→ Decision

Decision Types:

ALLOW

WARN

BLOCK

---

## Performance Requirements

Performance = first-class requirement.

Slow security product = failed security product.

Most actions must never invoke LLM. Rules evaluate first. Only suspicious/ambiguous actions escalate.

Target Flow:

Tool Call
→ Rule Engine
→ Risk Score

Risk < 30
→ Allow

Risk 30-70
→ Warn

Risk > 70
→ LLM Evaluation

Thresholds configurable.

---

## LLM Usage Rules

Send only:

* User Goal
* Recent Tool History
* Current Action

Never send:

* Entire Conversations
* Entire Repositories
* Large Context Windows

Minimize cost, latency, tokens.

---

## Inspector Requirements

Launched via:

agentwall inspect

Opens as native desktop window (PyWebView). No browser navigation required.

Backend runs locally at http://localhost:8080 (internal). Accessible via --browser flag for headless environments.

Optional. Not required for SDK operation.

Purpose:

* Timeline Analysis
* Threat Investigation
* Policy Management
* Provider Configuration
* Evaluation Review

Implementation:

* PyWebView wraps existing React UI + FastAPI backend
* FastAPI starts in daemon thread
* PyWebView window blocks until closed
* No Electron, no Tauri, no Qt

---

## CLI Requirements

Required commands:

agentwall config

agentwall inspect

agentwall doctor

agentwall version

Keep simple. No command bloat.

---

## UI Philosophy

Inspector = developer tool.

Prioritize:

* Clarity
* Speed
* Auditability

No:

* Marketing Pages
* SaaS Dashboards
* User Management
* Billing Screens

---

## Engineering Rules

Prefer:

* Simple Architecture
* Modular Design
* Strong Typing
* Maintainable Code
* Test Coverage

Avoid:

* Microservices
* Premature Optimization
* Unnecessary Abstractions
* Enterprise Feature Creep

Build focused runtime security SDK.

---

## Goal Inference

`goal` parameter optional in all `protect_*` functions.

When omitted, goal inferred automatically:

OpenAI Agents SDK:

* InputGuardrail injected into `agent.input_guardrails`
* Fires before first LLM call
* Captures `Runner.run()` input string

LangChain:

* `executor.invoke` patched after wrapping
* Extracts from `input`, `query`, `task` keys or first dict value

CrewAI:

* `crew.kickoff` patched after wrapping
* Extracts from `inputs` dict first value
* Fallback: first `task.description`

Explicit `goal="..."` still works. No inference patch when goal provided.

Goal stored in DB via `SessionManager.update_goal()`. All wrapped tool closures see updated goal via shared `_goal_ref` list.

---

## Success Criteria

Developer should:

pip install agentwall

agentwall config

Integrate:

agent = protect_agent(agent)

Run app. Launch:

agentwall inspect

See:

* Sessions
* Tool Calls
* Security Decisions
* Risk Scores
* Detector Results
* Audit Trails

No cloud required. That = successful AgentWall implementation.