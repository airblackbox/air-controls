"""
SQLite event storage for AIR Controls.

Stores every agent action as a structured event with HMAC-SHA256 audit chain.
Local-first: your agent telemetry never leaves your machine.
"""

import hashlib
import hmac
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# Default DB location
DEFAULT_DB_PATH = os.environ.get(
    "AIR_CONTROLS_DB",
    str(Path.home() / ".air-controls" / "events.db"),
)

# HMAC key — in production this would be configurable
HMAC_KEY = os.environ.get("AIR_CONTROLS_HMAC_KEY", "air-controls-default-key").encode()

def _generate_id() -> str:
    """Generate a short unique event ID."""
    return f"evt_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    """Current time as ISO 8601 UTC string."""
    return datetime.now(timezone.utc).isoformat()


def _compute_chain_hash(previous_hash: str, event_data: str) -> str:
    """Compute HMAC-SHA256 chain hash for tamper-evident audit trail."""
    message = f"{previous_hash}:{event_data}".encode()
    return hmac.new(HMAC_KEY, message, hashlib.sha256).hexdigest()


class EventStore:
    """
    SQLite-backed event store for agent actions.

    Usage:
        store = EventStore()  # uses default path ~/.air-controls/events.db
        store = EventStore("/path/to/custom.db")

        store.log_event(
            agent_id="sales-bot",
            action_type="api_call",
            raw_action="POST /v1/contacts/update",
            human_summary="Updated customer email",
        )

        events = store.get_events("sales-bot", limit=20)
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH

        # Create parent directory if needed
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._last_hash = self._get_last_hash()

    def _create_tables(self):
        """Create tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                framework       TEXT,
                status          TEXT DEFAULT 'active',
                created_at      TEXT,
                config          TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS events (
                id              TEXT PRIMARY KEY,
                agent_id        TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                action_type     TEXT NOT NULL,
                raw_action      TEXT,
                human_summary   TEXT,
                input_data      TEXT,
                output_data     TEXT,
                tokens_used     INTEGER DEFAULT 0,
                cost_usd        REAL DEFAULT 0.0,
                duration_ms     INTEGER DEFAULT 0,
                risk_score      TEXT DEFAULT 'low',
                trigger_event_id TEXT,
                chain_hash      TEXT,
                metadata        TEXT DEFAULT '{}',
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_events_agent
                ON events(agent_id, timestamp DESC);

            CREATE INDEX IF NOT EXISTS idx_events_type
                ON events(action_type);

            CREATE TABLE IF NOT EXISTS alerts (
                id              TEXT PRIMARY KEY,
                agent_id        TEXT NOT NULL,
                alert_type      TEXT NOT NULL,
                severity        TEXT NOT NULL,
                message         TEXT NOT NULL,
                event_id        TEXT,
                acknowledged    INTEGER DEFAULT 0,
                created_at      TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS baselines (
                agent_id        TEXT NOT NULL,
                metric          TEXT NOT NULL,
                avg_7d          REAL DEFAULT 0.0,
                stddev_7d       REAL DEFAULT 0.0,
                updated_at      TEXT,
                PRIMARY KEY (agent_id, metric)
            );

            CREATE TABLE IF NOT EXISTS guardrails (
                id              TEXT PRIMARY KEY,
                agent_id        TEXT NOT NULL,
                rule_type       TEXT NOT NULL,
                config          TEXT NOT NULL,
                enabled         INTEGER DEFAULT 1,
                created_at      TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );
        """)
        self.conn.commit()

    def _get_last_hash(self) -> str:
        """Get the last chain hash for continuity."""
        row = self.conn.execute(
            "SELECT chain_hash FROM events ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return row["chain_hash"] if row else "genesis"

    def ensure_agent(self, agent_id: str, name: Optional[str] = None,
                     framework: Optional[str] = None):
        """Register an agent if it doesn't exist yet."""
        existing = self.conn.execute(
            "SELECT id FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if not existing:
            self.conn.execute(
                "INSERT INTO agents (id, name, framework, created_at) VALUES (?, ?, ?, ?)",
                (agent_id, name or agent_id, framework, _now_iso()),
            )
            self.conn.commit()

    def log_event(
        self,
        agent_id: str,
        action_type: str,
        raw_action: str = "",
        human_summary: str = "",
        input_data: Any = None,
        output_data: Any = None,
        tokens_used: int = 0,
        cost_usd: float = 0.0,
        duration_ms: int = 0,
        risk_score: str = "low",
        trigger_event_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Log an agent action event.

        Returns the event ID.
        """
        event_id = _generate_id()
        timestamp = _now_iso()

        # Build chain hash
        event_data = f"{event_id}:{agent_id}:{action_type}:{timestamp}"
        chain_hash = _compute_chain_hash(self._last_hash, event_data)
        self._last_hash = chain_hash

        self.conn.execute(
            """INSERT INTO events
               (id, agent_id, timestamp, action_type, raw_action, human_summary,
                input_data, output_data, tokens_used, cost_usd, duration_ms,
                risk_score, trigger_event_id, chain_hash, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, agent_id, timestamp, action_type,
                raw_action, human_summary,
                json.dumps(input_data) if input_data else None,
                json.dumps(output_data) if output_data else None,
                tokens_used, cost_usd, duration_ms,
                risk_score, trigger_event_id, chain_hash,
                json.dumps(metadata or {}),
            ),
        )
        self.conn.commit()
        return event_id

    def get_events(
        self,
        agent_id: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Get events, optionally filtered by agent and/or action type."""
        query = "SELECT * FROM events WHERE 1=1"
        params: list = []

        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if action_type:
            query += " AND action_type = ?"
            params.append(action_type)
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_event(self, event_id: str) -> Optional[Dict]:
        """Get a single event by ID."""
        row = self.conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_agents(self) -> List[Dict]:
        """Get all registered agents."""
        rows = self.conn.execute(
            "SELECT * FROM agents ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """Get a single agent by ID."""
        row = self.conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_agent_stats(self, agent_id: str) -> Dict:
        """Get summary stats for an agent."""
        row = self.conn.execute(
            """SELECT
                COUNT(*) as total_events,
                SUM(tokens_used) as total_tokens,
                SUM(cost_usd) as total_cost,
                AVG(duration_ms) as avg_duration_ms,
                MIN(timestamp) as first_event,
                MAX(timestamp) as last_event
               FROM events WHERE agent_id = ?""",
            (agent_id,),
        ).fetchone()
        return dict(row) if row else {}

    def pause_agent(self, agent_id: str):
        """Pause an agent (kill switch)."""
        self.conn.execute(
            "UPDATE agents SET status = 'paused' WHERE id = ?", (agent_id,)
        )
        self.conn.commit()

    def resume_agent(self, agent_id: str):
        """Resume a paused agent."""
        self.conn.execute(
            "UPDATE agents SET status = 'active' WHERE id = ?", (agent_id,)
        )
        self.conn.commit()

    def is_agent_paused(self, agent_id: str) -> bool:
        """Check if an agent is paused."""
        row = self.conn.execute(
            "SELECT status FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        return row["status"] == "paused" if row else False

    def verify_chain(self, agent_id: Optional[str] = None) -> bool:
        """Verify the HMAC-SHA256 audit chain integrity."""
        query = "SELECT * FROM events"
        params: list = []
        if agent_id:
            query += " WHERE agent_id = ?"
            params.append(agent_id)
        query += " ORDER BY timestamp ASC"

        rows = self.conn.execute(query, params).fetchall()

        previous_hash = "genesis"
        for row in rows:
            event_data = f"{row['id']}:{row['agent_id']}:{row['action_type']}:{row['timestamp']}"
            expected = _compute_chain_hash(previous_hash, event_data)
            if expected != row["chain_hash"]:
                return False
            previous_hash = row["chain_hash"]

        return True

    def close(self):
        """Close the database connection."""
        self.conn.close()
