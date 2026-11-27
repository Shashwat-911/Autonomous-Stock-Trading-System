"""Record/replay actual broker decision paths without replaying broker orders.

Dependency responses are a tape, not a market simulator. A match establishes
decision parity for recorded inputs, never hypothetical fills or profitability.
"""
import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

BROKER_METHODS = ('get_account_info','get_current_position','get_all_positions',
    'is_market_open','_has_pending_buy_order','_update_trailing_stop',
    'submit_buy','submit_bracket_buy','submit_sell')
RISK_METHODS = ('can_trade','check_stop_loss','check_portfolio_heat',
    'get_position_size_atr','get_position_size')
CODE_FILES = ('broker/alpaca.py','strategy/signals.py','strategy/data_quality.py',
              'analytics/decision_trace.py')


def code_hashes():
    root=Path(__file__).resolve().parents[1]
    return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in CODE_FILES}


def clean(value):
    return json.loads(json.dumps(value, default=lambda v: {'__model__':v.model_dump(mode='json')} if hasattr(v,'model_dump') else v.isoformat() if isinstance(v,datetime)
        else v.item() if hasattr(v,'item') else str(v)))


class Recorder:
    def __init__(self):
        self.calls=[]; self.originals=[]

    def wrap(self, obj, name, label):
        original=getattr(obj,name)
        def call(*args,**kwargs):
            item={'method':label,'args':clean(args),'kwargs':clean(kwargs)}
            self.calls.append(item)
            try:
                result=original(*args,**kwargs)
                item['result']=clean(result)
                return result
            except Exception as exc:
                item['error']=type(exc).__name__
                raise
        self.originals.append((obj,name,original)); setattr(obj,name,call)

    def restore(self):
        for obj,name,original in reversed(self.originals): setattr(obj,name,original)


def record_tick(broker, frame, context):
    import config
    import broker.alpaca as module
    now=module.datetime.now()
    trace={'schema':2,'recorded_at':datetime.now(timezone.utc).isoformat(),
        'revision':os.getenv('RENDER_GIT_COMMIT',os.getenv('GITHUB_SHA','unknown')),
        'code_sha256':code_hashes(),'symbol':broker.ticker,'bars_csv':frame.to_csv(),
        'context':clean(context),'config':{k:clean(getattr(config,k)) for k in ('SIGNAL','RISK','TRADING','BRACKET','MARKET_REGIME')},
        'min_confidence':broker.min_confidence,'last_buy_time':clean(broker._last_buy_time),
        'decision_clock':now.isoformat(),
        'generator':{k:clean(v) for k,v in vars(broker.signal_generator).items() if isinstance(v,(str,int,float,bool,type(None)))}}
    recorder=Recorder()
    try:
        for method in BROKER_METHODS: recorder.wrap(broker,method,'broker.'+method)
        for method in RISK_METHODS:
            if hasattr(broker.risk_manager,method): recorder.wrap(broker.risk_manager,method,'risk.'+method)
        # SELL paths read open bracket legs directly; preserve those observations.
        recorder.wrap(broker.client,'get_orders','client.get_orders')
        result=broker.run_tick(frame,**context)
        trace['result']=clean(result)
        return result,trace
    except Exception as exc:
        trace['error']=type(exc).__name__
        return {'action':'ERROR','reason':type(exc).__name__},trace
    finally:
        recorder.restore(); trace['calls']=recorder.calls


def replay_tick(payload):
    import io
    from types import SimpleNamespace
    from unittest.mock import patch
    import pandas as pd
    import broker.alpaca as module
    from strategy.signals import SignalGenerator
    if payload.get('code_sha256') != code_hashes():
        return {'status':'BLOCKED_CODE_MISMATCH'}
    if payload.get('error'):
        return {'status':'INCOMPLETE_ERROR_PATH','error':payload['error']}
    tape=copy.deepcopy(payload['calls']); cursor=0
    def restore(value):
        if isinstance(value,list): return [restore(v) for v in value]
        if isinstance(value,dict):
            if '__model__' in value:
                return SimpleNamespace(**{k:restore(v) for k,v in value['__model__'].items()})
            return {k:restore(v) for k,v in value.items()}
        return value
    def dependency(label):
        def call(*args,**kwargs):
            nonlocal cursor
            if cursor >= len(tape): raise AssertionError('Unrecorded dependency')
            item=tape[cursor]; cursor+=1
            if (label,clean(args),clean(kwargs)) != (item['method'],item['args'],item['kwargs']):
                raise AssertionError('Dependency request differs')
            if 'error' in item: raise RuntimeError(item['error'])
            return restore(item['result'])
        return call
    b=object.__new__(module.AlpacaPaperBroker)
    b.ticker=payload['symbol']; b.min_confidence=payload['min_confidence']
    b._last_buy_time={k:datetime.fromisoformat(v) for k,v in payload['last_buy_time'].items()}
    b.risk_manager=SimpleNamespace(**{n:dependency('risk.'+n) for n in RISK_METHODS})
    b.signal_generator=SignalGenerator(b.risk_manager,**payload['config']['SIGNAL'])
    for k,v in payload['generator'].items(): setattr(b.signal_generator,k,v)
    for method in BROKER_METHODS: setattr(b,method,dependency('broker.'+method))
    b.client=SimpleNamespace(get_orders=dependency('client.get_orders'))
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            value=datetime.fromisoformat(payload['decision_clock'])
            return value if tz is None else value.replace(tzinfo=timezone.utc).astimezone(tz)
    frame=pd.read_csv(io.StringIO(payload['bars_csv']),index_col=0,float_precision='round_trip')
    # Compare semantic result; wall-clock logging is not a trading decision.
    def semantic(value): return {k:v for k,v in clean(value).items() if k!='time'}
    try:
        with patch.object(module,'datetime',Clock), patch.multiple('config',**payload['config']):
            result=b.run_tick(frame,**payload['context'])
        match=cursor==len(tape) and semantic(result)==semantic(payload['result'])
        return {'status':'MATCH' if match else 'MISMATCH','scope':'recorded_decision_path_not_counterfactual_execution'}
    except (AssertionError,RuntimeError,KeyError,ValueError) as exc:
        return {'status':'MISMATCH','error':type(exc).__name__}
