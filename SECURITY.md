# Security Policy

## Threat Model

AgentWall targets **behavioral deviation** in agentic AI systems — specifically, the consequences of prompt injection and goal hijacking rather than the injection vector itself.

### What AgentWall Protects Against

| Threat | Detection Method |
|--------|-----------------|
| Goal hijacking | LLM evaluation of action vs. stated goal |
| Goal drift | GoalDriftDetector: compares tool actions against inferred goal text |
| Sensitive resource access | Pattern matching on file paths and targets |
| Scope expansion | Cross-event resource drift analysis |
| Data exfiltration | External upload and API call detection |
| Tool misuse | Risk scoring by tool type + action |
| Policy violations | User-defined allow/warn/block rules |

### What AgentWall Does Not Protect Against

- Prompt injection content (AgentWall does not inspect LLM inputs or outputs)
- Malicious tool implementations (AgentWall evaluates calls, not implementations)
- Actions taken between `protect_tool` registration and agent execution
- Network-level threats
- Retroactive blocking based on tool results (post-execution analysis is audit-only — see below)

---

## Runtime Security Philosophy

Every tool call is evaluated against the question:

> Is this action consistent with what the user asked the agent to do?

AgentWall does not evaluate prompt content. It evaluates behavior — the sequence of tool calls an agent makes relative to its stated or inferred goal.

**Example:**

```
Goal:  Fix login page bug
OK:    read("login.tsx")
OK:    read("auth.ts")
WARN:  read(".env")            ← credential access off code goal
BLOCK: read("~/.ssh/id_rsa")  ← sensitive target + goal drift signal
```

The blocked action is not inherently malicious — reading SSH keys is normal system administration. It is flagged because it is inconsistent with the stated goal of fixing a login bug.

---

## Evaluation Pipeline

```
Tool call
  → Detectors (pattern matching, zero latency)
      SensitiveResourceDetector   — credential/key file patterns
      ScopeExpansionDetector      — cross-event resource drift
      DataExfiltrationDetector    — external upload patterns
      GoalDriftDetector           — action vs. goal text signals
  → Rule Engine (risk scoring, zero latency)
  → Policy Engine (user-defined rules, zero latency)
  → Threshold routing:
      risk < low_threshold  → ALLOW
      risk < high_threshold → WARN
      risk ≥ high_threshold → LLM Evaluation (only when provider configured)
```

Default thresholds: 30 (warn), 70 (LLM eval). Configurable via `agentwall config`.

Most tool calls never reach the LLM.

---

## Goal Drift Detection

`GoalDriftDetector` emits risk signals when tool actions are inconsistent with the agent's stated or inferred goal. It is part of the default detector pipeline.

| Signal | Condition |
|--------|-----------|
| `goal_drift:credential_access_off_goal` | `resource_category == CREDENTIALS` AND goal contains code-work keywords (fix/build/read/test/…) AND goal does not contain credential keywords (secret/key/token/auth/credential) |
| `goal_drift:sensitive_target_off_goal` | Target matches credential path patterns (`.env`, `id_rsa`, `.pem`, `.aws/`, etc.) AND goal contains code-work keywords AND `resource_category != CREDENTIALS` |
| `goal_drift:unexpected_email` | `tool_type == EMAIL` AND `action == SEND` AND goal does not contain email/send/notify/report/upload/export keywords |
| `goal_drift:system_access_off_goal` | `resource_category == SYSTEM` AND goal contains code-work keywords AND goal does not contain system/config/setup/install/deploy keywords |

Each signal adds 10.0 to the risk score. Multiple signals stack.

Goal drift signals are informational when risk stays below the warn threshold, and can contribute to LLM escalation for ambiguous high-risk events.

---

## API Key Security

API keys for LLM providers are **never stored in**:
- SQLite database
- JSON or YAML configuration files
- Source code
- Log files
- Environment variable exports (within AgentWall)

Keys are stored exclusively in the OS credential store:
- **Windows**: Windows Credential Manager (`keyring` library)
- **macOS**: Keychain
- **Linux**: Secret Service (libsecret or equivalent)

Keys are retrieved at runtime via `keyring.get_password()`.

---

## Data Storage

### What is stored in `~/.agentwall/data.db`

- Session metadata (goal, timestamps)
- Tool event records (tool name, arguments, target, timestamps)
- Evaluation results (decision, risk score, reason, detector hits)
- Post-execution analysis: result classification, detector hits, metadata (content hashes, row counts, lengths — **never actual content**)
- Goal segments (goal text, transition timestamps, transition reason, confidence score)
- Provider configuration (provider name, model, priority) — **no API keys**
- User policies

**Note:** Tool call **arguments** are stored as-is. If your tools accept sensitive values (API keys, passwords) as explicit arguments, those values will appear in the audit trail. Structure sensitive operations to keep secrets out of function arguments.

**Note:** The user **goal** string is stored in plain text. Avoid embedding sensitive information in goal strings.

### What is NOT stored

- API keys or secrets (keyring only)
- LLM conversation content
- Agent internal state
- Actual tool result content (only hashes, counts, and classifications)

---

## Privacy Model

AgentWall is entirely local. No data is sent to any AgentWall service.

When LLM evaluation is triggered, the following is sent to the configured provider:
- User goal (as provided to `protect_*` or inferred automatically)
- Current tool call (name + arguments)
- Up to 5 recent tool calls (names + arguments)

This data is subject to the privacy policy of the configured LLM provider (OpenAI, Anthropic, Groq, DeepSeek, or Ollama).

Ollama runs locally; no data leaves the machine.

---

## Post-Execution Analysis

After a tool call completes, `ResultAnalyzer` classifies the result:

| Classification | Trigger |
|---------------|---------|
| `sensitive_data_exposure` | Credential markers found in filesystem/terminal output |
| `bulk_data_access` | Database query returned > 50 rows |
| `external_transfer` | API write action returned success signals |
| `email_dispatch` | Email tool completed |

Findings are persisted to the audit trail. **Post-execution analysis never retroactively blocks.** The pre-execution ALLOW/WARN/BLOCK decision is final. Post-execution findings are informational only — they enrich the audit trail and can inform future policy rules.

Actual content is never stored. Only hashes (`sha256[:16]`), row counts, output lengths, and classifications are persisted.

---

## Inspector Security

The Inspector backend (`agentwall inspect`) binds to `127.0.0.1:8080` by default. The API has **no authentication**.

**If you bind to `0.0.0.0` (`agentwall inspect --host 0.0.0.0`), the entire audit trail — including session goals, tool arguments, and security decisions — is accessible to anyone who can reach that port.**

Only bind to a non-loopback address in trusted network environments. For remote access, use SSH port forwarding instead.

---

## Auto-Instrumentation Security

Zero-config mode (`import agentwall`) patches framework internals at import time. This is equivalent in effect to calling `protect_*` manually:

- The same `SecurityEngine` evaluates every tool call
- Sessions are created and closed automatically
- API keys remain in OS keyring
- No additional data is collected or transmitted

To disable auto-instrumentation in security-sensitive environments:

```bash
AGENTWALL_AUTO=0 python your_script.py
```

---

## Assumptions

1. The user-provided or inferred `goal` string accurately reflects the user's intent.
2. Tool arguments (file paths, URLs, etc.) are extractable and meaningful.
3. The LLM provider (when configured) is trusted for evaluation purposes.
4. The SQLite database file is not accessible to malicious agents (filesystem isolation is the deployer's responsibility).

---

## Reporting Security Issues

To report a security vulnerability, email: panrwitabrata34t@gmail.com

Do not create public GitHub issues for security vulnerabilities.
