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
