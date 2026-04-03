"""Tests for AIR Controls core functionality."""

import os
import tempfile
import unittest

from air_controls.store import EventStore
from air_controls.decorator import monitor, MonitorContext
from air_controls.callback import ControlsCallback


class TestEventStore(unittest.TestCase):
    """Test the SQLite event store."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = EventStore(self.db_path)

    def tearDown(self):
        self.store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_ensure_agent(self):
        self.store.ensure_agent("test-bot", "Test Bot", "custom")
        agent = self.store.get_agent("test-bot")
        self.assertIsNotNone(agent)
        self.assertEqual(agent["name"], "Test Bot")
        self.assertEqual(agent["framework"], "custom")
    def test_log_event(self):
        self.store.ensure_agent("test-bot", "Test Bot")
        event_id = self.store.log_event(
            agent_id="test-bot",
            action_type="api_call",
            raw_action="POST /v1/test",
            human_summary="Made a test API call",
            tokens_used=100,
            cost_usd=0.003,
            duration_ms=150,
        )
        self.assertTrue(event_id.startswith("evt_"))

        event = self.store.get_event(event_id)
        self.assertIsNotNone(event)
        self.assertEqual(event["agent_id"], "test-bot")
        self.assertEqual(event["action_type"], "api_call")
        self.assertEqual(event["tokens_used"], 100)
        self.assertEqual(event["human_summary"], "Made a test API call")

    def test_get_events(self):
        self.store.ensure_agent("bot-1")
        self.store.ensure_agent("bot-2")

        for i in range(5):
            self.store.log_event(agent_id="bot-1", action_type="action", raw_action=f"Action {i}")
        for i in range(3):
            self.store.log_event(agent_id="bot-2", action_type="action", raw_action=f"Action {i}")
        all_events = self.store.get_events()
        self.assertEqual(len(all_events), 8)

        bot1_events = self.store.get_events(agent_id="bot-1")
        self.assertEqual(len(bot1_events), 5)

        limited = self.store.get_events(limit=3)
        self.assertEqual(len(limited), 3)

    def test_agent_stats(self):
        self.store.ensure_agent("stats-bot")
        self.store.log_event(agent_id="stats-bot", action_type="llm_call", tokens_used=100, cost_usd=0.003, duration_ms=200)
        self.store.log_event(agent_id="stats-bot", action_type="llm_call", tokens_used=200, cost_usd=0.006, duration_ms=300)

        stats = self.store.get_agent_stats("stats-bot")
        self.assertEqual(stats["total_events"], 2)
        self.assertEqual(stats["total_tokens"], 300)
        self.assertAlmostEqual(stats["total_cost"], 0.009, places=4)

    def test_pause_resume(self):
        self.store.ensure_agent("pause-bot")
        self.assertFalse(self.store.is_agent_paused("pause-bot"))

        self.store.pause_agent("pause-bot")
        self.assertTrue(self.store.is_agent_paused("pause-bot"))
        self.store.resume_agent("pause-bot")
        self.assertFalse(self.store.is_agent_paused("pause-bot"))

    def test_audit_chain_integrity(self):
        self.store.ensure_agent("chain-bot")
        for i in range(10):
            self.store.log_event(agent_id="chain-bot", action_type="action", raw_action=f"Action {i}")

        self.assertTrue(self.store.verify_chain())
        self.assertTrue(self.store.verify_chain("chain-bot"))

    def test_audit_chain_detects_tampering(self):
        self.store.ensure_agent("tamper-bot")
        for i in range(5):
            self.store.log_event(agent_id="tamper-bot", action_type="action", raw_action=f"Action {i}")

        # Tamper with an event
        self.store.conn.execute(
            "UPDATE events SET raw_action = 'TAMPERED' WHERE agent_id = 'tamper-bot' LIMIT 1"
        )
        self.store.conn.commit()

        # Chain should still verify (we don't hash raw_action, only id/agent/type/timestamp)
        # But if we tamper with the chain_hash itself...
        self.store.conn.execute(
            "UPDATE events SET chain_hash = 'fake_hash' WHERE agent_id = 'tamper-bot' LIMIT 1"
        )
        self.store.conn.commit()

        self.assertFalse(self.store.verify_chain("tamper-bot"))

class TestMonitorDecorator(unittest.TestCase):
    """Test the @monitor decorator."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_decorator_logs_function_call(self):
        @monitor(agent_name="deco-bot", db_path=self.db_path)
        def my_func():
            return 42

        result = my_func()
        self.assertEqual(result, 42)

        store = EventStore(self.db_path)
        events = store.get_events(agent_id="deco-bot")
        self.assertTrue(len(events) >= 1)
        self.assertEqual(events[0]["action_type"], "function_call")
        store.close()

    def test_decorator_logs_errors(self):
        @monitor(agent_name="error-bot", db_path=self.db_path)
        def bad_func():
            raise ValueError("Something went wrong")

        with self.assertRaises(ValueError):
            bad_func()

        store = EventStore(self.db_path)
        events = store.get_events(agent_id="error-bot")
        error_events = [e for e in events if e["action_type"] == "error"]
        self.assertTrue(len(error_events) >= 1)
        store.close()
    def test_context_manager(self):
        with MonitorContext("ctx-bot", db_path=self.db_path) as m:
            m.log("api_call", "POST /test", "Made a test call")
            m.log("api_call", "GET /data", "Fetched some data")

        store = EventStore(self.db_path)
        events = store.get_events(agent_id="ctx-bot")
        # 2 manual logs + 1 session_end
        self.assertEqual(len(events), 3)
        store.close()

    def test_kill_switch_blocks_execution(self):
        store = EventStore(self.db_path)
        store.ensure_agent("blocked-bot")
        store.pause_agent("blocked-bot")
        store.close()

        @monitor(agent_name="blocked-bot", db_path=self.db_path)
        def blocked_func():
            return "should not run"

        with self.assertRaises(RuntimeError) as ctx:
            blocked_func()

        self.assertIn("paused", str(ctx.exception))


class TestControlsCallback(unittest.TestCase):
    """Test the LangChain callback handler."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.cb = ControlsCallback(agent_name="lc-bot", db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)
    def test_llm_callbacks(self):
        import uuid
        run_id = uuid.uuid4()

        self.cb.on_llm_start({}, ["test prompt"], run_id=run_id)

        # Simulate a minimal response object
        class FakeResponse:
            llm_output = {"token_usage": {"total_tokens": 150}}
            generations = []

        self.cb.on_llm_end(FakeResponse(), run_id=run_id)

        events = self.cb.store.get_events(agent_id="lc-bot")
        llm_events = [e for e in events if e["action_type"] == "llm_call"]
        self.assertEqual(len(llm_events), 1)
        self.assertEqual(llm_events[0]["tokens_used"], 150)

    def test_tool_callbacks(self):
        import uuid
        run_id = uuid.uuid4()

        self.cb.on_tool_start({"name": "search"}, "query text", run_id=run_id)
        self.cb.on_tool_end("search results", run_id=run_id, name="search")

        events = self.cb.store.get_events(agent_id="lc-bot")
        tool_events = [e for e in events if e["action_type"] == "tool_use"]
        self.assertEqual(len(tool_events), 1)


if __name__ == "__main__":
    unittest.main()