from __future__ import annotations

import importlib
import threading
from pathlib import Path
from typing import Annotated

import typer

from agentwall import __version__

app = typer.Typer(name="agentwall", help="AgentWall - AI Agent Runtime Security.", add_completion=False)

_INSPECTOR_HOST = "127.0.0.1"
_INSPECTOR_PORT = 8080

_PROVIDER_NAMES = ["openai", "anthropic", "groq", "deepseek", "ollama"]

_PROVIDER_MODELS: dict[str, list[str]] = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "ollama": ["llama3.2", "llama3.1", "mistral", "gemma2", "phi3"],
}

_NO_API_KEY_PROVIDERS = {"ollama"}


def _get_db():
    from agentwall.storage.database import Database
    return Database()


@app.command()
def version() -> None:
    """Print version."""
    typer.echo(f"agentwall {__version__}")


@app.command()
def doctor() -> None:
    """Check installation health."""
    checks = [
        ("keyring", "API key storage (keyring)"),
        ("sqlalchemy", "ORM (sqlalchemy)"),
        ("fastapi", "Inspector API (fastapi)"),
        ("uvicorn", "Inspector server (uvicorn)"),
        ("pydantic", "Validation (pydantic)"),
        ("openai", "OpenAI/Groq/DeepSeek SDK (openai)"),
        ("anthropic", "Anthropic SDK (anthropic)"),
        ("webview", "Desktop Inspector (pywebview)"),
    ]
    all_ok = True
    for module, label in checks:
        try:
            importlib.import_module(module)
            typer.echo(f"  OK  {label}")
        except ImportError:
            typer.echo(f"  MISSING  {label}")
            all_ok = False

    if all_ok:
        typer.echo("\nAgentWall installation OK.")
    else:
        typer.echo("\nSome dependencies missing. Run: pip install agentwall")
        raise typer.Exit(1)


@app.command()
def config(
    provider: Annotated[str | None, typer.Option(help="Provider name")] = None,
    model: Annotated[str | None, typer.Option(help="Model name")] = None,
    priority: Annotated[int | None, typer.Option(help="Priority (1=primary)")] = None,
    low_threshold: Annotated[float | None, typer.Option(help="Low risk threshold")] = None,
    high_threshold: Annotated[float | None, typer.Option(help="High risk threshold")] = None,
    status: Annotated[bool, typer.Option("--status", help="Show provider health")] = False,
) -> None:
    """Configure AgentWall. No flags = interactive wizard."""
    from agentwall.core.config_manager import ConfigManager

    db = _get_db()
    mgr = ConfigManager(db)

    if status:
        _show_status(db)
        db.close()
        return

    non_interactive = any(x is not None for x in [provider, model, priority, low_threshold, high_threshold])

    if non_interactive:
        _apply_config_flags(mgr, provider, model, priority, low_threshold, high_threshold)
    else:
        _run_wizard(mgr, db)

    db.close()


def _apply_config_flags(mgr, provider, model, priority, low_threshold, high_threshold):
    if provider and model:
        from agentwall.providers.keyring import store_api_key
        p = priority or 0
        if provider not in _NO_API_KEY_PROVIDERS:
            api_key = typer.prompt(f"API key for {provider}", hide_input=True)
            if api_key:
                store_api_key(provider, api_key)
                typer.echo(f"API key stored in OS keyring for {provider}.")
        mgr.set_provider(provider, model, priority=p)
        typer.echo(f"Set {provider} → {model} (priority={p})")

    if low_threshold is not None or high_threshold is not None:
        current = mgr.get_thresholds()
        low = low_threshold if low_threshold is not None else current["low_threshold"]
        high = high_threshold if high_threshold is not None else current["high_threshold"]
        mgr.set_thresholds(low, high)
        typer.echo(f"Thresholds: low={low} high={high}")


