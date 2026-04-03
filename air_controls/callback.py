"""
LangChain / LangGraph callback handler for AIR Controls.

Drop-in integration — add two lines of code to any chain:

    from air_controls import ControlsCallback

    cb = ControlsCallback(agent_name="sales-bot")
    chain.invoke({"input": "..."}, config={"callbacks": [cb]})
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Union

from air_controls.store import EventStore


class ControlsCallback:
    """
    LangChain-compatible callback handler that logs all agent actions
    to the AIR Controls event store.

    Works with LangChain's BaseCallbackHandler interface without
    requiring langchain as a dependency — we duck-type the interface
    so the package stays lightweight.
    """

    def __init__(
        self,
        agent_name: str,        framework: str = "langchain",
        db_path: Optional[str] = None,
        verbose: bool = False,
    ):
        self.agent_name = agent_name
        self.agent_id = agent_name.lower().replace(" ", "-")
        self.framework = framework
        self.verbose = verbose
        self.store = EventStore(db_path)
        self.store.ensure_agent(self.agent_id, agent_name, framework)

        # Track timing for duration calculation
        self._timers: Dict[str, float] = {}

    def _log(self, msg: str):
        if self.verbose:
            print(f"[AIR Controls] {msg}")

    def _start_timer(self, run_id: str):
        self._timers[run_id] = time.time()

    def _get_duration(self, run_id: str) -> int:
        start = self._timers.pop(run_id, None)
        if start:
            return int((time.time() - start) * 1000)
        return 0

    # ── LLM callbacks ──────────────────────────────────────────
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: Optional[Any] = None,
        **kwargs,
    ):
        """Called when an LLM call starts."""
        rid = str(run_id or uuid.uuid4())
        self._start_timer(rid)
        self._log(f"LLM call started (run={rid[:8]})")

    def on_llm_end(self, response: Any, *, run_id: Optional[Any] = None, **kwargs):
        """Called when an LLM call ends."""
        rid = str(run_id or "")
        duration = self._get_duration(rid)

        # Extract token usage if available
        tokens = 0
        cost = 0.0
        if hasattr(response, "llm_output") and response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            tokens = usage.get("total_tokens", 0)
            # Rough cost estimate (GPT-4 pricing as default)
            cost = tokens * 0.00003
        # Extract model response text
        output_text = ""
        if hasattr(response, "generations") and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    if hasattr(gen, "text"):
                        output_text = gen.text[:200]  # First 200 chars

        event_id = self.store.log_event(
            agent_id=self.agent_id,
            action_type="llm_call",
            raw_action=f"LLM completion ({tokens} tokens)",
            human_summary=f"AI generated a response ({tokens} tokens, {duration}ms)",
            tokens_used=tokens,
            cost_usd=cost,
            duration_ms=duration,
            output_data={"preview": output_text} if output_text else None,
        )
        self._log(f"LLM call logged: {event_id} ({tokens} tokens, {duration}ms)")

    def on_llm_error(self, error: Exception, *, run_id: Optional[Any] = None, **kwargs):
        """Called when an LLM call errors."""
        rid = str(run_id or "")
        duration = self._get_duration(rid)

        self.store.log_event(
            agent_id=self.agent_id,
            action_type="llm_error",
            raw_action=f"LLM error: {type(error).__name__}",
            human_summary=f"AI call failed: {str(error)[:100]}",
            duration_ms=duration,
            risk_score="high",
        )
    # ── Tool callbacks ─────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: Optional[Any] = None,
        **kwargs,
    ):
        """Called when a tool starts executing."""
        rid = str(run_id or uuid.uuid4())
        self._start_timer(rid)
        tool_name = serialized.get("name", "unknown_tool")
        self._log(f"Tool '{tool_name}' started (run={rid[:8]})")

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: Optional[Any] = None,
        name: Optional[str] = None,
        **kwargs,
    ):
        """Called when a tool finishes executing."""
        rid = str(run_id or "")
        duration = self._get_duration(rid)
        tool_name = name or "tool"
        event_id = self.store.log_event(
            agent_id=self.agent_id,
            action_type="tool_use",
            raw_action=f"Tool: {tool_name}",
            human_summary=f"Used tool '{tool_name}'",
            duration_ms=duration,
            output_data={"result": str(output)[:500]},
        )
        self._log(f"Tool '{tool_name}' logged: {event_id} ({duration}ms)")

    def on_tool_error(
        self,
        error: Exception,
        *,
        run_id: Optional[Any] = None,
        name: Optional[str] = None,
        **kwargs,
    ):
        """Called when a tool errors."""
        rid = str(run_id or "")
        duration = self._get_duration(rid)
        tool_name = name or "tool"

        self.store.log_event(
            agent_id=self.agent_id,
            action_type="tool_error",
            raw_action=f"Tool error: {tool_name} — {type(error).__name__}",
            human_summary=f"Tool '{tool_name}' failed: {str(error)[:100]}",
            duration_ms=duration,
            risk_score="medium",
        )
    # ── Chain callbacks ────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: Optional[Any] = None,
        **kwargs,
    ):
        """Called when a chain starts."""
        rid = str(run_id or uuid.uuid4())
        self._start_timer(rid)

    def on_chain_end(
        self, outputs: Dict[str, Any], *, run_id: Optional[Any] = None, **kwargs
    ):
        """Called when a chain finishes."""
        rid = str(run_id or "")
        duration = self._get_duration(rid)

        self.store.log_event(
            agent_id=self.agent_id,
            action_type="chain_end",
            raw_action="Chain execution completed",
            human_summary=f"Workflow completed ({duration}ms)",
            duration_ms=duration,
        )
    def on_chain_error(
        self, error: Exception, *, run_id: Optional[Any] = None, **kwargs
    ):
        """Called when a chain errors."""
        rid = str(run_id or "")
        duration = self._get_duration(rid)

        self.store.log_event(
            agent_id=self.agent_id,
            action_type="chain_error",
            raw_action=f"Chain error: {type(error).__name__}",
            human_summary=f"Workflow failed: {str(error)[:100]}",
            duration_ms=duration,
            risk_score="high",
        )

    # ── Agent callbacks ────────────────────────────────────────

    def on_agent_action(self, action: Any, *, run_id: Optional[Any] = None, **kwargs):
        """Called when an agent takes an action."""
        tool = getattr(action, "tool", "unknown")
        tool_input = str(getattr(action, "tool_input", ""))[:200]

        self.store.log_event(
            agent_id=self.agent_id,
            action_type="agent_action",
            raw_action=f"Agent action: {tool}",
            human_summary=f"Agent decided to use '{tool}'",
            input_data={"tool_input": tool_input},
        )
    def on_agent_finish(self, finish: Any, *, run_id: Optional[Any] = None, **kwargs):
        """Called when an agent finishes."""
        output = str(getattr(finish, "return_values", ""))[:200]

        self.store.log_event(
            agent_id=self.agent_id,
            action_type="agent_finish",
            raw_action="Agent finished",
            human_summary="Agent completed its task",
            output_data={"result": output},
        )

    # ── Retriever callbacks (for RAG) ──────────────────────────

    def on_retriever_start(self, serialized: Dict[str, Any], query: str, **kwargs):
        """Called when a retriever starts."""
        self._start_timer(f"retriever-{query[:20]}")

    def on_retriever_end(self, documents: List[Any], **kwargs):
        """Called when a retriever finishes."""
        self.store.log_event(
            agent_id=self.agent_id,
            action_type="retrieval",
            raw_action=f"Retrieved {len(documents)} documents",
            human_summary=f"Searched knowledge base and found {len(documents)} relevant documents",
        )