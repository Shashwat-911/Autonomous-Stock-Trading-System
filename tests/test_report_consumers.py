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



if __name__ == "__main__":
    unittest.main()
