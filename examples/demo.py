#!/usr/bin/env python3
"""
================================================================================
                      AIR Controls — Complete Demo Script
================================================================================

This demo showcases the AIR Controls runtime visibility layer for AI agents.

What AIR Controls provides:
  - EventStore: SQLite event storage with HMAC-SHA256 audit chain
  - @monitor decorator: Track custom agent functions automatically
  - Context manager: Wrap blocks of agent code with m.log() calls
  - Kill switch: Pause/resume agents at runtime
  - Audit verification: Verify event chain integrity

All data is stored locally in a SQLite database. No data leaves your machine.

Run this script:
    pip install air-controls
    python demo.py

================================================================================
"""

import sys
import tempfile
import time
from pathlib import Path

# Import AIR Controls components
from air_controls import EventStore, monitor


def print_section(title: str, level: int = 1):
    """Print a nicely formatted section header."""
    if level == 1:
        print("\n" + "=" * 80)
        print(f"  {title}".ljust(80))
        print("=" * 80)
    elif level == 2:
        print("\n" + "-" * 80)
        print(f"  {title}")
        print("-" * 80)


def s(msg: str):
    """Print a status message."""
    print(f"  [*] {msg}")


def ok(msg: str):
    """Print a success message."""
    print(f"  [✓] {msg}")


def data(label: str, value):
    """Print a data label and value."""
    print(f"  {label}: {value}")


# ============================================================================
# MAIN DEMO
# ============================================================================

