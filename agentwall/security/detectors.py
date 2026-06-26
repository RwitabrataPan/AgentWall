from __future__ import annotations

from agentwall.core.types import ResourceCategory, RuntimeEvent, ToolAction, ToolType

_SSH_PATTERNS = frozenset([
    ".ssh/", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    "known_hosts", "authorized_keys",
])
_AWS_PATTERNS = frozenset([
    ".aws/credentials", ".aws/config",
    "aws_access_key", "aws_secret_access_key", "aws_session_token",
])
_TOKEN_PATTERNS = frozenset([
    ".env", "api_key", "api_token", "secret_key", "access_token",
    "auth_token", "bearer_token", "client_secret", "refresh_token",
    "service_account",
])
_CERT_PATTERNS = frozenset([
    ".pem", ".p12", ".pfx", ".crt", ".cert",
    "-----begin", "private_key", ".key",
])
_CLOUD_PATTERNS = frozenset([
    ".gcloud", "gcp_key", "azure_client", "azure_tenant",
    "kubeconfig", ".kube/config",
])

_EXFIL_DOMAINS = frozenset([
    "webhook.site", "requestbin", "pipedream.net",
    "pastebin.com", "gist.github.com", "ngrok.io",
    "serveo.net", "transfer.sh", "hastebin.com",
])
_PRIVATE_PREFIXES = ("localhost", "127.", "192.168.", "10.", "172.")

_PRIVILEGED_CATEGORIES = frozenset([
    ResourceCategory.CREDENTIALS,
    ResourceCategory.SYSTEM,
])


class BaseDetector:
    name: str = "base"

    def detect(self, event: RuntimeEvent, history: list[RuntimeEvent]) -> list[str]:
        """Return detector hit labels; empty list = clean."""
        return []


class SensitiveResourceDetector(BaseDetector):
    """Detects access to SSH keys, API tokens, AWS credentials, certs, private keys."""

    name: str = "sensitive_resource"

    def detect(self, event: RuntimeEvent, history: list[RuntimeEvent]) -> list[str]:
        hits: list[str] = []
        tgt = event.target.lower().replace("\\", "/")

        if any(p in tgt for p in _SSH_PATTERNS):
            hits.append("ssh_key")
        if any(p in tgt for p in _AWS_PATTERNS):
            hits.append("aws_credentials")
        if any(p in tgt for p in _TOKEN_PATTERNS):
            hits.append("api_token_or_secret")
        if any(p in tgt for p in _CERT_PATTERNS):
            hits.append("private_key_or_cert")
        if any(p in tgt for p in _CLOUD_PATTERNS):
            hits.append("cloud_credentials")

        return hits


class ScopeExpansionDetector(BaseDetector):
    """Detects unexpected resource growth, unrelated access, privilege escalation."""

    name: str = "scope_expansion"
    _HISTORY_MIN = 3   # need enough history to establish baseline

    def detect(self, event: RuntimeEvent, history: list[RuntimeEvent]) -> list[str]:
        if len(history) < self._HISTORY_MIN:
            return []

        hits: list[str] = []
        seen_types = {e.tool_type for e in history}
        seen_categories = {e.resource_category for e in history}

        # New tool type introduced after baseline established
        if event.tool_type not in seen_types:
            hits.append("new_tool_type_introduced")

        # Privilege escalation: first access to privileged category
        if (event.resource_category in _PRIVILEGED_CATEGORIES
                and not (seen_categories & _PRIVILEGED_CATEGORIES)):
            hits.append("privilege_escalation")

        # Unrelated resource: dominant tool type clearly established, now accessing other
        if len(history) >= 5:
            type_counts: dict[ToolType, int] = {}
            for e in history:
                type_counts[e.tool_type] = type_counts.get(e.tool_type, 0) + 1
            dominant = max(type_counts, key=lambda t: type_counts[t])
            dominant_share = type_counts[dominant] / len(history)
            if dominant_share >= 0.7 and event.tool_type != dominant:
                hits.append("unrelated_resource_access")

        return hits


