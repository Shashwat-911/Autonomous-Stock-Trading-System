import pickle
import numpy as np
import pandas as pd
import os
import logging

logger = logging.getLogger(__name__)

class MetaLabelPredictor:
    """
    Loads the trained LightGBM model and predicts
    trade success probability for live signals.
    """
    
    def __init__(self, model_path: str = "ml/meta_model.pkl"):
        self.model = None
        self.features = []
        self.threshold = 0.65
        self.model_path = model_path
        self._load_model()
    
    def _load_model(self):
        if not os.path.exists(self.model_path):
            logger.warning(
                "Meta model not found at %s. "
                "Run ml/train_model.py first. "
                "All signals will pass through unfiltered.",
                self.model_path
            )
            return
        
        try:
            with open(self.model_path, "rb") as f:
                data = pickle.load(f)
            self.model = data["model"]
            self.features = data["features"]
            self.threshold = data.get("threshold", 0.65)
            logger.info(
                "Meta model loaded: %d features, "
                "threshold=%.2f",
                len(self.features), self.threshold
            )
        except Exception as e:
            logger.error("Failed to load meta model: %s", e)
            self.model = None
    
    def should_trade(self, df: pd.DataFrame) -> tuple[bool, float]:
        """
        Given indicator-enriched DataFrame, predict whether
        the current signal is likely to be profitable.
        
        Returns: (should_trade: bool, probability: float)
        """
        if self.model is None:
            return True, 1.0  # No model: pass all signals
        
        try:
            # Import here to avoid circular imports
            import sys, os as _os
            sys.path.insert(0, _os.path.abspath(
                _os.path.join(_os.path.dirname(__file__), '..')))
            from ml.data_pipeline import compute_features
            
            # Compute features on last row
            features_df = compute_features(df)
            last_row = features_df.iloc[[-1]]
            
            # Use only trained features
            available = [f for f in self.features 
                        if f in last_row.columns]
            missing = [f for f in self.features 
                      if f not in last_row.columns]
            
            if missing:
                logger.warning(
                    "Missing features: %s. "
                    "Using available features only.", missing
                )
            
            if not available:
                return True, 1.0
            
            X = last_row[available].values
            
            # Handle NaN values
            if np.isnan(X).any():
                logger.warning(
                    "NaN in features — passing signal unfiltered"
                )
                return True, 1.0
            
            prob = self.model.predict_proba(X)[0][1]
            should = prob >= self.threshold
            
            logger.info(
                "MetaLabel prediction: P(success)=%.3f "
                "(threshold=%.2f) -> %s",
                prob, self.threshold,
                "TRADE" if should else "SKIP"
            )
            
            return should, float(prob)
            
        except Exception as e:
            logger.error(
                "MetaLabel prediction failed: %s — "
                "passing signal unfiltered", e
            )
            return True, 1.0