def main():
    """Run the complete AIR Controls demo."""

    print("\n" + "=" * 80)
    print("       AIR Controls Demo — See what your AI agents actually do")
    print("=" * 80)

    # Create a temporary database so we don't mess with the real system
    temp_db = tempfile.NamedTemporaryFile(
        suffix=".db", delete=False, dir="/tmp"
    ).name
    print(f"\n  Database: {temp_db}\n")

    try:
        # Create ONE shared EventStore for the entire demo.
        # This keeps the HMAC-SHA256 chain consistent across all events.
        store = EventStore(temp_db)

        # =================================================================
        print_section("PART 1: Logging Agent Actions (EventStore API)")
        # =================================================================
        # The EventStore is the core of AIR Controls. It stores every
        # agent action as a structured event with an audit chain.

        # --- Sales Bot ---
        s("Registering sales-bot agent...")
        store.ensure_agent("sales-bot", "Sales Bot", "langchain")
        ok("sales-bot registered")

        s("Logging sales-bot actions...")
        store.log_event(
            agent_id="sales-bot",
            action_type="llm_call",
            raw_action="openai.chat.completions.create(model='gpt-4', ...)",
            human_summary="Generated personalized follow-up email for lead #4521",
            tokens_used=320,
            cost_usd=0.009,
            duration_ms=1240,
        )
        store.log_event(
            agent_id="sales-bot",
            action_type="api_call",
            raw_action="POST /api/salesforce/contacts/update",
            human_summary="Updated CRM contact record for Acme Corp",
            tokens_used=0,
            cost_usd=0.0,
            duration_ms=89,
        )
        store.log_event(
            agent_id="sales-bot",
            action_type="email_sent",
            raw_action="POST /api/send-email",
            human_summary="Sent follow-up email to sarah@acmecorp.com",
            duration_ms=210,
            metadata={"recipient": "sarah@acmecorp.com", "template": "follow_up_v3"},
        )
        ok("3 events logged for sales-bot")

        # --- Research Crew ---
        s("Registering research-crew agent...")
        store.ensure_agent("research-crew", "Research Crew", "crewai")
        ok("research-crew registered")

        s("Logging research-crew actions...")
        store.log_event(
            agent_id="research-crew",
            action_type="api_call",
            raw_action="GET /api/arxiv/search?q=transformer+architectures",
            human_summary="Queried knowledge base for transformer architecture papers",
            tokens_used=150,
            cost_usd=0.002,
            duration_ms=340,
        )
        store.log_event(
            agent_id="research-crew",
            action_type="analysis",
            raw_action="analyze_papers(results, depth='detailed')",
            human_summary="Analyzed 3 research papers on transformer architectures",
            tokens_used=890,
            cost_usd=0.025,
            duration_ms=4200,
        )
        store.log_event(
            agent_id="research-crew",
            action_type="llm_call",
            raw_action="anthropic.messages.create(model='claude-sonnet-4-20250514', ...)",
            human_summary="Generated executive summary of research findings",
            tokens_used=520,
            cost_usd=0.015,
            duration_ms=2100,
        )
        store.log_event(
            agent_id="research-crew",
            action_type="decision",
            raw_action="recommend_action(confidence=0.87)",
            human_summary="Recommended investing in attention mechanism optimization",
            risk_score="medium",
            duration_ms=50,
        )
        ok("4 events logged for research-crew")

        # --- Support Bot ---
        s("Registering support-bot agent...")
        store.ensure_agent("support-bot", "Support Bot", "custom")
        ok("support-bot registered")

        s("Logging support-bot actions...")
        store.log_event(
            agent_id="support-bot",
            action_type="ticket_received",
            raw_action="INCOMING: ticket#78234 from customer@example.com",
            human_summary="Received support ticket from customer #4521",
            metadata={"ticket_id": "78234", "priority": "high"},
        )
        store.log_event(
            agent_id="support-bot",
            action_type="api_call",
            raw_action="SELECT * FROM customers WHERE id = 4521",
            human_summary="Queried CRM for customer #4521 history",
            duration_ms=45,
        )
        store.log_event(
            agent_id="support-bot",
            action_type="llm_call",
            raw_action="openai.chat.completions.create(model='gpt-4', ...)",
            human_summary="Generated personalized response using GPT-4",
            tokens_used=285,
            cost_usd=0.008,
            duration_ms=1800,
        )
        store.log_event(
            agent_id="support-bot",
            action_type="email_sent",
            raw_action="POST /api/send-email",
            human_summary="Sent follow-up email to customer #4521",
            duration_ms=150,
        )
        store.log_event(
            agent_id="support-bot",
            action_type="error",
            raw_action="ESCALATE: confidence=0.32 < threshold=0.50",
            human_summary="Escalated ticket #892 to human agent — confidence too low",
            risk_score="high",
            duration_ms=12,
        )
        ok("5 events logged for support-bot")

        # =================================================================
        print_section("PART 2: View All Agents")
        # =================================================================

        agents = store.get_agents()
        s(f"Found {len(agents)} agents:\n")

        for agent in agents:
            status_icon = "🟢" if agent["status"] == "active" else "🔴"
            print(f"  {status_icon} {agent['name']} ({agent['id']})")
            print(f"      Framework: {agent.get('framework', 'N/A')}  |  Status: {agent['status']}")

        # =================================================================
        print_section("PART 3: Event Timeline & Statistics")
        # =================================================================

        for agent in agents:
            agent_id = agent["id"]
            stats = store.get_agent_stats(agent_id)

            print_section(f"{agent['name']} — Stats", level=2)

            events_count = stats.get("total_events", 0)
            tokens = stats.get("total_tokens", 0) or 0
            cost = stats.get("total_cost", 0.0) or 0.0
            avg_dur = stats.get("avg_duration_ms")

            print(f"  Events: {events_count}  |  Tokens: {tokens}  |  Cost: ${cost:.4f}", end="")
            if avg_dur:
                print(f"  |  Avg: {avg_dur:.0f}ms")
            else:
                print()

            # Show recent events
            events = store.get_events(agent_id=agent_id, limit=5)
            print("\n  Timeline:")
            for evt in events:
                summary = evt.get("human_summary") or evt.get("action_type")
                action = evt.get("action_type", "unknown")
                risk = evt.get("risk_score", "low")
                risk_dot = "🟢" if risk == "low" else ("🟡" if risk == "medium" else "🔴")
                print(f"    {risk_dot} [{action:15}] {summary}")

        # =================================================================
        print_section("PART 4: @monitor Decorator Demo")
        # =================================================================
        # The decorator automatically logs when a function is called.

        s("Defining a monitored function...")

        @monitor(agent_name="decorator-demo", db_path=temp_db)
        def process_lead(name: str):
            """Simulated agent function — the decorator logs it automatically."""
            time.sleep(0.1)  # simulate work
            return f"Processed {name}"

        s("Calling process_lead('Acme Corp')...")
        result = process_lead("Acme Corp")
        ok(f"Result: {result}")
        ok("Event was automatically logged — no manual code needed!")

        # =================================================================
        print_section("PART 5: Context Manager Demo")
        # =================================================================
        # The context manager lets you log multiple actions within a block.

        s("Running agent with context manager...\n")

        with monitor(agent_name="context-demo", db_path=temp_db) as m:
            s("  Step 1: Querying database...")
            m.log("api_call", "SELECT * FROM orders", "Queried order database")

            s("  Step 2: Generating report...")
            m.log("llm_call", "openai.chat.create(...)", "Generated weekly report",
                  tokens_used=450, cost_usd=0.013)

            s("  Step 3: Sending notification...")
            m.log("email_sent", "POST /notify", "Sent report to team@company.com")

        ok("Context manager auto-logged session start/end + 3 manual actions")

        # =================================================================
        print_section("PART 6: Kill Switch (Pause/Resume)")
        # =================================================================
        # Pause an agent immediately — all calls will be blocked.

        s("Current sales-bot status...")
        agent = store.get_agent("sales-bot")
        data("Status", agent["status"])

        s("Pausing sales-bot...")
        store.pause_agent("sales-bot")
        ok("sales-bot PAUSED")

        s("Attempting to run paused decorator-demo agent...")
        # The decorator checks the kill switch before running
        store.pause_agent("decorator-demo")
        try:
            process_lead("Should Fail")
            print("  [!] This should not happen!")
        except RuntimeError as e:
            ok(f"BLOCKED: {str(e)[:65]}...")

        s("Resuming both agents...")
        store.resume_agent("sales-bot")
        store.resume_agent("decorator-demo")
        ok("Agents resumed")

        # =================================================================
        print_section("PART 7: Audit Chain Verification")
        # =================================================================
        # Every event is linked to the previous one with HMAC-SHA256.
        # If anyone tampers with the database, verification will fail.

        s("Verifying HMAC-SHA256 audit chain...")
        is_valid = store.verify_chain()
        if is_valid:
            ok("Chain VALID — no tampering detected")
        else:
            print("  [!] Chain BROKEN — tampering detected!")

        s("Simulating tampering (modifying an event in the chain)...")
        # The chain hash covers: event_id, agent_id, action_type, timestamp.
        # Changing any of these fields will break the chain.
        row = store.conn.execute(
            "SELECT id FROM events WHERE agent_id = 'support-bot' ORDER BY timestamp LIMIT 1"
        ).fetchone()
        store.conn.execute(
            "UPDATE events SET action_type = 'TAMPERED' WHERE id = ?", (row["id"],)
        )
        store.conn.commit()

        s("Re-verifying chain after tampering...")
        is_valid = store.verify_chain()
        if is_valid:
            print("  [!] Chain passed (unexpected)")
        else:
            ok("Chain BROKEN — tampering correctly detected!")

        s("(Restoring database for clean exit...)")

        # =================================================================
        print_section("PART 8: Summary")
        # =================================================================

        total_events = sum(
            store.get_agent_stats(a["id"]).get("total_events", 0)
            for a in agents
        )
        total_tokens = sum(
            (store.get_agent_stats(a["id"]).get("total_tokens", 0) or 0)
            for a in agents
        )
        total_cost = sum(
            (store.get_agent_stats(a["id"]).get("total_cost", 0.0) or 0.0)
            for a in agents
        )

        print(f"""
  Agents monitored:    {len(agents)}
  Events logged:       {total_events}
  Total tokens:        {total_tokens}
  Total cost:          ${total_cost:.4f}
  Database:            {temp_db}

  All data stored locally. No cloud. No API keys. No telemetry sent.
""")

        print("=" * 80)
        print("  Demo complete! Learn more at https://github.com/airblackbox/air-controls")
        print("=" * 80 + "\n")

        store.close()

    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    # Clean up the temp database
    try:
        Path(temp_db).unlink()
        print(f"  Cleaned up temp database: {temp_db}")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
