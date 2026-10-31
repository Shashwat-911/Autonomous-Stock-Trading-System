import ast
from pathlib import Path
import unittest
import pandas as pd


def labels_function():
    tree = ast.parse(Path('ml/data_pipeline.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate_labels')
    ns = {'pd': pd}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'labels', 'exec'), ns)
    return ns['generate_labels']


class ResearchValidationTests(unittest.TestCase):
    def test_ambiguous_bar_is_loss_and_incomplete_horizon_excluded(self):
        bars = pd.DataFrame({'Close': [100]*4, 'High': [100, 103, 100, 100], 'Low': [100, 97, 100, 100]})
        result = labels_function()(bars, forward_bars=2)
        self.assertEqual(result.iloc[0], 0)
        self.assertTrue(result.iloc[-2:].isna().all())

    def test_last_bar_of_full_horizon_is_included(self):
        bars = pd.DataFrame({'Close': [100]*4, 'High': [100, 100, 103, 100], 'Low': [100]*4})
        self.assertEqual(labels_function()(bars, forward_bars=2).iloc[0], 1)
