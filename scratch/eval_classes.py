import pandas as pd
df = pd.read_csv("live_gold_data.csv")
df['mid'] = (df['bid'] + df['ask']) / 2
labels = []
LOOKAHEAD_TICKS = 100
TARGET_PIPS = 50
for i in range(len(df) - LOOKAHEAD_TICKS):
    current_price = df['mid'].iloc[i]
    future_prices = df['mid'].iloc[i+1 : i+LOOKAHEAD_TICKS+1]
    max_move_up = future_prices.max() - current_price
    max_move_down = current_price - future_prices.min()
    if max_move_up >= (TARGET_PIPS * 0.01):
        labels.append(1)
    elif max_move_down >= (TARGET_PIPS * 0.01):
        labels.append(2)
    else:
        labels.append(0)
from collections import Counter
print(Counter(labels))
