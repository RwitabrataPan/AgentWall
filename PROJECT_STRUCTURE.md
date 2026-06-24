# AgentWall Project Structure

```
agentwall/
├── __init__.py                    # Public API: protect_agent, protect_tool
├── cli/
│   └── main.py                    # Typer CLI: version, doctor, config, inspect
├── core/
│   ├── config_manager.py          # DB config: providers, thresholds
│   ├── event_manager.py           # Tool event recording and retrieval
│   ├── session_manager.py         # Session lifecycle
│   └── types.py                   # ToolType, ToolAction, ResourceCategory, Decision, RuntimeEvent, EvalContext
├── inspector/
│   ├── deps.py                    # FastAPI dependency injection
│   ├── desktop.py                 # PyWebView launcher
│   ├── event_bus.py               # In-process pub/sub for WebSocket push
│   ├── routes/                    # FastAPI routers (sessions, events, goals, policies, providers, config, export, ws)
│   ├── server.py                  # FastAPI app assembly + lifespan
│   └── ui/
│       ├── dist/                  # Built React app (shipped in wheel)
│       │   ├── index.html
│       │   └── assets/
│       └── src/                   # React source (not shipped in wheel)
├── integrations/
│   ├── crewai.py                  # protect_crewai_crew()
│   ├── langchain.py               # protect_langchain_agent()
│   └── openai_agents.py           # protect_openai_agent()
├── interceptors/
│   ├── __init__.py                # protect_agent(), protect_tool() exports
│   ├── agent.py                   # ProtectedAgent class
│   ├── base.py                    # BaseInterceptor abstract class
│   └── tool.py                    # ToolInterceptor, protect_tool()
├── providers/
│   ├── anthropic.py               # AnthropicEvaluator
│   ├── base.py                    # BaseEvaluator, build_prompt(), parse_llm_response()
│   ├── chain.py                   # ProviderChain
│   ├── deepseek.py                # DeepSeekEvaluator
│   ├── groq.py                    # GroqEvaluator
│   ├── keyring.py                 # store_api_key(), get_api_key(), delete_api_key()
│   ├── ollama.py                  # OllamaEvaluator
│   ├── openai.py                  # OpenAIEvaluator
│   └── registry.py                # ProviderRegistry, EVALUATOR_CLASSES
├── security/
│   ├── detectors.py               # SensitiveResourceDetector, ScopeExpansionDetector, DataExfiltrationDetector
│   ├── engine.py                  # SecurityEngine, build_default_engine()
│   ├── exceptions.py              # AgentWallSecurityException
│   ├── goal_tracker.py            # GoalTracker, goal segment lifecycle, transition heuristics
│   ├── policy_engine.py           # PolicyEngine
│   ├── result_analyzer.py         # ResultAnalyzer, ResultClassification, AnalysisResult
│   └── rules.py                   # Risk scoring rules
└── storage/
    ├── database.py                # Database (SQLite, SQLAlchemy)
    └── models.py                  # ORM models: Session, ToolEvent, Evaluation, GoalSegment, Policy, ProviderSetting

tests/
├── conftest.py                    # db fixture (tempfile.mkdtemp)
├── integration/
│   ├── test_crewai_integration.py
│   ├── test_langchain_integration.py
│   └── test_openai_agents_integration.py
├── test_cli.py
├── test_config_manager.py
├── test_detectors.py
├── test_engine_defaults.py
├── test_event_manager.py
├── test_goal_inference.py
├── test_goal_tracker.py
├── test_event_bus.py
├── test_inspector_desktop.py
├── test_inspector_routes.py
├── test_interceptors.py
├── test_parse_robust.py
├── test_policy_engine.py
├── test_policy_priority.py
├── test_post_execution.py
├── test_provider_keyring.py
├── test_providers.py
├── test_registry.py
├── test_result_analyzer.py
├── test_security_engine.py
├── test_security_rules.py
├── test_session_manager.py
└── test_storage.py

examples/
├── crewai/example.py
├── langchain/example.py
└── openai_agents/example.py

docs/
└── superpowers/
    ├── plans/
    └── specs/
```

## Key Design Boundaries

| Concern | Where |
|---------|-------|
| Public API | `agentwall/__init__.py`, `agentwall/interceptors/__init__.py` |
| Session lifecycle | `agentwall/core/session_manager.py` |
| Tool interception | `agentwall/interceptors/tool.py` |
| Post-execution analysis | `agentwall/security/result_analyzer.py` |
| Goal tracking | `agentwall/security/goal_tracker.py` |
| Evaluation logic | `agentwall/security/engine.py` |
| Risk scoring | `agentwall/security/rules.py` |
| Behavior detection | `agentwall/security/detectors.py` |
| User policies | `agentwall/security/policy_engine.py` |
| LLM evaluation | `agentwall/providers/` |
| Storage | `agentwall/storage/` |
| Configuration | `agentwall/core/config_manager.py` |
| Inspector backend | `agentwall/inspector/` |
| Inspector UI | `agentwall/inspector/ui/dist/` |
| CLI | `agentwall/cli/main.py` |
