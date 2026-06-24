from __future__ import annotations

import pytest

from agentwall.core.types import ResourceCategory, RuntimeEvent, ToolAction, ToolType
from agentwall.security.result_analyzer import AnalysisResult, ResultAnalyzer, ResultClassification


def _event(
    tool_type: ToolType = ToolType.FILESYSTEM,
    action: ToolAction = ToolAction.READ,
    target: str = "/app/file.txt",
    resource_category: ResourceCategory = ResourceCategory.CODE,
) -> RuntimeEvent:
    return RuntimeEvent(
        session_id="s1",
        goal="fix bug",
        tool_type=tool_type,
        action=action,
        target=target,
        resource_category=resource_category,
        metadata={},
        tool_name="test_tool",
    )


def test_normal_filesystem_result_is_normal():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(_event(), "contents of login.tsx")
    assert result.classification == ResultClassification.NORMAL
    assert result.post_risk == 0.0
    assert result.detector_hits == []


def test_filesystem_result_with_private_key_flagged():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(_event(), "-----BEGIN RSA PRIVATE KEY-----\nMIIEo...")
    assert result.classification == ResultClassification.SENSITIVE_DATA_EXPOSURE
    assert "sensitive_content_in_output" in result.detector_hits
    assert result.post_risk > 0


def test_filesystem_result_with_password_flagged():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(_event(), "DB_PASSWORD=supersecret123")
    assert result.classification == ResultClassification.SENSITIVE_DATA_EXPOSURE


def test_credential_resource_category_flagged():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(
        _event(resource_category=ResourceCategory.CREDENTIALS),
        "no sensitive content here",
    )
    assert result.classification == ResultClassification.SENSITIVE_DATA_EXPOSURE
    assert "credential_file_read" in result.detector_hits


def test_metadata_never_stores_content():
    analyzer = ResultAnalyzer()
    secret = "-----BEGIN PRIVATE KEY-----\nABCDEF"
    result = analyzer.analyze(_event(), secret)
    # Metadata must not contain raw content
    for v in result.metadata.values():
        assert secret not in str(v)
    assert "content_hash" in result.metadata
    assert len(result.metadata["content_hash"]) == 16


def test_none_result_is_normal():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(_event(), None)
    assert result.classification == ResultClassification.NORMAL
    assert result.post_risk == 0.0


def test_database_bulk_rows_flagged():
    analyzer = ResultAnalyzer()
    bulk = "\n".join([f"row{i}" for i in range(60)])
    result = analyzer.analyze(_event(tool_type=ToolType.DATABASE, action=ToolAction.QUERY), bulk)
    assert result.classification == ResultClassification.BULK_DATA_ACCESS
    assert "bulk_data_retrieved" in result.detector_hits
    assert result.metadata["row_estimate"] > 50


def test_database_sensitive_column_flagged():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(
        _event(tool_type=ToolType.DATABASE, action=ToolAction.QUERY),
        "id,email,password,token\n1,a@b.com,hash123,tok456",
    )
    assert "sensitive_columns_present" in result.detector_hits
    assert "password" in result.metadata["sensitive_columns_detected"]


def test_database_normal_small_result():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(
        _event(tool_type=ToolType.DATABASE, action=ToolAction.QUERY),
        "id,name\n1,Alice\n2,Bob",
    )
    assert result.classification == ResultClassification.NORMAL
    assert result.post_risk == 0.0


def test_api_write_with_success_flagged():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(
        _event(tool_type=ToolType.API, action=ToolAction.WRITE, target="https://api.example.com/upload"),
        '{"status": "success", "id": "abc123"}',
    )
    assert result.classification == ResultClassification.EXTERNAL_TRANSFER
    assert "external_transfer_confirmed" in result.detector_hits
    assert result.post_risk == 30.0


def test_api_read_with_success_not_flagged():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(
        _event(tool_type=ToolType.API, action=ToolAction.READ, target="https://api.example.com/data"),
        '{"status": "200", "data": []}',
    )
    # READ action → not flagged as external transfer
    assert result.classification == ResultClassification.NORMAL


def test_email_always_flagged():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(
        _event(tool_type=ToolType.EMAIL, action=ToolAction.SEND, target="victim@example.com"),
        "Email sent successfully",
    )
    assert result.classification == ResultClassification.EMAIL_DISPATCH
    assert "email_dispatched" in result.detector_hits
    assert result.post_risk == 30.0
    assert result.metadata["target"] == "victim@example.com"


def test_terminal_with_credentials_flagged():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(
        _event(tool_type=ToolType.TERMINAL, action=ToolAction.EXECUTE),
        "AWS_ACCESS_KEY=AKIA... AWS_SECRET=xxx",
    )
    assert result.classification == ResultClassification.SENSITIVE_DATA_EXPOSURE


def test_unknown_tool_type_returns_normal():
    analyzer = ResultAnalyzer()
    result = analyzer.analyze(
        _event(tool_type=ToolType.BROWSER),
        "some page content",
    )
    assert result.classification == ResultClassification.NORMAL


def test_post_risk_never_exceeds_100():
    analyzer = ResultAnalyzer()
    # Trigger max hits on filesystem
    result = analyzer.analyze(
        _event(resource_category=ResourceCategory.CREDENTIALS),
        "-----BEGIN RSA PRIVATE KEY-----\npassword=secret\ntoken=abc",
    )
    assert result.post_risk <= 100.0
