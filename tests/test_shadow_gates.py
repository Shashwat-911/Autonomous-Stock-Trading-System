import tempfile
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from pathlib import Path
from research.gates import evaluate
from research.shadow import advance

class EvaluationTests(unittest.TestCase):
    def test_missing_evidence_never_passes(self):
        self.assertFalse(evaluate({})['eligible_for_review'])
        self.assertFalse(evaluate({})['automatic_deployment'])
    def test_future_holdout_cannot_be_claimed(self):
        result=evaluate({'complete_prospective_holdout':True},'2026-11-02')
        self.assertEqual(result['checks']['complete_prospective_holdout'],'UNKNOWN')
    def test_shadow_waits_before_registered_start(self):
        with tempfile.TemporaryDirectory() as folder, patch('research.shadow.PaperReader') as reader:
            reader.return_value.get.return_value=[{'date':'2026-10-30','close':'16:00'}]
            advance(folder,datetime(2026,10,31,tzinfo=timezone.utc))
            self.assertIn('WAITING_FOR_START',(Path(folder)/'status.json').read_text())
    def test_shadow_refuses_late_bootstrap(self):
        with tempfile.TemporaryDirectory() as folder, patch('research.shadow.PaperReader') as reader:
            reader.return_value.get.return_value=[{'date':'2026-11-03','close':'16:00'}]
            with self.assertRaises(ValueError): advance(folder,datetime(2026,11,4,tzinfo=timezone.utc))
    def test_first_session_is_idempotent_and_has_no_same_close_fill(self):
        import pandas as pd
        import json
        dates=pd.bdate_range(end='2026-11-02',periods=61,tz='America/New_York')
        calendar=[{'date':d.date().isoformat(),'close':'16:00'} for d in dates]
        data=pd.DataFrame({'Open':range(100,161),'High':range(102,163),'Low':range(99,160),
                           'Close':range(101,162),'Volume':1000},index=dates)
        with tempfile.TemporaryDirectory() as folder, patch('research.shadow.PaperReader') as reader, patch('research.shadow.yf.Ticker') as ticker:
            reader.return_value.get.return_value=calendar
            ticker.return_value.history.return_value=data
            now=datetime(2026,11,2,23,tzinfo=timezone.utc)
            advance(folder,now)
            result=json.loads((Path(folder)/'2026-11-02/result.json').read_text())
            self.assertEqual(result['equity'],100000)
            self.assertTrue(all(not r['fills'] for r in result['results'].values()))
            advance(folder,now)
            self.assertEqual(ticker.return_value.history.call_count,5)
