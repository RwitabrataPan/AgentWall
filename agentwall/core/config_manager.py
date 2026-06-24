from __future__ import annotations

import time

from ..storage.database import Database
from ..storage.models import Policy, ProviderSetting

_DEFAULT_THRESHOLDS = {"low_threshold": 30.0, "high_threshold": 70.0}
_THRESHOLDS_POLICY = "thresholds"


class ConfigManager:
    def __init__(self, db: Database) -> None:
        self._db = db

    # --- Provider settings ---

    def get_provider(self, provider: str) -> ProviderSetting | None:
        with self._db.session() as db:
            row = db.get(ProviderSetting, provider)
            if row:
                db.expunge(row)
            return row

    def set_provider(
        self,
        provider: str,
        model: str,
        priority: int = 0,
        enabled: bool = True,
        config: dict | None = None,
    ) -> None:
        with self._db.session() as db:
            existing = db.get(ProviderSetting, provider)
            if existing:
                existing.model = model
                existing.priority = priority
                existing.enabled = enabled
                existing.config = config or {}
            else:
                db.add(ProviderSetting(
                    provider=provider, model=model,
                    priority=priority, enabled=enabled, config=config or {},
                ))
            db.commit()

    def set_provider_enabled(self, provider: str, enabled: bool) -> None:
        with self._db.session() as db:
            row = db.get(ProviderSetting, provider)
            if row:
                row.enabled = enabled
                db.commit()

    def remove_provider(self, provider: str) -> None:
        with self._db.session() as db:
            row = db.get(ProviderSetting, provider)
            if row:
                db.delete(row)
                db.commit()

    def list_providers(self) -> list[ProviderSetting]:
        with self._db.session() as db:
            rows = db.query(ProviderSetting).all()
            for r in rows:
                db.expunge(r)
            return rows

    def list_providers_ordered(self) -> list[ProviderSetting]:
        with self._db.session() as db:
            rows = db.query(ProviderSetting).order_by(ProviderSetting.priority).all()
            for r in rows:
                db.expunge(r)
            return rows

    # --- Policies ---

    def get_policy(self, name: str) -> Policy | None:
        with self._db.session() as db:
            row = db.query(Policy).filter(Policy.name == name).first()
            if row:
                db.expunge(row)
            return row

    def set_policy(self, name: str, config: dict) -> None:
        with self._db.session() as db:
            existing = db.query(Policy).filter(Policy.name == name).first()
            if existing:
                existing.config = config
            else:
                db.add(Policy(name=name, config=config, created_at=time.time()))
            db.commit()

    def list_policies(self) -> list[Policy]:
        with self._db.session() as db:
            rows = db.query(Policy).order_by(Policy.name).all()
            for r in rows:
                db.expunge(r)
            return rows

    # --- Risk thresholds (stored as policy) ---

    def get_thresholds(self) -> dict:
        policy = self.get_policy(_THRESHOLDS_POLICY)
        if policy:
            return {**_DEFAULT_THRESHOLDS, **policy.config}
        return dict(_DEFAULT_THRESHOLDS)

    def set_thresholds(self, low: float, high: float) -> None:
        self.set_policy(_THRESHOLDS_POLICY, {"low_threshold": low, "high_threshold": high})
