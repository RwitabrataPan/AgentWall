from __future__ import annotations

import keyring

_SERVICE = "agentwall"


def store_api_key(provider: str, api_key: str) -> None:
    keyring.set_password(_SERVICE, provider, api_key)


def get_api_key(provider: str) -> str | None:
    return keyring.get_password(_SERVICE, provider)


def delete_api_key(provider: str) -> None:
    try:
        keyring.delete_password(_SERVICE, provider)
    except keyring.errors.PasswordDeleteError:
        pass
