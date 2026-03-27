import pandas as pd
import os

# Configuration
INPUT_FILE = "live_gold_data.csv"
SL_PIPS = 15
TP_PIPS = 25
BE_PIPS = 5

def backtest():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run the bot first to collect data.")
        return

    print("Replaying historical ticks...")
    df = pd.read_csv(INPUT_FILE)
    df['mid'] = (df['bid'] + df['ask']) / 2
    
    # Simulating signals (Assuming the model was already trained)
    # Using a simple moving average crossover for the backtest demonstration
    df['ma5'] = df['mid'].rolling(5).mean()
    df['ma20'] = df['mid'].rolling(20).mean()
    
    trades = []
    active_trade = None # {entry_price, side, sl, tp, has_be_set}
    
    for i in range(20, len(df)):
        tick = df.iloc[i]
        
        if active_trade is None:
            # Signal: MA5 Cross MA20
            if df['ma5'].iloc[i] > df['ma20'].iloc[i] and df['ma5'].iloc[i-1] <= df['ma20'].iloc[i-1]:
                # BUY
                active_trade = {
                    "entry_price": tick['ask'],
                    "side": "BUY",
                    "sl": tick['ask'] - (SL_PIPS * 0.01),
                    "tp": tick['ask'] + (TP_PIPS * 0.01),
                    "has_be_set": False
                }
            elif df['ma5'].iloc[i] < df['ma20'].iloc[i] and df['ma5'].iloc[i-1] >= df['ma20'].iloc[i-1]:
                # SELL
                active_trade = {
                    "entry_price": tick['bid'],
                    "side": "SELL",
                    "sl": tick['bid'] + (SL_PIPS * 0.01),
                    "tp": tick['bid'] - (TP_PIPS * 0.01),
                    "has_be_set": False
                }
        else:
            # Manage Active Trade
            if active_trade["side"] == "BUY":
                # Check BE
                if not active_trade["has_be_set"]:
                    profit = tick['bid'] - active_trade["entry_price"]
                    if profit >= (BE_PIPS * 0.01):
                        active_trade["sl"] = active_trade["entry_price"]
                        active_trade["has_be_set"] = True
                
                # Check Exit
                if tick['bid'] >= active_trade["tp"]:
                    trades.append(TP_PIPS)
                    active_trade = None
                elif tick['bid'] <= active_trade["sl"]:
                    # SL or BE Hit
                    loss = (tick['bid'] - active_trade["entry_price"]) * 100
                    trades.append(loss)
                    active_trade = None
            else: # SELL
                # Check BE
                if not active_trade["has_be_set"]:
                    profit = active_trade["entry_price"] - tick['ask']
                    if profit >= (BE_PIPS * 0.01):
                        active_trade["sl"] = active_trade["entry_price"]
                        active_trade["has_be_set"] = True
                
                # Check Exit
                if tick['ask'] <= active_trade["tp"]:
                    trades.append(TP_PIPS)
                    active_trade = None
                elif tick['ask'] >= active_trade["sl"]:
                    loss = (active_trade["entry_price"] - tick['ask']) * 100
                    trades.append(loss)
                    active_trade = None

    # Performance Stats
    if not trades:
        print("No trades executed.")
        return

    win_rate = len([t for t in trades if t > 0]) / len(trades)
    total_profit = sum(trades)
    print(f"--- Backtest Results ---")
    print(f"Total Trades: {len(trades)}")
    print(f"Win Rate: {win_rate*100:.2f}%")
    print(f"Net Pips: {total_profit:.2f}")

if __name__ == "__main__":
    backtest()
