"""Keyring tests — uses mock backend to avoid touching OS credential store."""
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}

    def fake_set(service, username, password):
        store[(service, username)] = password

    def fake_get(service, username):
        return store.get((service, username))

    def fake_delete(service, username):
        store.pop((service, username), None)

    monkeypatch.setattr("keyring.set_password", fake_set)
    monkeypatch.setattr("keyring.get_password", fake_get)
    monkeypatch.setattr("keyring.delete_password", fake_delete)
    return store


def test_store_and_retrieve():
    from agentwall.providers.keyring import get_api_key, store_api_key
    store_api_key("openai", "sk-test-123")
    assert get_api_key("openai") == "sk-test-123"


def test_retrieve_missing_returns_none():
    from agentwall.providers.keyring import get_api_key
    assert get_api_key("nonexistent") is None


def test_delete_key():
    from agentwall.providers.keyring import delete_api_key, get_api_key, store_api_key
    store_api_key("groq", "gsk-abc")
    delete_api_key("groq")
    assert get_api_key("groq") is None


def test_delete_missing_does_not_raise():
    from agentwall.providers.keyring import delete_api_key
    delete_api_key("never_stored")


def test_keys_isolated_per_provider():
    from agentwall.providers.keyring import get_api_key, store_api_key
    store_api_key("openai", "key-openai")
    store_api_key("anthropic", "key-anthropic")
    assert get_api_key("openai") == "key-openai"
    assert get_api_key("anthropic") == "key-anthropic"
