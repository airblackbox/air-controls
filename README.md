# AIR Controls

**See what your AI agents actually do.**

Runtime visibility for AI agents: action timeline, intent translation, anomaly detection, and guardrails. Part of the [AIR Blackbox](https://airblackbox.ai) ecosystem.

```
pip install air-controls
```

## Why

Companies are deploying AI agents that send emails, update CRMs, and run workflows. Nobody knows what these agents are actually doing. Logs exist but are useless. Observability tools are too technical. There's no "understandable layer."

AIR Controls fixes that.

## Quick Start

### LangChain / LangGraph

```python
from air_controls import ControlsCallback

cb = ControlsCallback(agent_name="sales-bot")
chain.invoke({"input": "..."}, config={"callbacks": [cb]})
# That's it. Run `air-controls status` to see the dashboard.
```

### Custom Agents (OpenAI / Anthropic API)

```python
from air_controls import monitor

@monitor(agent_name="my-bot")
def process_customer(query):
    response = openai.chat.completions.create(...)
    return response

# Or as a context manager with manual logging:
with monitor(agent_name="my-bot") as m:
    response = openai.chat.completions.create(...)
    m.log("api_call", "POST /v1/chat/completions", "Generated AI response")
```

### CrewAI

```python
from air_controls import CrewMonitor

mon = CrewMonitor(agent_name="research-crew")
result = mon.run(crew)
```

### AutoGen
```python
from air_controls import AutoGenMonitor

mon = AutoGenMonitor(agent_name="coding-assistant")
mon.attach(agent)
```

## CLI

```bash
air-controls status              # Show all agents and recent activity
air-controls events sales-bot    # Show event timeline for an agent
air-controls stats sales-bot     # Detailed statistics
air-controls pause sales-bot     # Kill switch — pause an agent
air-controls resume sales-bot    # Resume a paused agent
air-controls verify              # Verify audit chain integrity
```

## What Gets Tracked

Every agent action is logged as a structured event:

- **Action type**: LLM call, tool use, API call, decision, error
- **Human summary**: Plain English translation of what happened
- **Cost**: Token usage and dollar cost per action
- **Duration**: How long each action took
- **Risk score**: Low / medium / high based on action type
- **Audit chain**: HMAC-SHA256 tamper-evident chain (shared with AIR Blackbox)
## Features

| Feature | Status |
|---------|--------|
| Action timeline | ✅ Shipped |
| LangChain callback | ✅ Shipped |
| CrewAI monitor | ✅ Shipped |
| AutoGen monitor | ✅ Shipped |
| Custom agent decorator | ✅ Shipped |
| CLI dashboard | ✅ Shipped |
| Kill switch | ✅ Shipped |
| HMAC-SHA256 audit chain | ✅ Shipped |
| Web dashboard | 🔜 Coming |
| Intent translation | 🔜 Coming |
| Anomaly detection | 🔜 Coming |
| Guardrails & rate limits | 🔜 Coming |

## How It Fits

```
AIR Blackbox (pre-deploy)  →  Scans code for EU AI Act compliance
AIR Controls (runtime)     →  Monitors what agents actually do
                ↓
    Same HMAC-SHA256 audit chain
```

## Local-First

Your agent telemetry never leaves your machine. Everything runs locally on SQLite. No cloud. No phone-home. No API keys needed.
Set a custom DB path:

```bash
export AIR_CONTROLS_DB=/path/to/events.db
```

## License

Apache 2.0

## Links

- **Website**: [airblackbox.ai](https://airblackbox.ai)
- **GitHub**: [github.com/airblackbox/air-controls](https://github.com/airblackbox/air-controls)
- **PyPI**: [pypi.org/project/air-controls](https://pypi.org/project/air-controls/)