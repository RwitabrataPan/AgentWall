"""ProviderRegistry tests — verifies fallback chain assembly from DB."""
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agentwall.core.config_manager import ConfigManager
from agentwall.storage.database import Database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="agentwall_reg_")
    d = Database(path=Path(tmpdir) / "test.db")
    yield d
    d.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_registry_empty_db_raises(db):
    from agentwall.providers.registry import ProviderRegistry
    reg = ProviderRegistry(db)
    with pytest.raises(ValueError):
        reg.load_chain()


def test_registry_loads_ollama_no_key(db):
    mgr = ConfigManager(db)
    mgr.set_provider("ollama", "llama3.2", priority=1)

    from agentwall.providers.registry import ProviderRegistry
    with patch("agentwall.providers.ollama.httpx.post"):
        reg = ProviderRegistry(db)
        chain = reg.load_chain()
    assert "ollama" in chain.providers


def test_registry_skips_disabled(db):
    mgr = ConfigManager(db)
    mgr.set_provider("ollama", "llama3.2", priority=1, enabled=False)

    from agentwall.providers.registry import ProviderRegistry
    reg = ProviderRegistry(db)
    with pytest.raises(ValueError):
        reg.load_chain()


def test_registry_respects_priority_order(db):
    mgr = ConfigManager(db)
    mgr.set_provider("ollama", "llama3.2", priority=2)
    mgr.set_provider("groq", "llama-3.1-8b-instant", priority=1)

    from agentwall.providers.registry import ProviderRegistry
    with (
        patch("agentwall.providers.registry.get_api_key", return_value="fake-key"),
        patch("openai.OpenAI"),
    ):
        reg = ProviderRegistry(db)
        chain = reg.load_chain()
    assert chain.providers[0] == "groq"
    assert chain.providers[1] == "ollama"


def test_config_manager_priority(db):
    mgr = ConfigManager(db)
    mgr.set_provider("openai", "gpt-4o", priority=1)
    mgr.set_provider("anthropic", "claude-haiku-4-5-20251001", priority=2)
    mgr.set_provider("groq", "llama-3.1-8b-instant", priority=3)

    ordered = mgr.list_providers_ordered()
    assert [p.provider for p in ordered] == ["openai", "anthropic", "groq"]


def test_config_manager_remove_provider(db):
    mgr = ConfigManager(db)
    mgr.set_provider("openai", "gpt-4o", priority=1)
    mgr.remove_provider("openai")
    assert mgr.get_provider("openai") is None


def test_config_manager_set_enabled(db):
    mgr = ConfigManager(db)
    mgr.set_provider("groq", "llama-3.1-8b-instant", priority=1)
    mgr.set_provider_enabled("groq", False)
    p = mgr.get_provider("groq")
    assert p is not None
    assert p.enabled is False
