from __future__ import annotations

from agentwall.core.types import DecisionType
from agentwall.providers.base import parse_llm_response


def test_flat_allow():
    d = parse_llm_response('{"decision": "allow", "reason": "safe"}')
    assert d.type == DecisionType.ALLOW
    assert d.reason == "safe"


def test_flat_block():
    d = parse_llm_response('{"decision": "block", "reason": "ssh key"}')
    assert d.type == DecisionType.BLOCK


def test_flat_warn():
    d = parse_llm_response('{"decision": "warn", "reason": "elevated"}')
    assert d.type == DecisionType.WARN


def test_nested_decision_block():
    d = parse_llm_response('{"decision": {"type": "block", "risk": 90}, "reason": "risky"}')
    assert d.type == DecisionType.BLOCK
    assert d.alignment_score == 90.0


def test_nested_decision_allow():
    d = parse_llm_response('{"decision": {"type": "allow", "risk": 10}}')
    assert d.type == DecisionType.ALLOW


def test_nested_decision_warn():
    d = parse_llm_response('{"decision": {"type": "warn", "alignment_score": 55}, "reason": "check"}')
    assert d.type == DecisionType.WARN
    assert d.alignment_score == 55.0


def test_fenced_json_block():
    text = "```json\n{\"decision\": \"warn\", \"reason\": \"elevated\"}\n```"
    d = parse_llm_response(text)
    assert d.type == DecisionType.WARN


def test_fenced_json_no_lang():
    text = "```\n{\"decision\": \"allow\", \"reason\": \"ok\"}\n```"
    d = parse_llm_response(text)
    assert d.type == DecisionType.ALLOW


def test_json_embedded_in_prose():
    text = 'Here is my evaluation: {"decision": "allow", "reason": "looks fine"}. Thanks.'
    d = parse_llm_response(text)
    assert d.type == DecisionType.ALLOW


def test_alignment_score_extracted():
    d = parse_llm_response('{"decision": "allow", "alignment_score": 95, "reason": "ok"}')
    assert d.alignment_score == 95.0


def test_unknown_decision_becomes_block():
    d = parse_llm_response('{"decision": "maybe", "reason": "unsure"}')
    assert d.type == DecisionType.BLOCK


def test_invalid_json_falls_back_to_block():
    d = parse_llm_response("I cannot determine the answer.")
    assert d.type == DecisionType.BLOCK
    assert "Failed" in d.reason


def test_deeply_nested_json_parsed():
    # outer { contains nested object — balanced brace extraction must handle this
    text = '{"decision": "block", "meta": {"key": "val"}, "reason": "deep"}'
    d = parse_llm_response(text)
    assert d.type == DecisionType.BLOCK
    assert d.reason == "deep"
