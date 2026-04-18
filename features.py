import time
from collections import deque
import numpy as np

class FeatureFactory:
    def __init__(self, window_ms: int = 2000):
        self.window_ms = window_ms
        self.ticks = deque() # Stores (timestamp_ms, bid, ask)
        
    def add_tick(self, bid: float, ask: float, timestamp_ms: int):
        self.ticks.append((timestamp_ms, bid, ask))
        
        # Prune old ticks outside the window
        while self.ticks and (timestamp_ms - self.ticks[0][0]) > self.window_ms:
            self.ticks.popleft()

    def get_features(self) -> dict:
        if len(self.ticks) < 5:
            return {}

        current_ts, current_bid, current_ask = self.ticks[-1]
        
        # 1. Spread (Convert to pips: 0.01 = 1.0)
        spread = (current_ask - current_bid) * 100
        
        # 2. Velocity (Price change in pips)
        v100 = self._calculate_velocity(100) * 100
        v500 = self._calculate_velocity(500) * 100
        v1000 = self._calculate_velocity(1000) * 100
        
        # 3. Volatility (Std deviation of mid-price changes in last 1s)
        # We look at the last 1s of ticks for volatility
        recent_mids = [((t[1] + t[2]) / 2) for t in self.ticks if (current_ts - t[0]) <= 1000]
        volatility = np.std(recent_mids) * 100 if len(recent_mids) > 1 else 0
        
        return {
            "spread": spread,
            "velocity_100ms": v100,
            "velocity_500ms": v500,
            "velocity_1s": v1000,
            "volatility": volatility,
            "tick_count": len(recent_mids)
        }

    def _calculate_velocity(self, ms_ago: int) -> float:
        if not self.ticks:
            return 0.0
        
        current_ts, current_bid, _ = self.ticks[-1]
        target_ts = current_ts - ms_ago
        
        # Search backwards for the most accurate historical tick
        for i in range(len(self.ticks)-1, -1, -1):
            ts, bid, ask = self.ticks[i]
            if ts <= target_ts:
                return current_bid - bid
                
        return current_bid - self.ticks[0][1]
