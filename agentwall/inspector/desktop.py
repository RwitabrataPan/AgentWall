from __future__ import annotations

import os
import threading
import time


def _wait_for_server(host: str, port: int, timeout: float = 15.0, interval: float = 0.2) -> bool:
    """Poll the health endpoint until it responds 200 or timeout elapses."""
    import httpx

    url = f"http://{host}:{port}/api/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=1.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _run_server_thread(host: str, port: int, server_ref: list) -> None:
    """Run uvicorn in a thread, storing Server reference for graceful stop."""
    import asyncio
    from uvicorn import Config, Server

    config = Config(
        "agentwall.inspector.server:app",
        host=host,
        port=port,
        log_level="warning",
    )
    srv = Server(config)
    server_ref.append(srv)
    asyncio.run(srv.serve())


def launch_desktop(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Launch the AgentWall Inspector as a native desktop window.

    Starts the FastAPI backend in a daemon thread, waits for it to be ready,
    then opens a PyWebView window. When the window is closed, signals uvicorn
    to stop gracefully so the terminal returns immediately with no zombie process.
    """
    import webview

    _server_ref: list = []
    t = threading.Thread(
        target=_run_server_thread,
        args=(host, port, _server_ref),
        daemon=True,
    )
    t.start()

    if not _wait_for_server(host, port):
        raise RuntimeError(
            f"AgentWall Inspector backend failed to start at http://{host}:{port}"
        )

    url = f"http://{host}:{port}"
    webview.create_window("AgentWall Inspector", url, width=1280, height=800, resizable=True)
    webview.start()

    # Graceful shutdown sequence:
    #   1. Signal uvicorn to drain and stop accepting new requests.
    #   2. Wait up to 5 s for the server thread to finish.
    #   3. Force-exit the interpreter.
    #
    # Step 3 is required on Windows: the EdgeWebView2 (Chromium) runtime spawns
    # non-daemon COM threads that survive after webview.start() returns and cannot
    # be joined or cleaned up from Python. Without os._exit(0) the interpreter
    # hangs indefinitely. SQLite WAL mode guarantees no corruption on abrupt exit
    # because committed transactions are already durable in the WAL file.
    if _server_ref:
        _server_ref[0].should_exit = True
    t.join(timeout=5)
    os._exit(0)
