from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentwall.inspector.deps import get_policy_engine
from agentwall.models.schemas import PolicySchema
from agentwall.security.policy_engine import PolicyEngine

router = APIRouter(prefix="/api/policies", tags=["policies"])


class _CreateBody(BaseModel):
    name: str
    config: dict
    priority: int = 0


class _UpdateBody(BaseModel):
    config: dict


class _PriorityBody(BaseModel):
    priority: int


@router.get("", response_model=list[PolicySchema])
def list_policies(pe: PolicyEngine = Depends(get_policy_engine)):
    return pe.list()


@router.post("", response_model=PolicySchema, status_code=201)
def create_policy(body: _CreateBody, pe: PolicyEngine = Depends(get_policy_engine)):
    try:
        return pe.create(body.name, body.config, priority=body.priority)
    except Exception as e:
        raise HTTPException(400, detail=str(e))


@router.put("/{name}", response_model=PolicySchema)
def update_policy(name: str, body: _UpdateBody, pe: PolicyEngine = Depends(get_policy_engine)):
    try:
        return pe.update(name, body.config)
    except KeyError:
        raise HTTPException(404, detail="Policy not found")


@router.post("/{name}/enable")
def enable_policy(name: str, pe: PolicyEngine = Depends(get_policy_engine)):
    try:
        pe.enable(name)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404, detail="Policy not found")


@router.post("/{name}/disable")
def disable_policy(name: str, pe: PolicyEngine = Depends(get_policy_engine)):
    try:
        pe.disable(name)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404, detail="Policy not found")


@router.patch("/{name}/priority")
def set_policy_priority(name: str, body: _PriorityBody, pe: PolicyEngine = Depends(get_policy_engine)):
    try:
        pe.set_priority(name, body.priority)
        return {"ok": True}
    except KeyError:
        raise HTTPException(404, detail="Policy not found")


@router.delete("/{name}")
def delete_policy(name: str, pe: PolicyEngine = Depends(get_policy_engine)):
    pe.delete(name)
    return {"ok": True}
