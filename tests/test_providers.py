"""Provider layer tests — mocks all external API calls."""
from unittest.mock import MagicMock, patch

import pytest

from agentwall.core.types import DecisionType, EvalContext, ToolCall
from agentwall.providers.base import ProviderHealth, ProviderStatus, build_prompt, parse_llm_response
from agentwall.providers.chain import ProviderChain


# --- parse_llm_response ---

def test_parse_allow():
    d = parse_llm_response('{"decision": "allow", "reason": "safe action"}')
    assert d.type == DecisionType.ALLOW
    assert d.reason == "safe action"


def test_parse_block():
    d = parse_llm_response('{"decision": "block", "reason": "ssh key access"}')
    assert d.type == DecisionType.BLOCK


def test_parse_warn():
    d = parse_llm_response('{"decision": "warn", "reason": "shell command"}')
    assert d.type == DecisionType.WARN


def test_parse_invalid_json_blocks():
    d = parse_llm_response("I cannot determine the answer.")
    assert d.type == DecisionType.BLOCK
    assert "Failed" in d.reason


def test_parse_unknown_decision_blocks():
    d = parse_llm_response('{"decision": "unknown", "reason": "x"}')
    assert d.type == DecisionType.BLOCK


# --- build_prompt ---

def test_build_prompt_contains_goal():
    call = ToolCall("read_file", {"path": "login.tsx"}, "s1")
    ctx = EvalContext("Fix login bug", call)
    prompt = build_prompt(ctx)
    assert "Fix login bug" in prompt
    assert "read_file" in prompt


def test_build_prompt_limits_history():
    call = ToolCall("bash", {}, "s1")
    history = [ToolCall(f"tool_{i}", {}, "s1") for i in range(20)]
    ctx = EvalContext("goal", call, recent_history=history)
    prompt = build_prompt(ctx)
    assert prompt.count("tool_") <= 5


# --- ProviderChain ---

def _make_mock_evaluator(decision_type: DecisionType, provider: str = "mock"):
    from agentwall.providers.base import BaseEvaluator
    from agentwall.core.types import Decision

    class MockEvaluator(BaseEvaluator):
        PROVIDER = provider
        DEFAULT_MODEL = "mock"
        MODELS = ["mock"]

        def evaluate(self, ctx):
            return Decision(decision_type, 75.0, "mock decision")

        def health_check(self):
            return ProviderStatus(self.PROVIDER, ProviderHealth.HEALTHY, "mock")

    return MockEvaluator()


def test_chain_uses_primary():
    chain = ProviderChain([_make_mock_evaluator(DecisionType.ALLOW)])
    call = ToolCall("bash", {}, "s1")
    ctx = EvalContext("goal", call)
    d = chain.evaluate(ctx)
    assert d.type == DecisionType.ALLOW


def test_chain_fallback_on_failure():
    from agentwall.providers.base import BaseEvaluator
    from agentwall.core.types import Decision

    class FailingEvaluator(BaseEvaluator):
        PROVIDER = "fail"
        DEFAULT_MODEL = "x"
        MODELS = ["x"]

        def evaluate(self, ctx):
            raise RuntimeError("API error")

        def health_check(self):
            return ProviderStatus("fail", ProviderHealth.UNAVAILABLE, "x")

    chain = ProviderChain([FailingEvaluator(), _make_mock_evaluator(DecisionType.WARN, "fallback")])
    call = ToolCall("bash", {}, "s1")
    d = chain.evaluate(EvalContext("goal", call))
    assert d.type == DecisionType.WARN


def test_chain_all_fail_returns_block():
    from agentwall.providers.base import BaseEvaluator

    class FailingEvaluator(BaseEvaluator):
        PROVIDER = "fail"
        DEFAULT_MODEL = "x"
        MODELS = ["x"]

        def evaluate(self, ctx):
            raise RuntimeError("down")

        def health_check(self):
            return ProviderStatus("fail", ProviderHealth.UNAVAILABLE, "x")

    chain = ProviderChain([FailingEvaluator()])
    d = chain.evaluate(EvalContext("goal", ToolCall("x", {}, "s1")))
    assert d.type == DecisionType.BLOCK
    assert "All providers failed" in d.reason


def test_chain_requires_at_least_one():
    with pytest.raises(ValueError):
        ProviderChain([])


def test_chain_providers_property():
    chain = ProviderChain([
        _make_mock_evaluator(DecisionType.ALLOW, "openai"),
        _make_mock_evaluator(DecisionType.ALLOW, "anthropic"),
    ])
    assert chain.providers == ["openai", "anthropic"]
