from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agentwall.inspector.deps import get_policy_engine
from agentwall.models.schemas import PolicySchema
from agentwall.security.policy_engine import PolicyEngine

router = APIRouter(prefix="/api/policies", tags=["policies"])

_TEMPLATES = [
    {
        "name": "Block SSH Keys",
        "description": "Block access to SSH private keys",
        "config": {
            "description": "Block access to SSH private keys",
            "rules": [
                {
                    "tool_type": "filesystem",
                    "pattern": "*/.ssh/id_*",
                    "decision": "block",
                    "reason": "SSH private key access blocked",
                },
                {
                    "tool_type": "filesystem",
                    "pattern": "*/.ssh/authorized_keys",
                    "decision": "block",
                    "reason": "SSH authorized_keys access blocked",
                },
            ],
        },
    },
    {
        "name": "Protect .env Files",
        "description": "Block read/write of .env files containing secrets",
        "config": {
            "description": "Block .env file access",
            "rules": [
                {
                    "tool_type": "filesystem",
                    "pattern": "**/.env",
                    "decision": "block",
                    "reason": ".env file access blocked",
                },
                {
                    "tool_type": "filesystem",
                    "pattern": "**/.env.*",
                    "decision": "block",
                    "reason": ".env variant file access blocked",
                },
            ],
        },
    },
    {
        "name": "Protect AWS Credentials",
        "description": "Block access to AWS credential files",
        "config": {
            "description": "Block AWS credential access",
            "rules": [
                {
                    "tool_type": "filesystem",
                    "pattern": "*/.aws/credentials",
                    "decision": "block",
                    "reason": "AWS credentials file access blocked",
                },
                {
                    "tool_type": "filesystem",
                    "pattern": "*/.aws/config",
                    "decision": "warn",
                    "reason": "AWS config file access flagged",
                },
            ],
        },
    },
    {
        "name": "Prevent Database Dumps",
        "description": "Block database dump/export operations",
        "config": {
            "description": "Block database dump operations",
            "rules": [
                {
                    "tool_type": "database",
                    "action": "execute",
                    "pattern": "*dump*",
                    "decision": "block",
                    "reason": "Database dump operation blocked",
                },
                {
                    "tool_type": "terminal",
                    "pattern": "*pg_dump*",
                    "decision": "block",
                    "reason": "pg_dump blocked",
                },
                {
                    "tool_type": "terminal",
                    "pattern": "*mysqldump*",
                    "decision": "block",
                    "reason": "mysqldump blocked",
                },
            ],
        },
    },
    {
        "name": "Prevent External Uploads",
        "description": "Block uploads to known data exfiltration services",
        "config": {
            "description": "Block external data upload services",
            "rules": [
                {
                    "tool_type": "api",
                    "pattern": "*webhook.site*",
                    "decision": "block",
                    "reason": "External upload to webhook.site blocked",
                },
                {
                    "tool_type": "api",
                    "pattern": "*pastebin.com*",
                    "decision": "block",
                    "reason": "External upload to pastebin blocked",
                },
                {
                    "tool_type": "api",
                    "pattern": "*transfer.sh*",
                    "decision": "block",
                    "reason": "External upload to transfer.sh blocked",
                },
            ],
        },
    },
    {
        "name": "Warn Before Email",
        "description": "Warn when agent attempts to send email",
        "config": {
            "description": "Warn before sending email",
            "rules": [
                {
                    "tool_type": "email",
                    "action": "send",
                    "decision": "warn",
                    "reason": "Email send requires approval",
                }
            ],
        },
    },
]


class _CreateBody(BaseModel):
    name: str
    config: dict
    priority: int = 0


class _UpdateBody(BaseModel):
    config: dict


class _PriorityBody(BaseModel):
    priority: int


class _TestBody(BaseModel):
    config: dict
    tool_type: str
    target: str = ""
    action: str | None = None
    resource_category: str | None = None


@router.get("/templates")
def list_templates():
    return _TEMPLATES


@router.post("/test")
def test_policy(body: _TestBody):
    """Simulate a policy evaluation without saving. Returns match result."""
    import fnmatch
    from agentwall.core.types import (
        DecisionType,
        ResourceCategory,
        RuntimeEvent,
        ToolAction,
        ToolType,
    )

    try:
        tt = ToolType(body.tool_type)
    except ValueError:
        tt = ToolType.GENERAL

    try:
        act = ToolAction(body.action) if body.action else ToolAction.READ
    except ValueError:
        act = ToolAction.READ

    try:
        rc = ResourceCategory(body.resource_category) if body.resource_category else ResourceCategory.UNKNOWN
    except ValueError:
        rc = ResourceCategory.UNKNOWN

    event = RuntimeEvent(
        session_id="test",
        goal="policy test",
        tool_type=tt,
        action=act,
        target=body.target,
        resource_category=rc,
        metadata={},
    )

    for i, rule in enumerate(body.config.get("rules", [])):
        if _rule_matches(rule, event):
            return {
                "matched": True,
                "rule_index": i,
                "decision": rule.get("decision", "block"),
                "reason": rule.get("reason", ""),
                "rule": rule,
            }

    return {"matched": False, "decision": None, "reason": None, "rule": None}


def _rule_matches(rule: dict, event) -> bool:
    import fnmatch
    if "tool_type" in rule and rule["tool_type"] != event.tool_type.value:
        return False
    if "action" in rule and rule["action"] != event.action.value:
        return False
    if "resource_category" in rule and rule["resource_category"] != event.resource_category.value:
        return False
    if "pattern" in rule:
        target = event.target.replace("\\", "/")
        if not fnmatch.fnmatch(target, rule["pattern"]) and rule["pattern"] not in target:
            return False
    return True


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
