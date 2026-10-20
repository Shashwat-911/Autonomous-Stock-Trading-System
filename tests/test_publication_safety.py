import ast
import base64
from datetime import datetime, timezone
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


def pipeline():
    path = Path(__file__).resolve().parents[1]/"scripts/post_session.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    ns = dict(os=os, datetime=datetime, timezone=timezone, DRY_RUN=False,
              subprocess=Mock(), sys=Mock())
    exec(compile(tree, str(path), "exec"), ns)
    return ns


class PublicationSafetyTests(unittest.TestCase):
    def test_failed_artifact_generation_never_invokes_git(self):
        for sequence in ([True, False], [True, True, False], [True, True, True, False]):
            ns = pipeline()
            ns["run_python"] = Mock(side_effect=sequence)
            ns["run"] = Mock()
            ns["banner"] = Mock()
            with patch("builtins.print"):
                self.assertFalse(ns["run_post_session_pipeline"]())
            ns["run"].assert_not_called()
            ns["subprocess"].run.assert_not_called()

    def test_token_only_enters_child_environment_not_git_configuration(self):
        ns = pipeline()
        with patch.dict(os.environ, {"GIT_TOKEN":"test-only-token", "GIT_CONFIG_COUNT":"1"}):
            env = ns["git_environment"]()
            self.assertEqual(os.environ["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(env["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(env["GIT_CONFIG_KEY_1"], "http.https://github.com/.extraheader")
        self.assertEqual(base64.b64decode(env["GIT_CONFIG_VALUE_1"].split()[-1]), b"x-access-token:test-only-token")
        ns["subprocess"].run.assert_not_called()
