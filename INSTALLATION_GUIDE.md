# AgentWall Installation Guide

---

## Requirements

- Python 3.12 or later
- pip 21.0 or later
- OS keyring support (see platform notes below)

---

## Installation

Choose **ONE** installation option.

### Core Package

```bash
pip install agentwall-security
```

Recommended if:

* You use a custom agent framework
* You only need the AgentWall SDK
* You do not use OpenAI Agents SDK, LangChain, or CrewAI

### OpenAI Agents SDK Integration

```bash
pip install agentwall-security[openai-agents]
```

Installs:

* AgentWall
* OpenAI Agents SDK integration dependencies

### LangChain Integration

```bash
pip install agentwall-security[langchain]
```

Installs:

* AgentWall
* LangChain
* LangChain OpenAI

### CrewAI Integration

```bash
pip install agentwall-security[crewai]
```

Installs:

* AgentWall
* CrewAI

### All Supported Integrations (Recommended)

```bash
pip install agentwall-security[integrations]
```

Installs:

* AgentWall
* OpenAI Agents SDK
* LangChain
* LangChain OpenAI
* CrewAI

You do **NOT** need to install `agentwall` separately when using an integration package. Integration packages include the core AgentWall package automatically.

### Verify Installation

```bash
agentwall version
agentwall doctor
```

`doctor` checks all required dependencies. Expected output:

```text
OK  API key storage (keyring)
OK  ORM (sqlalchemy)
OK  Inspector API (fastapi)
OK  Inspector server (uvicorn)
OK  Validation (pydantic)
OK  OpenAI/Groq/DeepSeek SDK (openai)
OK  Anthropic SDK (anthropic)
OK  Desktop Inspector (pywebview)

AgentWall installation OK.
```


---

## Configuration

### Interactive Wizard

```bash
agentwall config
```

Launches the configuration wizard.

Options:

1. Add / update provider
2. Remove provider
3. Set risk thresholds
4. Test provider connections
5. Exit

### Add a Provider (Non-Interactive)

```bash
agentwall config --provider openai --model gpt-4o-mini --priority 1
```

When prompted, enter your API key. It is stored in the OS keyring — not in any file.

### Set Thresholds

```bash
agentwall config --low-threshold 25 --high-threshold 65
```

Default:

- low = 30
- high = 70

Behavior:

- Actions scoring below `low-threshold` → ALLOW
- Actions scoring between thresholds → WARN
- Actions scoring above `high-threshold` → LLM evaluation (if a provider is configured)

## LLM Evaluation

LLM evaluation is optional.

Most actions are evaluated using:

- Rules
- Detectors
- Policies
- Risk scoring

Only high-risk or ambiguous actions escalate to an LLM evaluator.

Decision flow:

```text
Risk < LOW
→ ALLOW

LOW ≤ Risk < HIGH
→ WARN

Risk ≥ HIGH
→ LLM Evaluation
```

Without a configured provider:

```text
High-risk events are blocked instead of evaluated.
```

Rule-based evaluation continues to function normally even when no LLM provider is configured.

### Check Status

```bash
agentwall config --status
```

Shows provider health, latency, and any errors.

---

## Provider API Keys

AgentWall stores API keys in the OS credential store only.

| Provider | Where to get the key |
|---------|---------------------|
| openai | https://platform.openai.com/api-keys |
| anthropic | https://console.anthropic.com/settings/keys |
| groq | https://console.groq.com/keys |
| deepseek | https://platform.deepseek.com/api_keys |
| ollama | No key needed — runs locally |

Keys are never stored in files, databases, or environment variables by AgentWall.

---

## Ollama (Local LLM)

Ollama requires no API key. Install Ollama separately:

```
https://ollama.com/download
```

Pull a model:

```bash
ollama pull llama3.2
```

Configure in AgentWall:

```bash
agentwall config --provider ollama --model llama3.2 --priority 1
```

---

## Inspector

### Desktop Mode (Default)

```bash
agentwall inspect
```

Launches the AgentWall Inspector desktop application.

AgentWall automatically:

1. Starts backend services
2. Starts FastAPI
3. Opens a native PyWebView window
4. Loads the Inspector UI

No browser navigation is required.

Requires PyWebView (included in the default installation).

### Browser Mode

```bash
agentwall inspect --browser
```

Starts the API server and opens the system browser.

Use this mode on:

- Headless servers
- Remote Linux machines
- CI environments
- Systems without desktop GUI support

### Custom Host/Port

```bash
agentwall inspect --host 0.0.0.0 --port 9090
```

Default:

```text
127.0.0.1:8080
```

## Framework Integration

### OpenAI Agents SDK

