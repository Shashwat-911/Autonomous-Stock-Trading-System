import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (classification_report, 
                              roc_auc_score, precision_score,
                              recall_score)
from sklearn.preprocessing import StandardScaler
import pickle
import os
import sys
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

FEATURE_COLS = [
    "rsi", "rsi_slope", "macd", "macd_signal", 
    "macd_hist", "macd_hist_slope", "bb_pct",
    "close_vs_sma", "close_vs_ema", "atr_pct",
    "atr_pct_5", "volatility_ratio", "volume_ratio",
    "volume_spike", "adx", "adx_trending", "di_diff",
    "return_1h", "return_3h", "return_6h", "return_24h",
    "hour", "day_of_week", "is_morning", "is_afternoon"
]

def train_meta_labeling_model(data_path: str = "ml/training_data.csv"):
    """
    Train LightGBM classifier to predict trade success probability.
    Uses TimeSeriesSplit to prevent data leakage.
    """
    print("Loading training data...")
    df = pd.read_csv(data_path, index_col=0)
    
    # Use only available feature columns
    available_features = [c for c in FEATURE_COLS if c in df.columns]
    print(f"Using {len(available_features)} features")
    
    X = df[available_features].values
    y = df["label"].values
    
    print(f"Dataset: {len(X)} samples, "
          f"{y.mean():.1%} positive rate")
    
    # TimeSeriesSplit — no data leakage
    tscv = TimeSeriesSplit(n_splits=5)
    
    fold_aucs = []
    fold_precisions = []
    
    print("\nCross-validation results:")
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X), 1):
        X_train, X_val = X[train_idx], X[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]
        
        model = lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            min_child_samples=50,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=0.1,
            class_weight="balanced",
            random_state=42,
            verbose=-1
        )
        
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50, verbose=False),
                      lgb.log_evaluation(period=-1)]
        )
        
        y_prob = model.predict_proba(X_val)[:, 1]
        auc = roc_auc_score(y_val, y_prob)
        prec = precision_score(y_val, y_prob >= 0.65,
                               zero_division=0)
        fold_aucs.append(auc)
        fold_precisions.append(prec)
        
        print(f"  Fold {fold}: AUC={auc:.3f}, "
              f"Precision@0.65={prec:.3f}")
    
    print(f"\nMean AUC: {np.mean(fold_aucs):.3f} "
          f"(+/- {np.std(fold_aucs):.3f})")
    print(f"Mean Precision@0.65: "
          f"{np.mean(fold_precisions):.3f}")
    
    # Train final model on ALL data
    print("\nTraining final model on full dataset...")
    final_model = lgb.LGBMClassifier(
        n_estimators=400,
        learning_rate=0.05,
        max_depth=6,
        num_leaves=31,
        min_child_samples=50,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        class_weight="balanced",
        random_state=42,
        verbose=-1
    )
    final_model.fit(X, y)
    
    # Feature importance
    importance = pd.DataFrame({
        "feature": available_features,
        "importance": final_model.feature_importances_
    }).sort_values("importance", ascending=False)
    
    print("\nTop 10 most important features:")
    print(importance.head(10).to_string(index=False))
    
    # Save model and feature list
    ml_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(ml_dir, exist_ok=True)
    model_path = os.path.join(ml_dir, "meta_model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": final_model,
            "features": available_features,
            "threshold": 0.65,
            "auc_scores": fold_aucs,
            "precision_scores": fold_precisions,
        }, f)
    
    importance.to_csv(os.path.join(ml_dir, "feature_importance.csv"), index=False)
    print(f"\nModel saved to {model_path}")
    print("Feature importance saved to ml/feature_importance.csv")
    return final_model, available_features

if __name__ == "__main__":
    train_meta_labeling_model()
