import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import os

# Configuration
INPUT_FILE = "live_gold_data.csv"
MODEL_OUTPUT = "xgboost_gold_model.json"
TARGET_PIPS = 15 # True scalping target
LOOKAHEAD_TICKS = 200 # More breathing room

def generate_labels(df):
    """Generates 1 for BUY, 2 for SELL, 0 for NONE based on future price moves."""
    # Using mid-price for labeling
    df['mid'] = (df['bid'] + df['ask']) / 2
    
    labels = []
    for i in range(len(df) - LOOKAHEAD_TICKS):
        current_price = df['mid'].iloc[i]
        future_prices = df['mid'].iloc[i+1 : i+LOOKAHEAD_TICKS+1]
        
        # Gold 1 pip = 0.01. 50 pips = 0.50
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
