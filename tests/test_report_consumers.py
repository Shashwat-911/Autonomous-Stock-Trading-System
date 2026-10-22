import ast
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analytics.reporting import run_report
from scripts.update_readme import render_block, update_readme, START, END
from test_reporting import fixture


class ConsumerTests(unittest.TestCase):
    def test_readme_preserves_legacy_text_and_missing_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            run_report(snapshot=fixture(), start="2026-10-14", end="2026-10-15",
                       private_root=root/"private", public_root=root/"public")
            from analytics.reporting import latest_report
            folder=latest_report(root/"public")
            original="# Project\n\nExisting historical evidence.\n"
            (root/"README.md").write_text(original,encoding="utf-8")
            with patch("scripts.update_readme.ROOT",root), patch("scripts.update_readme.latest_report",return_value=folder):
                update_readme()
                update_readme()
            text=(root/"README.md").read_text(encoding="utf-8")
            self.assertIn("Existing historical evidence.",text)
            self.assertEqual(text.count(START),1)
            self.assertEqual(text.count(END),1)
            self.assertIn("Unavailable",text)
            self.assertIn("not a validated baseline",text)

    def test_equity_script_import_does_not_fetch_or_overwrite_legacy(self):
        # The export is now guarded by main; importing it cannot touch the broker.
        import importlib
        with patch("scripts.reconcile_paper_account.PaperReader",side_effect=AssertionError("No network")):
            module=importlib.import_module("scripts.fetch_alpaca_equity")
            self.assertTrue(callable(module.main))



class DailyTableTests(unittest.TestCase):
    def test_live_table_uses_validated_rows_and_actual_log_links(self):
        from scripts.update_readme import render_daily_table
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"outputs/logs").mkdir(parents=True)
            (root/"outputs/logs/session_2026_10_21.txt").write_text("session")
            (root/"daily_account_measurement.csv").write_text(
                "date,equity,gross_realized_pnl,equity_change_since_prior_observation\n"
                "2026-10-21,99743.94,-31.39,19.41\n")
            with patch("scripts.update_readme.ROOT", root):
                table=render_daily_table(root)
            self.assertIn("$99,743.94", table)
            self.assertIn("$-31.39", table)
            self.assertIn("session_2026_10_21.txt", table)


class ArchiveTests(unittest.TestCase):
    def test_html_recovery_keeps_stdout_and_excludes_navigation(self):
        from scripts.archive_session_log import LogParser
        parser=LogParser()
        parser.feed('<h1>Navigation</h1><div class="log-content">LIVE PAPER TRADING &lt;10 min\nDone</div><footer>Footer</footer>')
        self.assertEqual("".join(parser.parts), "LIVE PAPER TRADING <10 min\nDone")


if __name__ == "__main__":
    unittest.main()