def _run_wizard(mgr, db) -> None:
    typer.echo("\nAgentWall Configuration Wizard")
    typer.echo("=" * 32)

    _print_current_config(mgr)

    actions = [
        "Add / update provider",
        "Remove provider",
        "Set risk thresholds",
        "Test provider connections",
        "Exit",
    ]
    typer.echo("\nWhat would you like to do?")
    for i, a in enumerate(actions, 1):
        typer.echo(f"  {i}. {a}")

    choice = typer.prompt("Select", default="1")
    try:
        idx = int(choice) - 1
        action = actions[idx]
    except (ValueError, IndexError):
        typer.echo("Invalid selection.")
        return

    if action == "Add / update provider":
        _wizard_add_provider(mgr)
    elif action == "Remove provider":
        _wizard_remove_provider(mgr)
    elif action == "Set risk thresholds":
        _wizard_thresholds(mgr)
    elif action == "Test provider connections":
        _show_status(db)


def _print_current_config(mgr) -> None:
    providers = mgr.list_providers_ordered()
    thresholds = mgr.get_thresholds()

    typer.echo(f"\nRisk thresholds: low={thresholds['low_threshold']} high={thresholds['high_threshold']}")
    if providers:
        typer.echo("Providers (by priority):")
        for p in providers:
            status = "enabled" if p.enabled else "disabled"
            typer.echo(f"  [{p.priority}] {p.provider} → {p.model}  ({status})")
    else:
        typer.echo("No providers configured.")


def _wizard_add_provider(mgr) -> None:
    typer.echo("\nAvailable providers:")
    for i, name in enumerate(_PROVIDER_NAMES, 1):
        typer.echo(f"  {i}. {name}")

    raw = typer.prompt("Select provider (name or number)", default="openai")
    if raw.isdigit():
        idx = int(raw) - 1
        provider_name = _PROVIDER_NAMES[idx] if 0 <= idx < len(_PROVIDER_NAMES) else raw
    else:
        provider_name = raw.lower().strip()

    if provider_name not in _PROVIDER_NAMES:
        typer.echo(f"Unknown provider: {provider_name}")
        return

    # API key (skip for Ollama)
    if provider_name not in _NO_API_KEY_PROVIDERS:
        api_key = typer.prompt(f"API key for {provider_name}", hide_input=True)
        if api_key:
            from agentwall.providers.keyring import store_api_key
            store_api_key(provider_name, api_key)
            typer.echo(f"API key stored in OS keyring for {provider_name}.")

    # Model selection
    models = _PROVIDER_MODELS.get(provider_name, [])
    typer.echo(f"\nAvailable models for {provider_name}:")
    for i, m in enumerate(models, 1):
        default_marker = " (default)" if i == 2 else ""
        typer.echo(f"  {i}. {m}{default_marker}")
    model_raw = typer.prompt("Select model (name or number)", default="2" if len(models) >= 2 else "1")
    if model_raw.isdigit():
        idx = int(model_raw) - 1
        model_name = models[idx] if 0 <= idx < len(models) else models[0]
    else:
        model_name = model_raw.strip()

    # Priority
    existing = mgr.list_providers_ordered()
    next_priority = max((p.priority for p in existing), default=0) + 1
    priority = typer.prompt(f"Priority (1=primary, higher=fallback)", default=str(next_priority), type=int)

    # Test connection
    typer.echo(f"\nTesting connection to {provider_name}...")
    try:
        cls = _load_evaluator_class(provider_name)
        from agentwall.providers.keyring import get_api_key
        api_key_val = get_api_key(provider_name) if provider_name not in _NO_API_KEY_PROVIDERS else None
        kwargs = {"model": model_name}
        if api_key_val:
            kwargs["api_key"] = api_key_val
        evaluator = cls(**kwargs)
        result = evaluator.health_check()
        if result.health.value == "healthy":
            typer.echo(f"Connection OK  ({result.latency_ms:.0f}ms)")
        else:
            typer.echo(f"Warning: {result.error}")
            if not typer.confirm("Save anyway?"):
                return
    except Exception as e:
        typer.echo(f"Connection failed: {e}")
        if not typer.confirm("Save anyway?"):
            return

    mgr.set_provider(provider_name, model_name, priority=priority)
    typer.echo(f"\nSaved: {provider_name} → {model_name} (priority={priority})")


