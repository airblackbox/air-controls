"""
Decorator for monitoring custom agents (OpenAI / Anthropic API direct).

Usage:
    from air_controls import monitor

    @monitor(agent_name="my-bot")
    def process_customer(query):
        response = openai.chat.completions.create(...)
        return response

    # Or as a context manager:
    with monitor(agent_name="my-bot") as m:
        response = openai.chat.completions.create(...)
        m.log("api_call", "POST /v1/chat/completions", "Generated AI response")
"""

import functools
import time
from typing import Any, Callable, Optional

from air_controls.store import EventStore


class MonitorContext:
    """Context manager for monitoring a block of agent code."""

    def __init__(self, agent_name: str, framework: str = "custom",
                 db_path: Optional[str] = None, verbose: bool = False):
        self.agent_name = agent_name
        self.agent_id = agent_name.lower().replace(" ", "-")        self.framework = framework
        self.verbose = verbose
        self.store = EventStore(db_path)
        self.store.ensure_agent(self.agent_id, agent_name, framework)
        self._start_time: Optional[float] = None
        self._events_logged = 0

    def __enter__(self):
        self._start_time = time.time()
        if self.verbose:
            print(f"[AIR Controls] Monitoring '{self.agent_name}' started")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = int((time.time() - (self._start_time or time.time())) * 1000)

        if exc_type:
            self.store.log_event(
                agent_id=self.agent_id,
                action_type="error",
                raw_action=f"Error: {exc_type.__name__}",
                human_summary=f"Agent failed: {str(exc_val)[:100]}",
                duration_ms=duration,
                risk_score="high",
            )
            if self.verbose:
                print(f"[AIR Controls] '{self.agent_name}' errored after {duration}ms")        else:
            self.store.log_event(
                agent_id=self.agent_id,
                action_type="session_end",
                raw_action=f"Session completed ({self._events_logged} actions logged)",
                human_summary=f"Agent session completed with {self._events_logged} actions",
                duration_ms=duration,
            )
            if self.verbose:
                print(f"[AIR Controls] '{self.agent_name}' completed in {duration}ms ({self._events_logged} actions)")

        return False  # Don't suppress exceptions

    def log(
        self,
        action_type: str = "action",
        raw_action: str = "",
        human_summary: str = "",
        tokens_used: int = 0,
        cost_usd: float = 0.0,
        risk_score: str = "low",
        **kwargs,
    ) -> str:
        """
        Log an action within the monitored block.

        Returns the event ID.
        """
        event_id = self.store.log_event(            agent_id=self.agent_id,
            action_type=action_type,
            raw_action=raw_action,
            human_summary=human_summary,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            risk_score=risk_score,
            **kwargs,
        )
        self._events_logged += 1
        if self.verbose:
            print(f"[AIR Controls]   → {human_summary or raw_action}")
        return event_id


class _MonitorProxy:
    """
    Proxy that works as both a decorator and a context manager.

    As a decorator:
        @monitor(agent_name="my-bot")
        def process(query): ...

    As a context manager:
        with monitor(agent_name="my-bot") as m:
            m.log("api_call", "POST /v1/chat", "Called OpenAI")
    """

    def __init__(self, agent_name: str, framework: str = "custom",
                 db_path: Optional[str] = None, verbose: bool = False):        self._agent_name = agent_name
        self._framework = framework
        self._db_path = db_path
        self._verbose = verbose
        self._ctx: Optional[MonitorContext] = None

    def _make_ctx(self) -> MonitorContext:
        return MonitorContext(self._agent_name, self._framework,
                             self._db_path, self._verbose)

    # ── Decorator usage ────────────────────────────────────────

    def __call__(self, func: Callable) -> Callable:
        ctx = self._make_ctx()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()

            # Check kill switch
            if ctx.store.is_agent_paused(ctx.agent_id):
                raise RuntimeError(
                    f"Agent '{self._agent_name}' is paused via AIR Controls kill switch. "
                    f"Resume with: air-controls resume {ctx.agent_id}"
                )

            try:
                result = func(*args, **kwargs)
                duration = int((time.time() - start) * 1000)
                ctx.store.log_event(
                    agent_id=ctx.agent_id,
                    action_type="function_call",
                    raw_action=f"Called {func.__name__}()",
                    human_summary=f"Agent ran '{func.__name__}' ({duration}ms)",
                    duration_ms=duration,
                )

                if self._verbose:
                    print(f"[AIR Controls] {func.__name__}() completed in {duration}ms")

                return result

            except Exception as e:
                duration = int((time.time() - start) * 1000)
                ctx.store.log_event(
                    agent_id=ctx.agent_id,
                    action_type="error",
                    raw_action=f"Error in {func.__name__}(): {type(e).__name__}",
                    human_summary=f"Agent '{func.__name__}' failed: {str(e)[:100]}",
                    duration_ms=duration,
                    risk_score="high",
                )
                raise

        # Attach store and agent_id for direct access
        wrapper.store = ctx.store
        wrapper.agent_id = ctx.agent_id
        return wrapper

    # ── Context manager usage ──────────────────────────────────

    def __enter__(self):
        self._ctx = self._make_ctx()
        return self._ctx.__enter__()    def __exit__(self, *args):
        if self._ctx:
            return self._ctx.__exit__(*args)
        return False


def monitor(
    agent_name: str,
    framework: str = "custom",
    db_path: Optional[str] = None,
    verbose: bool = False,
):
    """
    Monitor an agent function or use as a context manager.

    As a decorator:
        @monitor(agent_name="my-bot")
        def process(query):
            ...

    As a context manager:
        with monitor(agent_name="my-bot") as m:
            m.log("api_call", "POST /v1/chat", "Called OpenAI")
    """
    return _MonitorProxy(agent_name, framework, db_path, verbose)
