from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentwall.core.types import ResourceCategory, RuntimeEvent, ToolAction, ToolType


class ResultClassification(str, Enum):
    NORMAL = "normal"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"
    BULK_DATA_ACCESS = "bulk_data_access"
    EXTERNAL_TRANSFER = "external_transfer"
    EMAIL_DISPATCH = "email_dispatch"


@dataclass
class AnalysisResult:
    classification: ResultClassification
    detector_hits: list[str]
    post_risk: float  # Additional risk signal (0-100). Never used to retroactively block.
    metadata: dict = field(default_factory=dict)  # Counts, hashes, type info — no content.


_SENSITIVE_CONTENT_MARKERS = [
    "-----begin", "private key", "aws_access_key", "aws_secret",
    "password", "passwd", "authorization:", "bearer ",
    "api_key", "apikey", "token", "credential",
    ".ssh/id_", "id_rsa", ".aws/credentials",
]

_SENSITIVE_DB_COLUMNS = {
    "password", "passwd", "secret", "token", "ssn", "credit_card",
    "cvv", "pin", "dob", "hash", "salt", "api_key",
}

_TRANSFER_SUCCESS_SIGNALS = {
    "200", "201", "uploaded", "success", "created", "ok",
    "sent", "accepted", "stored", "saved", "written",
}

_WRITE_ACTIONS = {ToolAction.WRITE, ToolAction.REQUEST, ToolAction.CREATE, ToolAction.SEND}


class ResultAnalyzer:
    """Analyzes tool execution results for post-execution security signals.

    Classifies results and produces metadata only. Never stores actual content —
    only hashes, counts, and classifications. Post-execution findings enrich the
    audit trail but NEVER retroactively block (pre-execution decision is final).
    """

    def analyze(self, event: RuntimeEvent, result: Any) -> AnalysisResult:
        if result is None:
            return AnalysisResult(ResultClassification.NORMAL, [], 0.0, {})

        result_str = str(result)

        if event.tool_type == ToolType.FILESYSTEM:
            return self._analyze_filesystem(event, result_str)
        if event.tool_type == ToolType.DATABASE:
            return self._analyze_database(event, result_str)
        if event.tool_type == ToolType.API:
            return self._analyze_api(event, result_str)
        if event.tool_type == ToolType.EMAIL:
            return self._analyze_email(event, result_str)
        if event.tool_type == ToolType.TERMINAL:
            return self._analyze_terminal(result_str)

        return AnalysisResult(
            ResultClassification.NORMAL,
            [],
            0.0,
            {"output_length": len(result_str)},
        )

    def _analyze_filesystem(self, event: RuntimeEvent, result_str: str) -> AnalysisResult:
        result_lower = result_str.lower()
        hits: list[str] = []

        if any(m in result_lower for m in _SENSITIVE_CONTENT_MARKERS):
            hits.append("sensitive_content_in_output")
        if event.resource_category == ResourceCategory.CREDENTIALS:
            hits.append("credential_file_read")

        classification = ResultClassification.SENSITIVE_DATA_EXPOSURE if hits else ResultClassification.NORMAL
        return AnalysisResult(
            classification,
            hits,
            min(len(hits) * 25.0, 60.0),
            {
                "output_length": len(result_str),
                "content_hash": _sha16(result_str),
                "target": event.target,
            },
        )

    def _analyze_database(self, event: RuntimeEvent, result_str: str) -> AnalysisResult:
        result_lower = result_str.lower()
        hits: list[str] = []

        line_count = result_str.count("\n") + 1 if result_str.strip() else 0
        sensitive_cols = [c for c in _SENSITIVE_DB_COLUMNS if c in result_lower]

        if line_count > 50:
            hits.append("bulk_data_retrieved")
        if sensitive_cols:
            hits.append("sensitive_columns_present")

        classification = ResultClassification.BULK_DATA_ACCESS if hits else ResultClassification.NORMAL
        return AnalysisResult(
            classification,
            hits,
            min(len(hits) * 20.0, 50.0),
            {
                "row_estimate": line_count,
                "sensitive_columns_detected": sensitive_cols,
                "output_hash": _sha16(result_str),
            },
        )

    def _analyze_api(self, event: RuntimeEvent, result_str: str) -> AnalysisResult:
        result_lower = result_str.lower()
        success_signals = [s for s in _TRANSFER_SUCCESS_SIGNALS if s in result_lower]
        hits: list[str] = []

        if event.action in _WRITE_ACTIONS and success_signals:
            hits.append("external_transfer_confirmed")

        classification = ResultClassification.EXTERNAL_TRANSFER if hits else ResultClassification.NORMAL
        return AnalysisResult(
            classification,
            hits,
            30.0 if hits else 0.0,
            {
                "target": event.target,
                "response_length": len(result_str),
                "success_signals": success_signals,
            },
        )

    def _analyze_email(self, event: RuntimeEvent, result_str: str) -> AnalysisResult:
        return AnalysisResult(
            ResultClassification.EMAIL_DISPATCH,
            ["email_dispatched"],
            30.0,
            {"target": event.target, "response_length": len(result_str)},
        )

    def _analyze_terminal(self, result_str: str) -> AnalysisResult:
        result_lower = result_str.lower()
        hits: list[str] = []

        if any(m in result_lower for m in _SENSITIVE_CONTENT_MARKERS):
            hits.append("sensitive_content_in_output")

        classification = ResultClassification.SENSITIVE_DATA_EXPOSURE if hits else ResultClassification.NORMAL
        return AnalysisResult(
            classification,
            hits,
            30.0 if hits else 0.0,
            {"output_length": len(result_str), "output_hash": _sha16(result_str)},
        )


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