```python
from agents import Agent, Runner, function_tool
from agentwall.integrations.openai_agents import protect_openai_agent
from agentwall.core.types import ToolType
from agentwall.security.exceptions import AgentWallSecurityException

@function_tool
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

agent = Agent(name="dev", instructions="Fix bugs.", tools=[read_file], model="gpt-4o-mini")

wall, protected = protect_openai_agent(
    agent,
    goal="Fix the auth bug in login.tsx",
    tool_type_map={"read_file": ToolType.FILESYSTEM},
)

try:
    result = await Runner.run(protected, "Read login.tsx")
except AgentWallSecurityException as e:
    print(f"Blocked: {e.decision.reason}")
finally:
    wall.end_session()
```

### LangChain

```python
from langchain_core.tools import tool
from langchain.agents import create_openai_tools_agent, AgentExecutor
from agentwall.integrations.langchain import protect_langchain_agent
from agentwall.core.types import ToolType

@tool
def read_file(path: str) -> str:
    """Read a file."""
    with open(path) as f:
        return f.read()

executor = AgentExecutor(agent=agent, tools=[read_file])

wall = protect_langchain_agent(
    executor,
    goal="Fix login bug",
    tool_type_map={"read_file": ToolType.FILESYSTEM},
)

result = executor.invoke({"input": "Read login.tsx"})
wall.end_session()
```

### CrewAI

```python
from crewai import Agent as CrewAgent, Task, Crew
from crewai.tools import tool
from agentwall.integrations.crewai import protect_crewai_crew
from agentwall.core.types import ToolType

@tool("Read File")
def read_file(path: str) -> str:
    """Read a file."""
    with open(path) as f:
        return f.read()

agent = CrewAgent(role="Developer", goal="Fix bugs", tools=[read_file])
task = Task(description="Fix login bug", expected_output="Fixed", agent=agent)
crew = Crew(agents=[agent], tasks=[task])

wall = protect_crewai_crew(crew, tool_type_map={"Read File": ToolType.FILESYSTEM})
result = crew.kickoff(inputs={"task": "Fix login bug"})
wall.end_session()
```

### Direct SDK

```python
from agentwall import protect_agent
from agentwall.core.types import ToolType, ToolAction

class MyAgent:
    def run(self, task):
        result = self.read(task)
        return result

agent = MyAgent()
wall = protect_agent(agent, goal="Analyze log files")

agent.read = wall.protect_tool(
    agent.read,
    tool_type=ToolType.FILESYSTEM,
    action=ToolAction.READ,
)

agent.run("Analyze the error logs")
wall.end_session()
```

---

## Goal Inference

`goal` is optional in all `protect_*` calls. When omitted, AgentWall infers the goal from the agent's first execution input.

```python
# Goal inferred from Runner.run() input
wall, protected = protect_openai_agent(agent)
result = await Runner.run(protected, "Fix the login page bug")
# wall.goal == "Fix the login page bug"

# Goal inferred from executor.invoke() input
wall = protect_langchain_agent(executor)
executor.invoke({"input": "Fix the login page bug"})
# wall.goal == "Fix the login page bug"
```

---

## Platform Notes

### Windows

- Keyring: Windows Credential Manager (built-in, no extra config)
- PyWebView: requires WebView2 runtime (usually pre-installed on Windows 11)
- If Inspector fails to open, use `--browser` flag

### macOS

- Keyring: macOS Keychain (built-in)
- PyWebView: uses WebKit (built-in)
- No extra dependencies needed

### Linux

- Keyring: requires libsecret (`sudo apt install libsecret-1-dev python3-secretstorage`)
- Alternative: install `keyrings.alt` for file-based fallback (less secure)
- PyWebView: requires GTK + WebKit2GTK (`sudo apt install python3-webview`)
- Headless servers: use `agentwall inspect --browser` and forward port

---

## Common Errors

### `keyring.errors.NoKeyringError`

No keyring backend available. On Linux:
```bash
pip install keyrings.alt
```

### `ModuleNotFoundError: No module named 'webview'`

PyWebView not installed or install failed:
```bash
pip install pywebview
```

On Linux, also install system dependencies:
```bash
sudo apt install python3-webview python3-gi gir1.2-webkit2-4.0
```

### Inspector fails to start

Check port is available:
```bash
agentwall inspect --port 8081
```

Or use browser mode:
```bash
agentwall inspect --browser
```

### `ValueError: No providers configured`

Run `agentwall config` to add a provider. Without a configured provider, high-risk events are blocked (not evaluated by LLM).

### `AgentWallSecurityException` in tests

Set `engine=SecurityEngine(detectors=[])` in tests to disable all detectors, or use a custom low threshold:
```python
engine = SecurityEngine(warn_threshold=100.0, block_threshold=100.0)
```

---

## Uninstall

```bash
pip uninstall agentwall
```

Data and config are stored at `~/.agentwall/`. Remove manually if needed:

```bash
rm -rf ~/.agentwall/
```

API keys in the OS keyring must be removed separately:
```bash
agentwall config  # → Remove provider (deletes key from keyring)
```
