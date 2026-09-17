"""
Master ML pipeline runner.
Run this once to build the full ML system:
  python ml/run_pipeline.py

Steps:
  1. Fetch 5 years of historical data + compute features
  2. Train LightGBM meta-labeling model
  3. Run Bayesian parameter optimization
  4. Print summary and recommended config changes
"""
import os, sys
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

ML_DIR = os.path.dirname(os.path.abspath(__file__))

print("="*60)
print("AUTONOMOUS TRADING AGENT - ML PIPELINE")
print("="*60)

# Step 1: Build dataset
print("\n[1/3] Building training dataset (5 years, 5 tickers)...")
from ml.data_pipeline import build_dataset
df = build_dataset()
os.makedirs(ML_DIR, exist_ok=True)
training_csv = os.path.join(ML_DIR, "training_data.csv")
df.to_csv(training_csv)
print(f"Dataset: {len(df)} samples saved")

# Step 2: Train model
print("\n[2/3] Training LightGBM meta-labeling model...")
from ml.train_model import train_meta_labeling_model
model, features = train_meta_labeling_model(data_path=training_csv)
print("Model trained and saved")

# Step 3: Bayesian optimization
print("\n[3/3] Running Bayesian parameter optimization...")
print("(50 trials - takes 3-5 minutes)")
from ml.optimize import run_optimization
best_params = run_optimization(n_trials=50)

# Final summary
import json
print("\n" + "="*60)
print("ML PIPELINE COMPLETE")
print("="*60)
print("\nFiles created:")
print("  ml/training_data.csv      - 5yr feature matrix")
print("  ml/meta_model.pkl         - trained LightGBM model")
print("  ml/feature_importance.csv - top predictive features")
print("  ml/optimal_params.json    - Bayesian optimal params")
print("  ml/optimization_results.csv - all trials")

print("\nNext step:")
print("  Review ml/optimal_params.json")
print("  Update config.py with recommended values")
print("  Integrate MetaLabelPredictor into signals.py")
