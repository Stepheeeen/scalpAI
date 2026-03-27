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

    def get_confidence(self, features: dict) -> float:
        """Returns a confidence score between 0.0 and 1.0."""
        if not features:
            return 0.0
            
        if self.model:
            try:
                # Convert features to DMatrix
                # Order matters here! Should match training order.
                feature_names = ["spread", "velocity_100ms", "velocity_500ms", "velocity_1s", "volatility"]
                data = np.array([[features.get(f, 0.0) for f in feature_names]])
                dmatrix = xgb.DMatrix(data, feature_names=feature_names)
                
                prediction = self.model.predict(dmatrix)
                return float(prediction[0])
            except Exception as e:
                self.logger.error(f"AI Prediction Error: {e}")
                return 0.0
        else:
            # MOCK MODE: Return high confidence if velocity is strong to test executioner
            velocity = features.get("velocity_100ms", 0)
            if abs(velocity) > 0.1: # Simulating momentum
                 return 0.85
            return 0.5
