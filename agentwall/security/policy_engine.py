from __future__ import annotations

import fnmatch
import time

from agentwall.core.types import Decision, DecisionType, RuntimeEvent
from agentwall.storage.database import Database
from agentwall.storage.models import Policy


class PolicyEngine:
    """Evaluates RuntimeEvents against persisted policies.

    Policy config schema:
    {
        "description": "...",
        "rules": [
            {
                "tool_type": "filesystem",      # optional
                "action": "read",               # optional
                "resource_category": "credentials", # optional
                "pattern": "*/.ssh/*",          # optional glob on target
                "decision": "block",            # allow | warn | block
                "reason": "..."
            }
        ]
    }
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(self, event: RuntimeEvent) -> Decision | None:
        """Return override Decision if a policy rule matches; None = no match."""
        for policy in self._enabled_policies():
            for rule in policy.config.get("rules", []):
                if _rule_matches(rule, event):
                    verdict = rule.get("decision", "block").lower()
                    if verdict not in ("allow", "warn", "block"):
                        verdict = "block"
                    reason = rule.get("reason", f"policy '{policy.name}'")
                    return Decision(
                        type=DecisionType(verdict),
                        risk_score=_verdict_score(verdict),
                        reason=reason,
                        metadata={"policy_matched": policy.name},
                    )
        return None

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(self, name: str, config: dict, priority: int = 0) -> Policy:
        with self._db.session() as db:
            policy = Policy(
                name=name, config=config, created_at=time.time(),
                enabled=True, priority=priority,
            )
            db.add(policy)
            db.commit()
            db.refresh(policy)
            db.expunge(policy)
        return policy

    def get(self, name: str) -> Policy | None:
        with self._db.session() as db:
            row = db.query(Policy).filter(Policy.name == name).first()
            if row:
                db.expunge(row)
            return row

    def list(self) -> list[Policy]:
        with self._db.session() as db:
            rows = (
                db.query(Policy)
                .order_by(Policy.priority.desc(), Policy.created_at)
                .all()
            )
            for r in rows:
                db.expunge(r)
            return rows

    def update(self, name: str, config: dict) -> Policy:
        with self._db.session() as db:
            row = db.query(Policy).filter(Policy.name == name).first()
            if not row:
                raise KeyError(f"policy '{name}' not found")
            row.config = config
            db.commit()
            db.refresh(row)
            db.expunge(row)
        return row

    def set_priority(self, name: str, priority: int) -> None:
        with self._db.session() as db:
            row = db.query(Policy).filter(Policy.name == name).first()
            if not row:
                raise KeyError(f"policy '{name}' not found")
            row.priority = priority
            db.commit()

    def enable(self, name: str) -> None:
        self._set_enabled(name, True)

    def disable(self, name: str) -> None:
        self._set_enabled(name, False)

    def delete(self, name: str) -> None:
        with self._db.session() as db:
            row = db.query(Policy).filter(Policy.name == name).first()
            if row:
                db.delete(row)
                db.commit()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _enabled_policies(self) -> list[Policy]:
        with self._db.session() as db:
            rows = (
                db.query(Policy)
                .filter(Policy.enabled == True)  # noqa: E712
                .order_by(Policy.priority.desc(), Policy.created_at)
                .all()
            )
            for r in rows:
                db.expunge(r)
            return rows

    def _set_enabled(self, name: str, value: bool) -> None:
        with self._db.session() as db:
            row = db.query(Policy).filter(Policy.name == name).first()
            if not row:
                raise KeyError(f"policy '{name}' not found")
            row.enabled = value
            db.commit()


def _rule_matches(rule: dict, event: RuntimeEvent) -> bool:
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


def _verdict_score(verdict: str) -> float:
    return {"allow": 0.0, "warn": 50.0, "block": 85.0}.get(verdict, 85.0)
