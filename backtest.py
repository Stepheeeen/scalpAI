import pandas as pd
import os
from brain import XGBoostGatekeeper
from features import FeatureFactory
from config_loader import Config

def backtest():
    config = Config()
    input_file = config.csv_file
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Run the bot first to collect data.")
        return

    print(f"Initializing AI Backtest on {input_file}...")
    brain = XGBoostGatekeeper()
    feature_factory = FeatureFactory()
    
    df = pd.read_csv(input_file)
    trades = []
    active_trade = None # {entry_price, side, sl, tp, has_be_set}
    
    # Risk settings from config
    SL_PIPS = config.risk_stop_loss_pips if hasattr(config, "risk_stop_loss_pips") else 15
    TP_PIPS = config.risk_take_profit_pips if hasattr(config, "risk_take_profit_pips") else 25
    BE_PIPS = config.risk_auto_break_even_pips if hasattr(config, "risk_auto_break_even_pips") else 5
    THRESHOLD = config.target_confidence
    
    for i in range(len(df)):
        tick = df.iloc[i]
        
        # 1. Update features
        feature_factory.add_tick(tick['bid'], tick['ask'], tick['server_time'])
        
        if active_trade is None:
            # 2. Get Signal
            features = feature_factory.get_features()
            if not features:
                continue
                
            signal_type, confidence = brain.get_signal(features)
            
            if confidence >= THRESHOLD:
                if signal_type == 1: # BUY
                    active_trade = {
                        "entry_price": tick['ask'],
                        "side": "BUY",
                        "sl": tick['ask'] - (SL_PIPS * 0.01),
                        "tp": tick['ask'] + (TP_PIPS * 0.01),
                        "has_be_set": False
                    }
                elif signal_type == 2: # SELL
                    active_trade = {
                        "entry_price": tick['bid'],
                        "side": "SELL",
                        "sl": tick['bid'] + (SL_PIPS * 0.01),
                        "tp": tick['bid'] - (TP_PIPS * 0.01),
                        "has_be_set": False
                    }
        else:
            # 3. Manage Active Trade
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
        print("No trades executed with current threshold.")
        return

    win_rate = len([t for t in trades if t > 0]) / len(trades)
    total_profit = sum(trades)
    print(f"\n--- AI Backtest Results ---")
    print(f"Total Trades: {len(trades)}")
    print(f"Win Rate: {win_rate*100:.2f}%")
    print(f"Net Pips: {total_profit:.2f}")
    if len(trades) > 0:
        print(f"Avg Pips/Trade: {total_profit/len(trades):.2f}")

if __name__ == "__main__":
    backtest()