def _wizard_remove_provider(mgr) -> None:
    providers = mgr.list_providers_ordered()
    if not providers:
        typer.echo("No providers configured.")
        return
    typer.echo("\nConfigured providers:")
    for i, p in enumerate(providers, 1):
        typer.echo(f"  {i}. {p.provider}")
    raw = typer.prompt("Select provider to remove")
    if raw.isdigit():
        idx = int(raw) - 1
        name = providers[idx].provider if 0 <= idx < len(providers) else raw
    else:
        name = raw.strip()
    if typer.confirm(f"Remove {name}?"):
        mgr.remove_provider(name)
        from agentwall.providers.keyring import delete_api_key
        delete_api_key(name)
        typer.echo(f"Removed {name} (API key deleted from keyring).")


def _wizard_thresholds(mgr) -> None:
    current = mgr.get_thresholds()
    typer.echo(f"\nCurrent: low={current['low_threshold']} high={current['high_threshold']}")
    low = typer.prompt("Low threshold (ALLOW below this)", default=str(current["low_threshold"]), type=float)
    high = typer.prompt("High threshold (LLM eval above this)", default=str(current["high_threshold"]), type=float)
    if low >= high:
        typer.echo("Error: low_threshold must be less than high_threshold.")
        return
    mgr.set_thresholds(low, high)
    typer.echo(f"Saved: low={low} high={high}")


def _show_status(db) -> None:
    from agentwall.providers.registry import ProviderRegistry
    from agentwall.providers.base import ProviderHealth

    reg = ProviderRegistry(db)
    statuses = reg.health_check_all()

    if not statuses:
        typer.echo("No providers configured. Run: agentwall config")
        return

    typer.echo("\nProvider Status:")
    for s in statuses:
        icon = "OK" if s.health == ProviderHealth.HEALTHY else ("WARN" if s.health == ProviderHealth.DEGRADED else "FAIL")
        latency = f" {s.latency_ms:.0f}ms" if s.latency_ms is not None else ""
        error = f" — {s.error}" if s.error else ""
        typer.echo(f"  [{icon}] {s.provider} ({s.model}){latency}{error}")


def _load_evaluator_class(provider_name: str):
    from agentwall.providers.registry import EVALUATOR_CLASSES
    cls = EVALUATOR_CLASSES.get(provider_name)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_name}")
    return cls


@app.command()
def inspect(
    host: Annotated[str, typer.Option(help="Bind host")] = _INSPECTOR_HOST,
    port: Annotated[int, typer.Option(help="Bind port")] = _INSPECTOR_PORT,
    browser: Annotated[bool, typer.Option("--browser", help="Open in browser instead of desktop window")] = False,
) -> None:
    """Launch AgentWall Inspector as a desktop window."""
    ui_dist = Path(__file__).parent.parent / "inspector" / "ui" / "dist"
    if not ui_dist.exists():
        typer.echo(
            "UI not built. Run:\n"
            "  cd agentwall/inspector/ui && npm install && npm run build"
        )
        typer.echo("Starting API-only mode (docs at /api/docs)...")

    if browser:
        _launch_browser(host, port)
    else:
        from agentwall.inspector.desktop import launch_desktop
        typer.echo("Starting AgentWall Inspector...")
        launch_desktop(host, port)


def _launch_browser(host: str, port: int) -> None:
    """Fallback: start uvicorn and open the system browser."""
    import uvicorn
    import webbrowser

    url = f"http://{host}:{port}"
    typer.echo(f"Starting AgentWall Inspector at {url}")

    def _open():
        import time
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "agentwall.inspector.server:app",
        host=host,
        port=port,
        log_level="warning",
    )
