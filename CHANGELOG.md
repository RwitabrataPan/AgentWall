# Changelog

All notable changes to AgentWall are documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

---

# [0.1.2] - 2026-06-24

## Fixed

### Version Management

- Fixed CLI version reporting.
- Package version now resolves from installed package metadata.
- Eliminated version mismatch between PyPI package metadata and CLI output.

### Documentation

- Updated installation instructions to use:

```bash
pip install agentwall-security
```

- Clarified optional dependency installation.
- Improved Inspector documentation.
- Improved LLM evaluation documentation.
- Fixed README and installation guide inconsistencies.

### Packaging

- Verified wheel and source distribution contents.
- Corrected package metadata consistency.
- Confirmed clean installation from PyPI in a fresh environment.

---

# [0.1.1] - 2026-06-24

## Fixed

### Documentation

- Corrected installation guide formatting.
- Updated package installation examples.
- Improved framework integration examples.
- Fixed PyPI documentation rendering issues.

### Release Hygiene

- Repository cleanup and packaging audit completed.
- Removed stale documentation references.
- Improved release readiness documentation.

---

# [0.1.0] - 2026-06-24

Initial public release.

## Added

### Runtime Security Engine

- Multi-stage runtime security evaluation pipeline:
  - Detectors
  - Rules
  - Policies
  - Threshold evaluation
  - Optional LLM evaluation

- Sensitive Resource Detection
- Scope Expansion Detection
- Data Exfiltration Detection

### Policy Engine

- User-defined allow, warn, and block policies.
- Runtime policy enforcement.
- Policy priority support.
- Dynamic policy updates.

### Goal Tracking

- Dynamic goal tracking across agent sessions.
- Goal inference from framework entry points.
- Goal transition detection.
- Goal segmentation and persistence.

### Post-Execution Analysis

- Tool output classification.
- Sensitive data exposure detection.
- Bulk data access detection.
- External transfer detection.
- Email dispatch detection.

### Inspector

#### Backend

- FastAPI-powered Inspector API.
- Session management APIs.
- Event streaming support.
- Policy management APIs.
- Goal tracking APIs.

#### Frontend

- React-based Inspector UI.
- Session timeline visualization.
- Policy management interface.
- Provider management interface.
- Security event monitoring.

#### Desktop Support

- PyWebView desktop application.
- Browser mode support.

### Framework Integrations

#### OpenAI Agents SDK

- Agent protection wrapper.
- Tool interception.
- Goal inference support.

#### LangChain

- AgentExecutor protection.
- Tool interception.
- Goal inference support.

#### CrewAI

- Crew protection wrapper.
- Tool interception.
- Goal inference support.

### LLM Providers

#### OpenAI

- GPT-4o
- GPT-4o Mini
- GPT-4 Turbo
- GPT-3.5 Turbo

#### Anthropic

- Claude Opus
- Claude Sonnet
- Claude Haiku

#### Groq

- Llama models
- Gemma models

#### DeepSeek

- DeepSeek Chat
- DeepSeek Reasoner

#### Ollama

- Local inference support.

### Storage

- SQLite-based local storage.
- Session tracking.
- Tool event tracking.
- Evaluation persistence.
- Goal persistence.
- Policy persistence.

### Security

- OS keyring integration.
- No plaintext API key storage.
- Local-first architecture.
- Audit trail generation.

### Command Line Interface

Commands:

```bash
agentwall version
agentwall doctor
agentwall config
agentwall inspect
```

---

# Unreleased

## Planned for v0.2.0

### Improvements

- Inspector authentication.
- Full async LangChain coverage.
- Environment-variable database configuration.
- Enhanced goal transition reasoning.
- Additional observability features.
- Expanded provider support.

### Known Limitations

- Goal transition detection currently relies on heuristic overlap analysis.
- ScopeExpansionDetector requires warmup history.
- Inspector authentication is not yet implemented.