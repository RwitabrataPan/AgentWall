from agentwall.core.config_manager import ConfigManager
from agentwall.storage.database import Database


def test_get_default_thresholds(db: Database):
    mgr = ConfigManager(db)
    t = mgr.get_thresholds()
    assert t["low_threshold"] == 30.0
    assert t["high_threshold"] == 70.0


def test_set_thresholds(db: Database):
    mgr = ConfigManager(db)
    mgr.set_thresholds(25.0, 65.0)
    t = mgr.get_thresholds()
    assert t["low_threshold"] == 25.0
    assert t["high_threshold"] == 65.0


def test_set_and_get_provider(db: Database):
    mgr = ConfigManager(db)
    mgr.set_provider("openai", "gpt-4o")
    p = mgr.get_provider("openai")
    assert p is not None
    assert p.model == "gpt-4o"


def test_update_provider(db: Database):
    mgr = ConfigManager(db)
    mgr.set_provider("openai", "gpt-4o")
    mgr.set_provider("openai", "gpt-4o-mini")
    p = mgr.get_provider("openai")
    assert p is not None
    assert p.model == "gpt-4o-mini"


def test_get_missing_provider(db: Database):
    mgr = ConfigManager(db)
    assert mgr.get_provider("nonexistent") is None


def test_list_providers(db: Database):
    mgr = ConfigManager(db)
    mgr.set_provider("openai", "gpt-4o")
    mgr.set_provider("anthropic", "claude-sonnet-4-6")
    providers = mgr.list_providers()
    assert len(providers) == 2


def test_set_and_get_policy(db: Database):
    mgr = ConfigManager(db)
    mgr.set_policy("block_ssh", {"rule": "sensitive_file_read", "action": "block"})
    p = mgr.get_policy("block_ssh")
    assert p is not None
    assert p.config["action"] == "block"


def test_list_policies(db: Database):
    mgr = ConfigManager(db)
    mgr.set_policy("policy_a", {"x": 1})
    mgr.set_policy("policy_b", {"x": 2})
    policies = mgr.list_policies()
    assert len(policies) == 2
