import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import os

# Configuration
INPUT_FILE = "live_gold_data.csv"
MODEL_OUTPUT = "xgboost_gold_model.json"
TARGET_PIPS = 7 # True scalping target
STOP_LOSS_PIPS = 10 # Hard stop
LOOKAHEAD_TICKS = 200 # More breathing room

def generate_labels(df):
    """Generates 1 for BUY, 2 for SELL, 0 for NONE based on future price moves."""
    # Using mid-price for labeling
    df['mid'] = (df['bid'] + df['ask']) / 2
    
    labels = []
    tp_val = TARGET_PIPS * 0.01
    sl_val = STOP_LOSS_PIPS * 0.01
    
    mid_prices = df['mid'].values
    n = len(mid_prices)
    
    for i in range(n - LOOKAHEAD_TICKS):
        current_price = mid_prices[i]
        
        buy_win = False
        sell_win = False
        
        # Simulate exact trade path for BUY
        for j in range(1, LOOKAHEAD_TICKS + 1):
            move = mid_prices[i + j] - current_price
            if move <= -sl_val:
                break # Hit Stop Loss first
            if move >= tp_val:
                buy_win = True
                break # Hit Take Profit first
                
        # Simulate exact trade path for SELL
        for j in range(1, LOOKAHEAD_TICKS + 1):
            move = mid_prices[i + j] - current_price
            if move >= sl_val:
                break # Hit Stop Loss first
            if move <= -tp_val:
                sell_win = True
                break # Hit Take Profit first
        
        if buy_win and not sell_win:
            labels.append(1)
        elif sell_win and not buy_win:
            labels.append(2)
        else:
            labels.append(0) # Ambiguous or SL hit
            
    # Pad labels to match df length
    labels.extend([0] * LOOKAHEAD_TICKS)
    return labels

def train():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Launch the bot in DRY RUN mode to collect data first.")
        return

    print("Loading data...")
    df = pd.read_csv(INPUT_FILE)
    
    print("Engineering features for alignment...")
    # Matches features.py precisely
    df['mid'] = (df['bid'] + df['ask']) / 2
    df['spread'] = (df['ask'] - df['bid']) * 100
    
    # Calculate velocities based on roughly 1 tick ~ 100ms (approximate for training)
    # In a real setup, we would log features directly in the bot to the CSV.
    df['velocity_100ms'] = df['mid'].diff(1).fillna(0) * 100
    df['velocity_500ms'] = df['mid'].diff(5).fillna(0) * 100
    df['velocity_1s'] = df['mid'].diff(10).fillna(0) * 100
    df['volatility'] = df['mid'].rolling(10).std().fillna(0) * 100
    
    df['target'] = generate_labels(df)
    
    # Drop rows without enough history
    df = df.iloc[20:].dropna()
    
    features = ['spread', 'velocity_100ms', 'velocity_500ms', 'velocity_1s', 'volatility']
    X = df[features]
    y = df['target']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print(f"Training XGBoost on {len(X)} samples...")
    model = xgb.XGBClassifier(
        n_estimators=300, # Increased for larger dataset
        max_depth=7,      # Increased depth for complex patterns
        learning_rate=0.05,
        objective='multi:softprob',
        num_class=3,
        tree_method='hist'
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"✅ Training Complete. Accuracy: {acc*100:.2f}%")
    
    model.save_model(MODEL_OUTPUT)
    print(f"🚀 Model saved to {MODEL_OUTPUT}")

if __name__ == "__main__":
    train()
