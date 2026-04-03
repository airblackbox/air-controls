"""
CrewAI integration for AIR Controls.

Usage:
    from air_controls import CrewMonitor

    monitor = CrewMonitor(agent_name="research-crew")
    result = monitor.run(crew)
"""

import time
from typing import Any, Optional

from air_controls.store import EventStore


class CrewMonitor:
    """Monitor CrewAI crew executions."""

    def __init__(self, agent_name: str, db_path: Optional[str] = None,
                 verbose: bool = False):
        self.agent_name = agent_name
        self.agent_id = agent_name.lower().replace(" ", "-")
        self.verbose = verbose
        self.store = EventStore(db_path)
        self.store.ensure_agent(self.agent_id, agent_name, "crewai")
    def run(self, crew: Any, inputs: Optional[dict] = None) -> Any:
        """
        Run a CrewAI crew with monitoring.

        Wraps crew.kickoff() and logs task-level events.
        """
        if self.store.is_agent_paused(self.agent_id):
            raise RuntimeError(
                f"Agent '{self.agent_name}' is paused via AIR Controls kill switch."
            )

        start = time.time()

        self.store.log_event(
            agent_id=self.agent_id,
            action_type="crew_start",
            raw_action="crew.kickoff()",
            human_summary=f"Crew '{self.agent_name}' started execution",
        )

        try:
            if inputs:
                result = crew.kickoff(inputs=inputs)
            else:
                result = crew.kickoff()

            duration = int((time.time() - start) * 1000)
            # Try to extract task results
            task_count = 0
            if hasattr(crew, "tasks"):
                task_count = len(crew.tasks)

            self.store.log_event(
                agent_id=self.agent_id,
                action_type="crew_end",
                raw_action=f"Crew completed ({task_count} tasks, {duration}ms)",
                human_summary=f"Crew finished {task_count} tasks in {duration}ms",
                duration_ms=duration,
                output_data={"result_preview": str(result)[:500]},
            )

            if self.verbose:
                print(f"[AIR Controls] Crew '{self.agent_name}' completed in {duration}ms")

            return result

        except Exception as e:
            duration = int((time.time() - start) * 1000)
            self.store.log_event(
                agent_id=self.agent_id,
                action_type="crew_error",
                raw_action=f"Crew error: {type(e).__name__}",
                human_summary=f"Crew failed after {duration}ms: {str(e)[:100]}",
                duration_ms=duration,
                risk_score="high",
            )
            raise