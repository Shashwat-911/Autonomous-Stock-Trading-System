import unittest
import pandas as pd
from research.simulator import Costs, simulate


def bars(rows):
    return pd.DataFrame(rows, columns=['Open','High','Low','Close','Volume'],
                        index=pd.date_range('2020-01-01', periods=len(rows), tz='UTC'))

ZERO = Costs(0,0,0)

class SimulatorTests(unittest.TestCase):
    def test_next_open_and_last_signal_not_executed(self):
        data = bars([[100,110,90,105,10],[120,125,115,121,10]])
        out = simulate(data, lambda p,q,e: {'target_qty': 1}, costs=ZERO)
        self.assertEqual(out['fills'][0]['price'], 120)
        self.assertEqual(len(out['fills']), 1)
        self.assertEqual(out['final_equity'], 100001)

    def test_stop_first_ambiguity_and_gap(self):
        for opening, expected in [(100,90),(80,80)]:
            data=bars([[100,100,100,100,10],[100,105,95,100,10],[opening,120,70,100,10]])
            def decide(p,q,e):
                return {'target_qty':1, 'stop_distance':10, 'target_distance':10} if len(p)==1 else None
            out=simulate(data, decide, costs=ZERO)
            self.assertEqual(out['fills'][-1]['price'], expected)
            self.assertEqual(out['fills'][-1]['reason'], 'stop')

    def test_partial_exits_conserve_cash_and_episode(self):
        data=bars([[100,100,100,100,10]]*4)
        targets={1:10,2:4,3:0}
        out=simulate(data, lambda p,q,e: {'target_qty':targets[len(p)]} if len(p) in targets else None,
                     costs=Costs(0,0,1))
        self.assertEqual(len(out['episodes']),1)
        self.assertEqual(out['final_equity'],99980)
        self.assertEqual(out['episodes'][0]['net_pnl'],-20)

    def test_invalid_data_rejected(self):
        data=bars([[100,90,80,100,10]]*2)
        with self.assertRaises(ValueError): simulate(data, lambda *a:None)

    def test_eod_flat_and_no_overnight_entry(self):
        data=bars([[100,100,100,100,10]]*3)
        data['is_session_end']=[False,True,True]
        out=simulate(data, lambda *a: {'target_qty':1}, costs=ZERO,flat_daily=True)
        self.assertEqual(out['open_qty'],0)
        self.assertEqual(len(out['fills']),2)

    def test_future_data_does_not_change_earlier_fills(self):
        data=bars([[100,101,99,100,10]]*5)
        decide=lambda p,q,e: {'target_qty':1} if len(p)==1 else None
        short=simulate(data.iloc[:3], decide, costs=ZERO)
        data.iloc[-1,data.columns.get_loc('High')]=1000
        self.assertEqual(short['fills'],simulate(data,decide,costs=ZERO)['fills'])

class AttributionTests(unittest.TestCase):
    def test_unknown_reason_is_not_invented_from_exit_time(self):
        from research.attribution import attribute
        def fill(id, side, day, price):
            return dict(id=id, order_id=id, activity_type='FILL', symbol='X',
                        transaction_time=day+'T19:55:00Z', qty='1',price=str(price),side=side)
        snapshot={'activities':[fill('a','buy','2026-10-20',100),fill('b','sell','2026-10-21',90)],
                  'orders':[{'id':'b','type':'market','client_order_id':'unidentified'}]}
        rows,_=attribute(snapshot)
        self.assertTrue(rows[0]['overnight'])
        self.assertEqual(rows[0]['exit_evidence'],['unknown'])
        self.assertEqual(rows[0]['entry_version'],'unknown')

class ComparisonTests(unittest.TestCase):
    def test_holdout_access_refused_before_reading_files(self):
        from research.compare import compare
        with self.assertRaises(ValueError): compare('missing','2026-11-02','2027-04-30')
