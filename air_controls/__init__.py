"""
AIR Controls — See what your AI agents actually do.

Runtime visibility for AI agents: action timeline, intent translation,
anomaly detection, and guardrails. Part of the AIR Blackbox ecosystem.

Usage:
    from air_controls import ControlsCallback  # LangChain
    from air_controls import monitor           # Custom agents (decorator)
    from air_controls import CrewMonitor       # CrewAI
    from air_controls import AutoGenMonitor    # AutoGen
"""

__version__ = "0.1.0"

from air_controls.store import EventStore
from air_controls.callback import ControlsCallback
from air_controls.decorator import monitor
from air_controls.crew import CrewMonitor
from air_controls.autogen import AutoGenMonitor

__all__ = [
    "EventStore",
    "ControlsCallback",
    "monitor",
    "CrewMonitor",
    "AutoGenMonitor",
]