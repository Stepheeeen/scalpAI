import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_synthetic_gold_data(num_samples=1000):
    """Generate realistic synthetic gold price data for training."""
    np.random.seed(42)
    
    # Starting prices for gold (XAUUSD)
    base_price = 2400.00
    
    # Generate timestamps
    timestamps = []
    start_time = datetime(2024, 1, 1, 0, 0, 0)
    for i in range(num_samples):
        timestamps.append(start_time + timedelta(seconds=i*0.1))  # ~100ms per tick
    
    # Generate bid/ask with realistic spread and movement
    prices = [base_price]
    for i in range(num_samples - 1):
        # Random walk with mean reversion
        drift = np.random.normal(0, 0.005)
        noise = np.random.normal(0, 0.02)
        prices.append(prices[-1] + drift + noise)
    
    prices = np.array(prices)
    
    # Gold spread is typically 0.01-0.05 pips
    spread = np.random.uniform(0.01, 0.05, num_samples)
    
    bid = prices - (spread / 2)
    ask = prices + (spread / 2)
    
    # Convert to cTrader format (0.01 unit)
    bid_raw = (bid * 100000).astype(int)
    ask_raw = (ask * 100000).astype(int)
    
    # Server times (milliseconds)
    server_times = [int(ts.timestamp() * 1000) for ts in timestamps]
    local_times = [int(ts.timestamp() * 1000) for ts in timestamps]
    latencies = np.random.uniform(5, 50, num_samples).astype(int)
    
    df = pd.DataFrame({
        'timestamp': [ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] for ts in timestamps],
        'bid': bid,
        'ask': ask,
        'server_time': server_times,
        'local_time': local_times,
        'latency_ms': latencies,
    })
    
    return df

if __name__ == "__main__":
    print("Generating synthetic gold price data...")
    df = generate_synthetic_gold_data(1000)
    df.to_csv("live_gold_data.csv", index=False)
    print(f"✅ Generated {len(df)} synthetic data points")
    print(f"Sample data:\n{df.head()}")
