"""
AutoGen integration for AIR Controls.

Usage:
    from air_controls import AutoGenMonitor

    monitor = AutoGenMonitor(agent_name="coding-assistant")
    monitor.attach(agent)  # patches send/receive
"""

import time
from typing import Any, Optional

from air_controls.store import EventStore


class AutoGenMonitor:
    """Monitor AutoGen agent message passing."""

    def __init__(self, agent_name: str, db_path: Optional[str] = None,
                 verbose: bool = False):
        self.agent_name = agent_name
        self.agent_id = agent_name.lower().replace(" ", "-")
        self.verbose = verbose
        self.store = EventStore(db_path)
        self.store.ensure_agent(self.agent_id, agent_name, "autogen")
    def attach(self, agent: Any):
        """
        Attach monitoring to an AutoGen agent by patching its message handling.

        Works with autogen ConversableAgent and subclasses.
        """
        if self.store.is_agent_paused(self.agent_id):
            raise RuntimeError(
                f"Agent '{self.agent_name}' is paused via AIR Controls kill switch."
            )

        original_send = getattr(agent, "send", None)
        original_receive = getattr(agent, "receive", None)
        monitor = self

        if original_send:
            def patched_send(message, recipient, *args, **kwargs):
                start = time.time()
                result = original_send(message, recipient, *args, **kwargs)
                duration = int((time.time() - start) * 1000)

                recipient_name = getattr(recipient, "name", str(recipient))
                msg_preview = str(message)[:200] if message else ""

                monitor.store.log_event(
                    agent_id=monitor.agent_id,
                    action_type="message_send",
                    raw_action=f"send() → {recipient_name}",
                    human_summary=f"Sent message to '{recipient_name}'",
                    duration_ms=duration,
                    input_data={"message_preview": msg_preview},
                )
                if monitor.verbose:
                    print(f"[AIR Controls] Message sent to '{recipient_name}'")

                return result

            agent.send = patched_send

        if original_receive:
            def patched_receive(message, sender, *args, **kwargs):
                start = time.time()
                result = original_receive(message, sender, *args, **kwargs)
                duration = int((time.time() - start) * 1000)

                sender_name = getattr(sender, "name", str(sender))
                msg_preview = str(message)[:200] if message else ""

                monitor.store.log_event(
                    agent_id=monitor.agent_id,
                    action_type="message_receive",
                    raw_action=f"receive() ← {sender_name}",
                    human_summary=f"Received message from '{sender_name}'",
                    duration_ms=duration,
                    input_data={"message_preview": msg_preview},
                )

                return result

            agent.receive = patched_receive

        self.store.log_event(
            agent_id=self.agent_id,
            action_type="monitor_attached",
            raw_action="AutoGenMonitor.attach()",
            human_summary=f"Monitoring attached to agent '{self.agent_name}'",
        )

        if self.verbose:
            print(f"[AIR Controls] Monitoring attached to '{self.agent_name}'")