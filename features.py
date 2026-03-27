import time
from collections import deque
import numpy as np

class FeatureFactory:
    def __init__(self, window_ms: int = 1000):
        self.window_ms = window_ms
        self.ticks = deque() # Stores (timestamp_ms, bid, ask)
        
    def add_tick(self, bid: float, ask: float, timestamp_ms: int):
        self.ticks.append((timestamp_ms, bid, ask))
        
        # Prune old ticks outside the 1s window
        while self.ticks and (timestamp_ms - self.ticks[0][0]) > self.window_ms:
            self.ticks.popleft()

    def get_features(self) -> dict:
        if len(self.ticks) < 2:
            return {}

        current_ts, current_bid, current_ask = self.ticks[-1]
        
        # 1. Spread Stability
        spread = current_ask - current_bid
        
        # 2. Velocity (Price change over last X ms)
        # Find ticks closest to -100ms, -500ms, -1000ms
        v100 = self._calculate_velocity(100)
        v500 = self._calculate_velocity(500)
        v1000 = self._calculate_velocity(1000)
        
        # 3. Micro-Volatility (Std deviation of mid-price changes)
        mids = [(t[1] + t[2]) / 2 for t in self.ticks]
        volatility = np.std(np.diff(mids)) if len(mids) > 1 else 0
        
        return {
            "spread": spread,
            "velocity_100ms": v100,
            "velocity_500ms": v500,
            "velocity_1s": v1000,
            "volatility": volatility,
            "tick_count": len(self.ticks)
        }

    def _calculate_velocity(self, ms_ago: int) -> float:
        if not self.ticks:
            return 0.0
        
        current_ts, current_bid, _ = self.ticks[-1]
        target_ts = current_ts - ms_ago
        
        # Find the tick closest to target_ts
        for ts, bid, ask in self.ticks:
            if ts >= target_ts:
                return current_bid - bid
                
        return 0.0
