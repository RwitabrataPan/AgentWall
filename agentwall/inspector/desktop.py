from __future__ import annotations

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


def _run_server_thread(host: str, port: int) -> None:
    """Run uvicorn in a daemon thread."""
    import asyncio
    from uvicorn import Config, Server

    config = Config(
        "agentwall.inspector.server:app",
        host=host,
        port=port,
        log_level="warning",
    )
    server = Server(config)

    asyncio.run(server.serve())


def launch_desktop(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Launch the AgentWall Inspector as a native desktop window.

    Starts the FastAPI backend in a daemon thread, waits for it to be ready,
    then opens a PyWebView window. Blocks until the window is closed.
    """
    import webview

    t = threading.Thread(target=_run_server_thread, args=(host, port), daemon=True)
    t.start()

    if not _wait_for_server(host, port):
        raise RuntimeError(
            f"AgentWall Inspector backend failed to start at http://{host}:{port}"
        )

    url = f"http://{host}:{port}"
    webview.create_window("AgentWall Inspector", url, width=1280, height=800, resizable=True)
    webview.start()
