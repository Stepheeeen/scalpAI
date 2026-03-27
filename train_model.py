import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import os

# Configuration
INPUT_FILE = "live_gold_data.csv"
MODEL_OUTPUT = "xgboost_gold_model.json"
TARGET_PIPS = 10 # We want to predict a 10-pip move
LOOKAHEAD_TICKS = 20 # ...within the next 20 ticks

def generate_labels(df):
    """Generates 1 for BUY, 2 for SELL, 0 for NONE based on future price moves."""
    # Using mid-price for labeling
    df['mid'] = (df['bid'] + df['ask']) / 2
    
    labels = []
    for i in range(len(df) - LOOKAHEAD_TICKS):
        current_price = df['mid'].iloc[i]
        future_prices = df['mid'].iloc[i+1 : i+LOOKAHEAD_TICKS+1]
        
        # Gold 1 pip = 0.01. 10 pips = 0.10
        max_move_up = future_prices.max() - current_price
        max_move_down = current_price - future_prices.min()
        
        if max_move_up >= (TARGET_PIPS * 0.01):
            labels.append(1) # Up move
        elif max_move_down >= (TARGET_PIPS * 0.01):
            labels.append(2) # Down move
        else:
            labels.append(0) # Noise
            
    # Pad labels to match df length
    labels.extend([0] * LOOKAHEAD_TICKS)
    return labels

def train():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found. Run the bot first to collect data.")
        return

    print("Loading data...")
    df = pd.read_csv(INPUT_FILE)
    
    # We need features. Since features are calculated in real-time in the bot,
    # for training we re-calculate them from the CSV.
    # Note: In a real HFT setup, you'd log features directly to the CSV.
    
    print("Engineering features and labels...")
    # Features (simplified for this script, should match features.py)
    df['mid'] = (df['bid'] + df['ask']) / 2
    df['spread'] = df['ask'] - df['bid']
    df['velocity_1s'] = df['mid'].diff(10) # Roughly 10 ticks ~ 1s?
    df['volatility'] = df['mid'].rolling(20).std()
    
    df['target'] = generate_labels(df)
    
    # Drop NAs from rolling/diff
    df = df.dropna()
    
    features = ['spread', 'velocity_1s', 'volatility', 'latency_ms']
    X = df[features]
    y = df['target']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("Training XGBoost...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        objective='multi:softprob',
        num_class=3,
        tree_method='hist' # Fast training
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"Training Complete. Accuracy: {acc*100:.2f}%")
    
    model.save_model(MODEL_OUTPUT)
    print(f"Model saved to {MODEL_OUTPUT}")

if __name__ == "__main__":
    train()
