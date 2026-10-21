from datetime import datetime
import unittest
from scripts.session_timing import assess_session


class TimingTests(unittest.TestCase):
    def phase(self, now, day, opening="09:30", closing="16:00"):
        return assess_session(datetime.fromisoformat(now), [{"date":day,"open":opening,"close":closing}])["status"]

    def test_dst_opening_and_cutoff(self):
        self.assertEqual(self.phase("2026-10-21T13:29:00+00:00","2026-10-21"),"PREOPEN")
        self.assertEqual(self.phase("2026-10-21T13:30:00+00:00","2026-10-21"),"READY")
        self.assertEqual(self.phase("2026-10-21T18:04:00+00:00","2026-10-21"),"LATE_START")
        self.assertEqual(self.phase("2026-11-02T13:30:00+00:00","2026-11-02"),"PREOPEN")
        self.assertEqual(self.phase("2026-11-02T14:30:00+00:00","2026-11-02"),"READY")

    def test_early_close_holiday_and_naive_timestamp(self):
        self.assertEqual(self.phase("2026-11-27T18:00:00+00:00","2026-11-27",closing="13:00"),"CLOSED")
        self.assertEqual(assess_session(datetime.fromisoformat("2026-12-25T15:00:00+00:00"),[])["status"],"NON_TRADING_DAY")
        with self.assertRaises(ValueError):
            assess_session(datetime(2026,10,21),[])

    def test_entry_gate_uses_actual_broker_close(self):
        import ast
        from pathlib import Path
        from types import SimpleNamespace
        tree = ast.parse((Path(__file__).resolve().parents[1]/"main.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_should_allow_new_entries")
        ns = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "entry-gate", "exec"), ns)
        gate = ns[fn.name]
        self.assertFalse(gate())
        for now, close, expected in [("2026-11-02T18:00:00+00:00", "2026-11-02T21:00:00+00:00", True),
                                     ("2026-11-27T16:00:00+00:00", "2026-11-27T18:00:00+00:00", False)]:
            clock = SimpleNamespace(is_open=True, timestamp=datetime.fromisoformat(now), next_close=datetime.fromisoformat(close))
            self.assertEqual(gate(clock=clock), expected)
            clock.is_open = False
            self.assertFalse(gate(clock=clock))

    def test_runner_status_checks_process_not_log_presence(self):
        import ast
        from pathlib import Path
        from datetime import timezone
        from unittest.mock import Mock
        tree = ast.parse((Path(__file__).resolve().parents[1]/"scripts/cloud_launcher.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "runner_status")
        ns = dict(RUNNER={"revision":"test"}, WORKER=None, datetime=datetime, timezone=timezone)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "runner-status", "exec"), ns)
        self.assertFalse(ns[fn.name]()["worker_running"])
        ns["WORKER"] = Mock()
        ns["WORKER"].poll.return_value = None
        self.assertTrue(ns[fn.name]()["worker_running"])
        ns["WORKER"].poll.return_value = 1
        self.assertFalse(ns[fn.name]()["worker_running"])

    def test_external_probe_rejects_generic_health_and_missing_worker(self):
        from scripts.check_cloud_status import validate_status
        from datetime import timezone
        now = datetime.now(timezone.utc)
        for state in ({"status":"healthy"}, {"revision":"abc", "phase":"UNKNOWN"},
                      {"revision":"abc", "phase":"LATE_START", "worker_running":False}):
            with self.assertRaises(ValueError):
                validate_status(state, now)
        validate_status({"revision":"abc", "phase":"PREOPEN"}, now)
        validate_status({"revision":"abc", "phase":"TRADING", "worker_running":True,
                         "last_worker_output":now.isoformat()}, now)
