from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentwall.core.config_manager import ConfigManager
from agentwall.inspector.deps import get_config_manager
from agentwall.models.schemas import ProviderSettingSchema

router = APIRouter(prefix="/api/providers", tags=["providers"])


class _UpdateBody(BaseModel):
    model: str
    priority: int = 0
    enabled: bool = True


class _KeyBody(BaseModel):
    api_key: str


@router.get("", response_model=list[ProviderSettingSchema])
def list_providers(mgr: ConfigManager = Depends(get_config_manager)):
    return mgr.list_providers_ordered()


@router.put("/{provider}", response_model=ProviderSettingSchema)
def update_provider(
    provider: str,
    body: _UpdateBody,
    mgr: ConfigManager = Depends(get_config_manager),
):
    mgr.set_provider(provider, body.model, priority=body.priority, enabled=body.enabled)
    row = mgr.get_provider(provider)
    if not row:
        raise HTTPException(500, detail="Failed to retrieve updated provider")
    return row


@router.post("/{provider}/key")
def update_key(provider: str, body: _KeyBody):
    from agentwall.providers.keyring import store_api_key
    store_api_key(provider, body.api_key)
    return {"ok": True}


@router.post("/{provider}/test")
def test_provider(provider: str, mgr: ConfigManager = Depends(get_config_manager)):
    from agentwall.providers.keyring import get_api_key
    from agentwall.providers.registry import EVALUATOR_CLASSES

    setting = mgr.get_provider(provider)
    if not setting:
        raise HTTPException(404, detail="Provider not configured")
    cls = EVALUATOR_CLASSES.get(provider)
    if not cls:
        raise HTTPException(400, detail="Unknown provider")
    try:
        api_key = get_api_key(provider) if cls.NEEDS_API_KEY else None
        kwargs: dict = {"model": setting.model}
        if api_key:
            kwargs["api_key"] = api_key
        result = cls(**kwargs).health_check()
        return {
            "provider": provider,
            "model": setting.model,
            "healthy": result.health.value == "healthy",
            "latency_ms": result.latency_ms,
            "error": result.error,
        }
    except Exception as exc:
        return {
            "provider": provider,
            "model": setting.model,
            "healthy": False,
            "latency_ms": None,
            "error": str(exc),
        }


@router.delete("/{provider}")
def delete_provider(provider: str, mgr: ConfigManager = Depends(get_config_manager)):
    mgr.remove_provider(provider)
    try:
        from agentwall.providers.keyring import delete_api_key
        delete_api_key(provider)
    except Exception:
        pass
    return {"ok": True}
