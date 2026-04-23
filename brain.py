import os
import xgboost as xgb
import numpy as np
import logging

class XGBoostGatekeeper:
    def __init__(self, model_path: str = "xgboost_gold_model.json", allow_mock: bool = False):
        self.model_path = model_path
        self.allow_mock = allow_mock
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
                self.model = None
        else:
            self.logger.warning(f"AI Model not found at {self.model_path}.")
            if self.allow_mock:
                self.logger.warning("Mock model mode enabled. This is not a real live trading signal source.")
            else:
                self.logger.warning("Mock model disabled. No live signals will be generated until the real model is available.")

    def get_signal(self, features: dict) -> tuple:
        """
        Processes features and returns (signal_type, confidence).
        signal_type: 0 (None), 1 (Buy), 2 (Sell)
        """
        if not features:
            return 0, 0.0
            
        if self.model:
            try:
                feature_names = ["spread", "velocity_100ms", "velocity_500ms", "velocity_1s", "volatility"]
                data = np.array([[features.get(f, 0.0) for f in feature_names]])
                dmatrix = xgb.DMatrix(data, feature_names=feature_names)
                probs = self.model.predict(dmatrix)[0]
                signal_type = int(np.argmax(probs))
                confidence = float(probs[signal_type])
                return signal_type, confidence
            except Exception as e:
                self.logger.error(f"AI Prediction Error: {e}")
                return 0, 0.0

        if self.allow_mock:
            v100 = features.get("velocity_100ms", 0)
            if v100 > 1.5:
                return 1, 0.85
            elif v100 < -1.5:
                return 2, 0.85
        return 0, 0.0
