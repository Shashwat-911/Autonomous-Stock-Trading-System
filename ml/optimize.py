import optuna
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))
from data.fetcher import get_historical_data
from strategy.indicators import add_all_indicators
import logging
logging.disable(logging.CRITICAL)
optuna.logging.set_verbosity(optuna.logging.WARNING)

def backtest_with_params(params: dict, 
                          ticker: str = "NVDA",
                          start: str = "2024-10-01",
                          end: str = "2026-09-01") -> float:
    """
    Run simplified backtest with given parameters.
    Returns Sharpe ratio (higher = better).
    """
    try:
        df = get_historical_data(ticker, start, end, "1h")
        df = add_all_indicators(df)
        df = df.dropna()
        
        if len(df) < 100:
            return -999.0
        
        cash = 100000.0
        shares = 0
        entry_price = 0.0
        returns = []
        prev_cash = cash
        
        rsi_buy = params["rsi_oversold"]
        rsi_sell = params["rsi_overbought"]
        adx_min = params["adx_min"]
        sl_pct = params["sl_pct"]
        tp_pct = params["tp_pct"]
        macd_confirm = params["macd_confirm"]
        
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            price = float(row["Close"])
            rsi = float(row["RSI_14"])
            macd = float(row["MACD"])
            macd_sig = float(row["MACD_Signal"])
            adx = float(row.get("ADX_14", 25.0))
            prev_macd = float(prev["MACD"])
            prev_sig = float(prev["MACD_Signal"])
            
            # Stop-loss / Take-profit check
            if shares > 0:
                if price <= entry_price * (1 - sl_pct):
                    cash += shares * price
                    shares = 0
                elif price >= entry_price * (1 + tp_pct):
                    cash += shares * price
                    shares = 0
            
            # Entry conditions
            if shares == 0 and adx >= adx_min:
                # Path 1: Dip buying
                dip_buy = rsi < rsi_buy
                
                # Path 2: Momentum crossover
                momentum_buy = (
                    macd > macd_sig and
                    prev_macd <= prev_sig and
                    40 <= rsi <= 65
                )
                
                if macd_confirm:
                    momentum_buy = momentum_buy and (macd > macd_sig)
                
                if dip_buy or momentum_buy:
                    max_shares = int((cash * 0.10) / price)
                    if max_shares > 0:
                        cost = max_shares * price
                        cash -= cost
                        shares = max_shares
                        entry_price = price
            
            # Exit on overbought
            elif shares > 0 and rsi > rsi_sell:
                cash += shares * price
                shares = 0
            
            # Track daily return
            current_value = cash + shares * price
            daily_ret = (current_value - prev_cash) / prev_cash
            returns.append(daily_ret)
            prev_cash = current_value
        
        # Close final position
        if shares > 0:
            cash += shares * float(df.iloc[-1]["Close"])
        
        if not returns or np.std(returns) == 0:
            return -999.0
        
        # Sharpe ratio (annualized, hourly bars)
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 * 6.5)
        return float(sharpe)
        
    except Exception as e:
        return -999.0

def objective(trial) -> float:
    params = {
        "rsi_oversold":  trial.suggest_float("rsi_oversold", 25.0, 50.0),
        "rsi_overbought": trial.suggest_float("rsi_overbought", 60.0, 80.0),
        "adx_min":       trial.suggest_float("adx_min", 15.0, 30.0),
        "sl_pct":        trial.suggest_float("sl_pct", 0.005, 0.025),
        "tp_pct":        trial.suggest_float("tp_pct", 0.008, 0.030),
        "macd_confirm":  trial.suggest_categorical("macd_confirm", [True, False]),
    }
    return backtest_with_params(params)

def run_optimization(n_trials: int = 100) -> dict:
    print(f"Running Bayesian optimization ({n_trials} trials)...")
    print("This finds the best parameters automatically.\n")
    
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, 
                  show_progress_bar=True)
    
    best = study.best_params
    best_sharpe = study.best_value
    
    print(f"\n{'='*50}")
    print("OPTIMAL PARAMETERS FOUND:")
    print(f"{'='*50}")
    for k, v in best.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")
    print(f"\nBest Sharpe Ratio: {best_sharpe:.4f}")
    print(f"{'='*50}")
    
    # Compare with current config
    import sys, os
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..')))
    import config
    
    current_params = {
        "rsi_oversold": config.SIGNAL.get("rsi_oversold", 45),
        "rsi_overbought": config.SIGNAL.get("rsi_overbought", 70),
        "adx_min": config.SIGNAL.get("adx_min", 22),
        "sl_pct": config.RISK.get("max_trade_loss_pct", 0.04),
        "tp_pct": 0.012,
        "macd_confirm": True,
    }
    current_sharpe = backtest_with_params(current_params)
    
    print(f"\nCurrent config Sharpe: {current_sharpe:.4f}")
    print(f"Optimal config Sharpe: {best_sharpe:.4f}")
    improvement = ((best_sharpe - current_sharpe) / 
                   abs(current_sharpe) * 100 
                   if current_sharpe != 0 else 0)
    print(f"Improvement: {improvement:+.1f}%")
    
    # Save results
    results_df = study.trials_dataframe()
    ml_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(ml_dir, exist_ok=True)
    results_df.to_csv(os.path.join(ml_dir, "optimization_results.csv"), index=False)
    
    import json
    params_path = os.path.join(ml_dir, "optimal_params.json")
    with open(params_path, "w") as f:
        json.dump({
            "best_params": best,
            "best_sharpe": best_sharpe,
            "current_sharpe": current_sharpe,
            "improvement_pct": improvement,
        }, f, indent=2)
    
    print(f"\nResults saved to {params_path}")
    return best

if __name__ == "__main__":
    best_params = run_optimization(n_trials=100)