class DataExfiltrationDetector(BaseDetector):
    """Detects external uploads, external email sends, external API posts."""

    name: str = "data_exfiltration"

    def detect(self, event: RuntimeEvent, history: list[RuntimeEvent]) -> list[str]:
        hits: list[str] = []
        tgt = event.target.lower()

        if event.tool_type == ToolType.EMAIL and event.action == ToolAction.SEND:
            hits.append("external_email_send")
            return hits

        if event.tool_type in (ToolType.BROWSER, ToolType.API):
            if event.action in (ToolAction.SEND, ToolAction.REQUEST, ToolAction.WRITE):
                # Known exfiltration domains
                if any(d in tgt for d in _EXFIL_DOMAINS):
                    hits.append("exfil_domain_upload")

                # External call after reading sensitive files (read-then-exfil pattern)
                is_external = not any(tgt.startswith(p) or p in tgt for p in _PRIVATE_PREFIXES)
                if is_external:
                    cred_reads = [
                        e for e in history[-10:]
                        if e.tool_type == ToolType.FILESYSTEM
                        and e.action == ToolAction.READ
                        and e.resource_category == ResourceCategory.CREDENTIALS
                    ]
                    if cred_reads:
                        hits.append("credential_read_then_external_call")

        if event.tool_type == ToolType.TERMINAL and event.action == ToolAction.EXECUTE:
            tgt_lower = event.target.lower()
            exfil_cmds = ("curl ", "wget ", "scp ", "rsync ", "nc ", "ncat ")
            if any(cmd in tgt_lower for cmd in exfil_cmds):
                if any(d in tgt_lower for d in _EXFIL_DOMAINS):
                    hits.append("terminal_exfil_to_known_domain")

        return hits


_CODE_GOAL_KEYWORDS = frozenset([
    "fix", "bug", "implement", "feature", "code", "test", "write", "build",
    "create", "update", "refactor", "debug", "review", "read", "analyze",
    "check", "inspect", "find", "locate",
])
_EXFIL_GOAL_KEYWORDS = frozenset(["send", "email", "notify", "report", "upload", "export"])
_CRED_TARGETS = frozenset([
    ".env", "credential", "secret", "password", "token", ".pem", ".key",
    "id_rsa", ".aws/", "service_account",
])


class GoalDriftDetector(BaseDetector):
    """Detects tool actions inconsistent with the current stated goal.

    Unlike ScopeExpansionDetector (history-based), this compares each action
    directly against the goal text to catch prompt-injection-induced goal hijacking.
    """

    name: str = "goal_drift"

    def detect(self, event: RuntimeEvent, history: list[RuntimeEvent]) -> list[str]:
        hits: list[str] = []
        goal = event.goal.lower()

        if not goal:
            return hits

        # Credentials access while goal is code-focused
        if (
            event.resource_category == ResourceCategory.CREDENTIALS
            and any(kw in goal for kw in _CODE_GOAL_KEYWORDS)
            and not any(kw in goal for kw in ("secret", "credential", "key", "token", "auth"))
        ):
            hits.append("goal_drift:credential_access_off_goal")

        # Credential target patterns while goal is code-focused
        tgt = event.target.lower().replace("\\", "/")
        if (
            any(p in tgt for p in _CRED_TARGETS)
            and any(kw in goal for kw in _CODE_GOAL_KEYWORDS)
            and event.resource_category not in (ResourceCategory.CREDENTIALS,)
        ):
            hits.append("goal_drift:sensitive_target_off_goal")

        # Email send when goal doesn't mention communication
        if (
            event.tool_type == ToolType.EMAIL
            and event.action == ToolAction.SEND
            and not any(kw in goal for kw in _EXFIL_GOAL_KEYWORDS)
        ):
            hits.append("goal_drift:unexpected_email")

        # System resource access when goal is code-focused
        if (
            event.resource_category == ResourceCategory.SYSTEM
            and any(kw in goal for kw in _CODE_GOAL_KEYWORDS)
            and not any(kw in goal for kw in ("system", "config", "setup", "install", "deploy"))
        ):
            hits.append("goal_drift:system_access_off_goal")

        return hits
