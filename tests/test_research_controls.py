import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from research.random_control import compare_random, randomized_trend
from research.simulator import Costs, cost_in_r
from research.register import record
from research.gates import evaluate


class ControlsTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame({'Open':[100+i for i in range(40)],'High':[102+i for i in range(40)],
            'Low':[99+i for i in range(40)],'Close':[101.5+i for i in range(40)],'Volume':1000},
            index=pd.date_range('2020-01-01',periods=40,tz='UTC'))

    def test_seeded_control_reproducible_and_does_not_promote(self):
        a=compare_random({'SPY':self.frame()},trials=3)
        self.assertEqual(a,compare_random({'SPY':self.frame()},trials=3))
        self.assertFalse(a['automatic_promotion'])
        self.assertEqual(len(a['controls']),3)

    def test_cost_r_is_round_trip_and_stop_scaled(self):
        self.assertAlmostEqual(cost_in_r(100,2,Costs(2,3,.005)),.045)
        with self.assertRaises(ValueError): cost_in_r(100,0)

    def test_failed_trials_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp, patch('research.register.subprocess.check_output',return_value='revision'):
            path=Path(tmp)/'tried.jsonl'
            record(path,{'seed':1},{'status':'FAILED'})
            record(path,{'seed':2},{'status':'NEGATIVE'})
            self.assertEqual(len(path.read_text().splitlines()),2)

    def test_new_registration_does_not_rewrite_old_holdout(self):
        old=json.loads(Path('research/protocol.json').read_text())
        new=json.loads(Path('research/experiments/etf-2026-11-30.json').read_text())
        self.assertEqual(old['prospective_holdout'][0],'2026-11-02')
        self.assertEqual(new['prospective_holdout'][0],'2026-11-30')
        self.assertEqual(evaluate({'complete_prospective_holdout':True},'2027-05-15',new['cannot_promote_before'])['checks']['complete_prospective_holdout'],'UNKNOWN')
