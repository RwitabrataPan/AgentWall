# Contributing to AgentWall

---

## Development Setup

```bash
git clone https://github.com/panrw/agentwall
cd agentwall
pip install -e ".[dev,integrations]"
```

## Running Tests

```bash
pytest tests/
pytest tests/ -v                        # verbose
pytest tests/integration/               # integration tests only
pytest tests/ -k "test_engine"          # filter by name
```

**Current count: 301 tests, all passing.**

The test suite disables zero-config auto-instrumentation via `conftest.py`:

```python
# tests/conftest.py (top of file, before any agentwall import)
import os
os.environ["AGENTWALL_AUTO"] = "0"
```

This prevents auto-mode from wrapping framework tools at import time and conflicting with explicit `protect_*` calls in integration tests. New tests must not remove or bypass this.

If you are writing tests specifically for auto-mode behavior, use `monkeypatch.delenv("AGENTWALL_AUTO")` inside the test itself.

## Code Style

- Python 3.12+
- Strong typing (`from __future__ import annotations`, full type hints)
- No unnecessary abstractions — solve the problem at hand
- No speculative features

## Architecture Rules

From CLAUDE.md:
- SDK-first: SDK must work without Inspector
- No cloud dependencies
- API keys in OS keyring only
- SQLite only (no Redis, Elasticsearch, etc.)
- Provider-agnostic evaluation

## Submitting Changes

1. Fork the repository
2. Create a branch: `git checkout -b fix/description`
3. Write tests for any changed behavior
4. Ensure all tests pass: `pytest tests/`
5. Open a pull request

## Reporting Bugs

Open a GitHub issue with:
- Python version
- AgentWall version (`agentwall version`)
- Framework and version
- Minimal reproduction
- Expected vs. actual behavior

## Security Issues

See [SECURITY.md](SECURITY.md). Do not create public issues for vulnerabilities.
