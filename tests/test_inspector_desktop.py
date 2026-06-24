from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


def test_launch_desktop_creates_webview_window(monkeypatch):
    """launch_desktop calls webview.create_window with correct title and URL."""
    mock_webview = MagicMock()
    mock_webview.create_window.return_value = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", mock_webview)

    from agentwall.inspector import desktop
    with patch.object(desktop, "_wait_for_server", return_value=True), \
         patch.object(desktop, "_run_server_thread"):
        desktop.launch_desktop("127.0.0.1", 8080)

    mock_webview.create_window.assert_called_once_with(
        "AgentWall Inspector",
        "http://127.0.0.1:8080",
        width=1280,
        height=800,
        resizable=True,
    )
    mock_webview.start.assert_called_once()


def test_launch_desktop_raises_if_server_does_not_start(monkeypatch):
    """launch_desktop raises RuntimeError if server doesn't respond in time."""
    mock_webview = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", mock_webview)

    from agentwall.inspector import desktop
    with patch.object(desktop, "_wait_for_server", return_value=False), \
         patch.object(desktop, "_run_server_thread"):
        with pytest.raises(RuntimeError, match="failed to start"):
            desktop.launch_desktop("127.0.0.1", 9999)


def test_wait_for_server_returns_true_on_200(monkeypatch):
    """_wait_for_server returns True when HTTP 200 received."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 200

    monkeypatch.setattr(httpx, "get", lambda url, timeout: mock_response)

    # must reload to get fresh module without cached imports
    if "agentwall.inspector.desktop" in sys.modules:
        del sys.modules["agentwall.inspector.desktop"]

    from agentwall.inspector.desktop import _wait_for_server
    result = _wait_for_server("127.0.0.1", 19999, timeout=2.0, interval=0.01)
    assert result is True


def test_wait_for_server_returns_false_on_timeout(monkeypatch):
    """_wait_for_server returns False when server never responds."""
    import httpx

    def _always_fail(url, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", _always_fail)

    if "agentwall.inspector.desktop" in sys.modules:
        del sys.modules["agentwall.inspector.desktop"]

    from agentwall.inspector.desktop import _wait_for_server
    result = _wait_for_server("127.0.0.1", 19998, timeout=0.05, interval=0.01)
    assert result is False
