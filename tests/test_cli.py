from typer.testing import CliRunner
from agentwall.cli.main import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "agentwall" in result.output
    assert "0.1.0" in result.output


def test_doctor_exits_zero():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_config_no_args():
    # --status avoids interactive prompts
    result = runner.invoke(app, ["config", "--status"])
    assert result.exit_code == 0


def test_inspect_requires_uvicorn():
    # Inspect imports uvicorn — just verify it doesn't hard crash on import
    from agentwall.inspector import server  # noqa: F401
