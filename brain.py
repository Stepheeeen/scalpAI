import os
import xgboost as xgb
import numpy as np
import logging

class XGBoostGatekeeper:
    def __init__(self, model_path: str = "xgboost_gold_model.json"):
        self.model_path = model_path
        self.model = None
        self.logger = logging.getLogger("XGBoostGatekeeper")
        self.load_model()

    def load_model(self):
        if os.path.exists(self.model_path):
            try:
                self.model = xgb.Booster()
                self.model.load_model(self.model_path)
                self.logger.info(f"AI Model loaded from {self.model_path}")
            except Exception as e:
                self.logger.error(f"Failed to load AI model: {e}")
        else:
            self.logger.warning(f"AI Model not found at {self.model_path}. Running in MOCK Mode.")

    def get_signal(self, features: dict) -> tuple:
        """
        Processes features and returns (signal_type, confidence).
        signal_type: 0 (None), 1 (Buy), 2 (Sell)
        """
        if not features:
            return 0, 0.0
            
        if self.model:
            try:
                # Feature names must match training EXACTLY
                feature_names = ["spread", "velocity_100ms", "velocity_500ms", "velocity_1s", "volatility"]
                data = np.array([[features.get(f, 0.0) for f in feature_names]])
                dmatrix = xgb.DMatrix(data, feature_names=feature_names)
                
                # Predict returns probabilities for each class
                probs = self.model.predict(dmatrix)[0]
                signal_type = np.argmax(probs)
                confidence = float(probs[signal_type])
                
                return signal_type, confidence
            except Exception as e:
                self.logger.error(f"AI Prediction Error: {e}")
                return 0, 0.0
        else:
            # MOCK MODE: Return high confidence if velocity is strong
            v100 = features.get("velocity_100ms", 0)
            if v100 > 1.5:  # ~1.5 pips
                return 1, 0.85 # Mock BUY
            elif v100 < -1.5:
                return 2, 0.85 # Mock SELL
            return 0, 0.5
