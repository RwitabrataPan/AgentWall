from __future__ import annotations

from agentwall.core.types import ResourceCategory, RuntimeEvent, ToolAction, ToolType

_SENSITIVE_PATHS = frozenset([
    ".ssh", ".aws", ".gnupg", ".config/gcloud",
    "id_rsa", "id_ed25519", "id_ecdsa",
    "/etc/passwd", "/etc/shadow", "/etc/sudoers",
    ".env", "credentials", "secrets",
    ".npmrc", ".pypirc", ".netrc",
    ".kube/config", "kubeconfig",
    "docker.sock", ".docker/config",
])

_DANGEROUS_COMMANDS = frozenset([
    "rm -rf", "rmdir /s",
    "dd if=", "format ",
    "chmod 777", "chmod 666",
    "chown ", "chgrp ",
    "curl ", "wget ",
    "nc ", "netcat ", "ncat ",
    "ssh ", "scp ", "rsync ",
    "sudo ", "su ",
    "iptables", "ufw ",
    "crontab", "at ",
    "python -c", "python3 -c",
    "perl -e", "ruby -e", "node -e",
    "eval ", "exec(",
    "base64 -d", "base64 --decode",
    "/bin/bash", "/bin/sh",
    "cmd.exe", "powershell",
])

_EXFIL_DOMAINS = frozenset([
    "webhook.site", "requestbin", "pipedream.net",
    "pastebin.com", "gist.github.com",
    "ngrok.io", "serveo.net",
])


def compute_risk(event: RuntimeEvent) -> float:
    fn = _RULE_MAP.get(event.tool_type, _default_risk)
    base = fn(event)
    bonus = _category_bonus(event.resource_category)
    return min(base + bonus, 100.0)


def _filesystem_risk(event: RuntimeEvent) -> float:
    risk = 0.0
    tgt = event.target.lower().replace("\\", "/")

    if any(p in tgt for p in _SENSITIVE_PATHS):
        risk += 80.0
    if ".." in event.target:
        risk += 40.0
    if event.action == ToolAction.WRITE:
        risk += 25.0
    elif event.action == ToolAction.DELETE:
        risk += 55.0
    elif event.action == ToolAction.CREATE:
        risk += 10.0

    return risk


def _terminal_risk(event: RuntimeEvent) -> float:
    risk = 0.0
    tgt = event.target.lower()

    if "rm -rf /" in tgt or "rm -rf *" in tgt:
        risk += 90.0
    elif any(cmd in tgt for cmd in _DANGEROUS_COMMANDS):
        risk += 40.0

    if event.action == ToolAction.EXECUTE:
        risk += 15.0

    return risk


def _browser_risk(event: RuntimeEvent) -> float:
    risk = 0.0
    tgt = event.target.lower()

    if not tgt.startswith(("http://", "https://")):
        risk += 30.0
    if any(d in tgt for d in _EXFIL_DOMAINS):
        risk += 55.0

    return risk


def _api_risk(event: RuntimeEvent) -> float:
    risk = 0.0
    tgt = event.target.lower()

    if any(d in tgt for d in _EXFIL_DOMAINS):
        risk += 55.0
    if event.action == ToolAction.SEND:
        risk += 20.0

    return risk


def _database_risk(event: RuntimeEvent) -> float:
    risk = 0.0
    tgt = event.target.lower()

    destructive = ("drop table", "drop database", "truncate ", "delete from")
    if any(kw in tgt for kw in destructive):
        risk += 70.0
    if "select *" in tgt:
        risk += 15.0
    if event.action == ToolAction.DELETE:
        risk += 40.0
    elif event.action in (ToolAction.WRITE, ToolAction.CREATE):
        risk += 10.0

    return risk


def _email_risk(event: RuntimeEvent) -> float:
    risk = 0.0
    if event.action == ToolAction.SEND:
        risk += 35.0
    return risk


def _default_risk(event: RuntimeEvent) -> float:
    return 10.0


def _category_bonus(category: ResourceCategory) -> float:
    return {
        ResourceCategory.CREDENTIALS: 30.0,
        ResourceCategory.SYSTEM: 20.0,
        ResourceCategory.CONFIG: 10.0,
        ResourceCategory.NETWORK: 10.0,
        ResourceCategory.CODE: 5.0,
        ResourceCategory.USER_DATA: 5.0,
        ResourceCategory.UNKNOWN: 0.0,
    }.get(category, 0.0)


_RULE_MAP = {
    ToolType.FILESYSTEM: _filesystem_risk,
    ToolType.TERMINAL:   _terminal_risk,
    ToolType.BROWSER:    _browser_risk,
    ToolType.API:        _api_risk,
    ToolType.DATABASE:   _database_risk,
    ToolType.EMAIL:      _email_risk,
}
