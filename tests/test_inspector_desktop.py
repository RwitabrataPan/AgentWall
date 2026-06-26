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

    def _noop_server(host, port, server_ref):
        pass  # don't start uvicorn; server_ref stays empty

    with patch.object(desktop, "_wait_for_server", return_value=True), \
         patch.object(desktop, "_run_server_thread", side_effect=_noop_server), \
         patch("os._exit"):
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

    def _noop_server(host, port, server_ref):
        pass

    with patch.object(desktop, "_wait_for_server", return_value=False), \
         patch.object(desktop, "_run_server_thread", side_effect=_noop_server):
        with pytest.raises(RuntimeError, match="failed to start"):
            desktop.launch_desktop("127.0.0.1", 9999)


def test_launch_desktop_signals_shutdown(monkeypatch):
    """launch_desktop sets should_exit on the server after window closes."""
    mock_webview = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", mock_webview)

    from agentwall.inspector import desktop

    class FakeServer:
        should_exit = False

    fake_srv = FakeServer()

    def _fake_server(host, port, server_ref):
        server_ref.append(fake_srv)

    with patch.object(desktop, "_wait_for_server", return_value=True), \
         patch.object(desktop, "_run_server_thread", side_effect=_fake_server), \
         patch("os._exit"):
        desktop.launch_desktop("127.0.0.1", 8080)

    assert fake_srv.should_exit is True


def test_launch_desktop_exits_process_after_window_close(monkeypatch):
    """launch_desktop calls os._exit(0) after the window closes and cleanup."""
    mock_webview = MagicMock()
    monkeypatch.setitem(sys.modules, "webview", mock_webview)

    from agentwall.inspector import desktop

    def _noop_server(host, port, server_ref):
        pass

    with patch.object(desktop, "_wait_for_server", return_value=True), \
         patch.object(desktop, "_run_server_thread", side_effect=_noop_server), \
         patch("os._exit") as mock_exit:
        desktop.launch_desktop("127.0.0.1", 8080)

    mock_exit.assert_called_once_with(0)


def test_wait_for_server_returns_true_on_200(monkeypatch):
    """_wait_for_server returns True when HTTP 200 received."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 200

    monkeypatch.setattr(httpx, "get", lambda url, timeout: mock_response)

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
