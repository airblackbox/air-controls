"""
CLI for AIR Controls.

Usage:
    air-controls status              Show all agents and recent activity
    air-controls events [agent_id]   Show event timeline
    air-controls agents              List all monitored agents
    air-controls stats <agent_id>    Show agent statistics
    air-controls pause <agent_id>    Pause an agent (kill switch)
    air-controls resume <agent_id>   Resume a paused agent
    air-controls verify [agent_id]   Verify audit chain integrity
"""

import argparse
import json
import sys
from datetime import datetime

from air_controls.store import EventStore


def _truncate(s: str, length: int = 60) -> str:
    """Truncate a string with ellipsis."""
    if not s:
        return ""
    return s[:length] + "..." if len(s) > length else s


def _format_time(iso_str: str) -> str:
    """Format ISO timestamp to readable local time."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso_str or ""


def _risk_icon(risk: str) -> str:
    """Get a risk indicator."""
    return {
        "low": "  ",
        "medium": "! ",
        "high": "!!",
        "critical": "XX",
    }.get(risk or "low", "  ")


def cmd_status(store: EventStore, args):
    """Show overview of all agents and recent activity."""
    agents = store.get_agents()

    if not agents:
        print("No agents registered yet.")
        print("")
        print("Get started:")
        print("  from air_controls import ControlsCallback")
    print('  cb = ControlsCallback(agent_name="my-bot")')
        return

    print("=" * 70)
    print("  AIR Controls — Agent Status")
    print("=" * 70)
    print("")

    for agent in agents:
        status_icon = "■ PAUSED" if agent["status"] == "paused" else "● active"
        stats = store.get_agent_stats(agent["id"])

        print(f"  {agent['name']}")
        print(f"  ID: {agent['id']}  |  Framework: {agent.get('framework', '-')}  |  {status_icon}")

        if stats.get("total_events"):
            cost = stats.get("total_cost", 0) or 0
            print(f"  Events: {stats['total_events']}  |  Tokens: {stats.get('total_tokens', 0) or 0}  |  Cost: ${cost:.4f}")
            print(f"  Last activity: {_format_time(stats.get('last_event', ''))}")
        else:
            print("  No events recorded yet")
        print("")

    # Show last 5 events across all agents
    recent = store.get_events(limit=5)
    if recent:
        print("-" * 70)
        print("  Recent Activity")
        print("-" * 70)
        for evt in recent:
            risk = _risk_icon(evt.get("risk_score", "low"))
            time_str = _format_time(evt["timestamp"])
            summary = evt.get("human_summary") or evt.get("raw_action") or evt["action_type"]
            print(f"  {risk} [{time_str}] {evt['agent_id']}: {_truncate(summary)}")
        print("")

    # Chain integrity
    is_valid = store.verify_chain()
    chain_status = "VALID" if is_valid else "BROKEN — possible tampering detected"
    print(f"  Audit chain: {chain_status}")
    print("=" * 70)


def cmd_events(store: EventStore, args):
    """Show event timeline for an agent."""
    events = store.get_events(agent_id=args.agent_id, limit=args.limit)

    if not events:
        if args.agent_id:
            print(f"No events found for agent '{args.agent_id}'")
        else:
            print("No events recorded yet.")
        return

    title = f"Events for '{args.agent_id}'" if args.agent_id else "All Events"
    print(f"\n  {title} (last {len(events)})")
    print("-" * 70)

    for evt in events:
        risk = _risk_icon(evt.get("risk_score", "low"))
        time_str = _format_time(evt["timestamp"])
        summary = evt.get("human_summary") or evt.get("raw_action") or ""
        cost = evt.get("cost_usd", 0) or 0
        duration = evt.get("duration_ms", 0) or 0

        print(f"  {risk} [{time_str}] {evt['action_type']}")
        print(f"     {_truncate(summary, 55)}")
        if cost > 0 or duration > 0:
            extras = []
            if duration > 0:
                extras.append(f"{duration}ms")
            if cost > 0:
                extras.append(f"${cost:.4f}")
            if evt.get("tokens_used"):
                extras.append(f"{evt['tokens_used']} tokens")
            print(f"     {' · '.join(extras)}")
        print("")


def cmd_agents(store: EventStore, args):
    """List all registered agents."""
    agents = store.get_agents()

    if not agents:
        print("No agents registered yet.")
        return

    print(f"\n  Registered Agents ({len(agents)})")
    print("-" * 70)

    for agent in agents:
        status = "PAUSED" if agent["status"] == "paused" else "active"
        print(f"  {agent['id']:25s}  {agent.get('framework', '-'):12s}  {status}")


def cmd_stats(store: EventStore, args):
    """Show detailed stats for an agent."""
    agent = store.get_agent(args.agent_id)
    if not agent:
        print(f"Agent '{args.agent_id}' not found.")
        return

    stats = store.get_agent_stats(args.agent_id)

    print(f"\n  Stats for '{agent['name']}'")
    print("=" * 50)
    print(f"  Framework:       {agent.get('framework', '-')}")
    print(f"  Status:          {agent['status']}")
    print(f"  Total events:    {stats.get('total_events', 0)}")
    print(f"  Total tokens:    {stats.get('total_tokens', 0) or 0}")
    print(f"  Total cost:      ${(stats.get('total_cost', 0) or 0):.4f}")
    print(f"  Avg duration:    {(stats.get('avg_duration_ms', 0) or 0):.0f}ms")
    print(f"  First event:     {_format_time(stats.get('first_event', ''))}")
    print(f"  Last event:      {_format_time(stats.get('last_event', ''))}")
    print("=" * 50)


def cmd_pause(store: EventStore, args):
    """Pause an agent (kill switch)."""
    agent = store.get_agent(args.agent_id)
    if not agent:
        print(f"Agent '{args.agent_id}' not found.")
        return

    store.pause_agent(args.agent_id)
    store.log_event(
        agent_id=args.agent_id,
        action_type="kill_switch",
        raw_action="Agent paused via CLI",
        human_summary=f"Agent '{args.agent_id}' paused by operator",
        risk_score="medium",
    )
    print(f"Agent '{args.agent_id}' is now PAUSED.")
    print(f"Resume with: air-controls resume {args.agent_id}")


def cmd_resume(store: EventStore, args):
    """Resume a paused agent."""
    agent = store.get_agent(args.agent_id)
    if not agent:
        print(f"Agent '{args.agent_id}' not found.")
        return

    store.resume_agent(args.agent_id)
    store.log_event(
        agent_id=args.agent_id,
        action_type="resumed",
        raw_action="Agent resumed via CLI",
        human_summary=f"Agent '{args.agent_id}' resumed by operator",
    )
    print(f"Agent '{args.agent_id}' is now ACTIVE.")


def cmd_verify(store: EventStore, args):
    """Verify audit chain integrity."""
    is_valid = store.verify_chain(args.agent_id)
    scope = f"agent '{args.agent_id}'" if args.agent_id else "all agents"

    if is_valid:
        print(f"Audit chain for {scope}: VALID")
        print("All events are tamper-evident and intact.")
    else:
        print(f"Audit chain for {scope}: BROKEN")
        print("WARNING: Chain integrity compromised. Events may have been tampered with.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="air-controls",
        description="AIR Controls — See what your AI agents actually do",
    )
    parser.add_argument("--db", default=None, help="Path to SQLite database")

    subparsers = parser.add_subparsers(dest="command")

    # status
    subparsers.add_parser("status", help="Show all agents and recent activity")

    # events
    p_events = subparsers.add_parser("events", help="Show event timeline")
    p_events.add_argument("agent_id", nargs="?", default=None, help="Filter by agent ID")
    p_events.add_argument("-n", "--limit", type=int, default=20, help="Number of events")

    # agents
    subparsers.add_parser("agents", help="List all monitored agents")

    # stats
    p_stats = subparsers.add_parser("stats", help="Show agent statistics")
    p_stats.add_argument("agent_id", help="Agent ID")

    # pause
    p_pause = subparsers.add_parser("pause", help="Pause an agent (kill switch)")
    p_pause.add_argument("agent_id", help="Agent ID")

    # resume
    p_resume = subparsers.add_parser("resume", help="Resume a paused agent")
    p_resume.add_argument("agent_id", help="Agent ID")

    # verify
    p_verify = subparsers.add_parser("verify", help="Verify audit chain integrity")
    p_verify.add_argument("agent_id", nargs="?", default=None, help="Agent ID (optional)")

    args = parser.parse_args()

    if not args.command:
        # Default to status
        args.command = "status"

    store = EventStore(args.db)

    commands = {
        "status": cmd_status,
        "events": cmd_events,
        "agents": cmd_agents,
        "stats": cmd_stats,
        "pause": cmd_pause,
        "resume": cmd_resume,
        "verify": cmd_verify,
    }

    commands[args.command](store, args)
    store.close()


if __name__ == "__main__":
    main()
