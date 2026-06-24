"""Tests for build_default_engine, DB-sourced thresholds, history in EvalContext,
and optional goal in protect_agent."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentwall.core.types import (
    Decision,
    DecisionType,
    ResourceCategory,
    RuntimeEvent,
    ToolAction,
    ToolType,
)
from agentwall.storage.database import Database


def _make_db():
    tmpdir = tempfile.mkdtemp(prefix="aw_test_")
    return Database(path=Path(tmpdir) / "test.db"), tmpdir


def _event(target: str = "/home/user/file.py") -> RuntimeEvent:
    return RuntimeEvent(
        session_id="s1",
        goal="fix login bug",
        tool_type=ToolType.FILESYSTEM,
        action=ToolAction.READ,
        target=target,
        resource_category=ResourceCategory.UNKNOWN,
        metadata={},
        tool_name="read_file",
    )


# ── build_default_engine: thresholds from DB ──────────────────────────────────

def test_build_default_engine_uses_db_thresholds():
    """Thresholds written to DB are loaded into SecurityEngine."""
    from agentwall.core.config_manager import ConfigManager
    from agentwall.security.engine import build_default_engine

    db, tmpdir = _make_db()
    try:
        ConfigManager(db).set_thresholds(10.0, 50.0)
        engine = build_default_engine(db)
        assert engine._warn == 10.0
        assert engine._block == 50.0
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_build_default_engine_default_thresholds_when_none_set():
    """Without DB thresholds, defaults 30.0/70.0 are used."""
    from agentwall.security.engine import build_default_engine

    db, tmpdir = _make_db()
    try:
        engine = build_default_engine(db)
        assert engine._warn == 30.0
        assert engine._block == 70.0
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── build_default_engine: provider chain ──────────────────────────────────────

def test_build_default_engine_no_providers_chain_is_none():
    """Empty provider config → chain=None, high-risk events BLOCK with no LLM call."""
    from agentwall.security.engine import build_default_engine

    db, tmpdir = _make_db()
    try:
        engine = build_default_engine(db)
        assert engine._chain is None
        terminal = RuntimeEvent(
            session_id="s1",
            goal="fix login",
            tool_type=ToolType.TERMINAL,
            action=ToolAction.EXECUTE,
            target="rm -rf /",
            resource_category=ResourceCategory.UNKNOWN,
            metadata={},
        )
        d = engine.evaluate(terminal)
        assert d.type == DecisionType.BLOCK
        assert "no LLM evaluator" in d.reason
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_build_default_engine_loads_chain_when_provider_configured():
    """When a provider is configured in DB, chain is constructed."""
    from agentwall.core.config_manager import ConfigManager
    from agentwall.security.engine import build_default_engine

    db, tmpdir = _make_db()
    try:
        ConfigManager(db).set_provider("openai", "gpt-4o-mini", priority=1)

        mock_evaluator = MagicMock()
        mock_evaluator.PROVIDER = "openai"
        mock_evaluator.NEEDS_API_KEY = False
        mock_evaluator.evaluate.return_value = Decision(
            type=DecisionType.WARN,
            risk_score=55.0,
            reason="LLM says warn",
        )

        with patch("agentwall.providers.registry.OpenAIEvaluator", return_value=mock_evaluator), \
             patch("agentwall.providers.registry.get_api_key", return_value="fake-key"):
            engine = build_default_engine(db)

        assert engine._chain is not None
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── EvalContext recent_history ─────────────────────────────────────────────────

def test_llm_evalcontext_receives_history():
    """SecurityEngine passes history as recent_history into EvalContext for LLM."""
    from agentwall.security.engine import SecurityEngine

    captured_ctx = {}

    def _fake_evaluate(ctx):
        captured_ctx["ctx"] = ctx
        return Decision(DecisionType.WARN, 75.0, "ok")

    mock_chain = MagicMock()
    mock_chain.evaluate.side_effect = _fake_evaluate

    engine = SecurityEngine(
        warn_threshold=0.0,
        block_threshold=0.0,
        provider_chain=mock_chain,
    )

    history = [
        RuntimeEvent(
            session_id="s1",
            goal="fix login",
            tool_type=ToolType.FILESYSTEM,
            action=ToolAction.READ,
            target="/app/login.tsx",
            resource_category=ResourceCategory.CODE,
            metadata={"args": ["/app/login.tsx"], "kwargs": {}},
            tool_name="read_file",
        ),
        RuntimeEvent(
            session_id="s1",
            goal="fix login",
            tool_type=ToolType.FILESYSTEM,
            action=ToolAction.READ,
            target="/app/auth.ts",
            resource_category=ResourceCategory.CODE,
            metadata={"args": ["/app/auth.ts"], "kwargs": {}},
            tool_name="read_file",
        ),
    ]

    engine.evaluate(_event(), history)

    assert mock_chain.evaluate.called
    ctx = captured_ctx["ctx"]
    assert len(ctx.recent_history) == 2
    assert ctx.recent_history[0].name == "read_file"
    assert ctx.recent_history[0].arguments["target"] == "/app/login.tsx"
    assert ctx.recent_history[1].arguments["target"] == "/app/auth.ts"


def test_llm_evalcontext_empty_history_when_no_prior_events():
    """No prior events → recent_history is empty list (not None)."""
    from agentwall.security.engine import SecurityEngine

    captured_ctx = {}

    def _fake_evaluate(ctx):
        captured_ctx["ctx"] = ctx
        return Decision(DecisionType.ALLOW, 5.0, "ok")

    mock_chain = MagicMock()
    mock_chain.evaluate.side_effect = _fake_evaluate

    engine = SecurityEngine(
        warn_threshold=0.0,
        block_threshold=0.0,
        provider_chain=mock_chain,
    )

    engine.evaluate(_event(), [])

    ctx = captured_ctx["ctx"]
    assert ctx.recent_history == []


# ── protect_agent optional goal ────────────────────────────────────────────────

def test_protect_agent_optional_goal():
    """protect_agent works with no goal argument — session created with empty goal."""
    from agentwall import protect_agent
    from agentwall.security.engine import SecurityEngine

    db, tmpdir = _make_db()
    try:
        engine = SecurityEngine()

        class _Stub:
            def run(self): pass

        wall = protect_agent(_Stub(), db=db, engine=engine)
        assert wall.goal == ""
        wall.end_session()
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_protect_agent_explicit_goal_still_works():
    """protect_agent with explicit goal stores it correctly."""
    from agentwall import protect_agent
    from agentwall.security.engine import SecurityEngine

    db, tmpdir = _make_db()
    try:
        engine = SecurityEngine()

        class _Stub:
            def run(self): pass

        wall = protect_agent(_Stub(), goal="fix auth bug", db=db, engine=engine)
        assert wall.goal == "fix auth bug"
        wall.end_session()
    finally:
        db.close()
        shutil.rmtree(tmpdir, ignore_errors=True)
