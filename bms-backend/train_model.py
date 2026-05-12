import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

print("Booting Sentinel-BMS Training Sequence...")
print("Loading Kaggle battery dataset (battery_dataset.csv)...")

try:
    df = pd.read_csv('battery_dataset.csv')
except FileNotFoundError:
    print("CRITICAL ERROR: 'battery_dataset.csv' not found in the directory.")
    exit()

# 1. Feature Mapping
# We map the Kaggle dataset columns to match the 3 inputs your server.py expects:
# [avg_voltage, abs(data.current), data.temp]
features = ['Voltage', 'Current', 'Temperature']
target = 'SOH'

print(f"Extracting features: {features}")
print(f"Targeting: {target}")

X = df[features]
y = df[target]

# 2. Train/Test Split (80% training, 20% testing)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 3. Initialize and Train the AI Brain
print("Training Random Forest Regressor (Optimized for non-linear BMS data)...")
model = RandomForestRegressor(n_estimators=150, max_depth=15, random_state=42)
model.fit(X_train, y_train)

# 4. Evaluate Accuracy
print("Running diagnostic tests on unseen data...")
y_pred = model.predict(X_test)
mae = mean_absolute_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)

print("\n--- Diagnostic Results ---")
print(f"Mean Absolute Error (MAE): {mae:.2f}%")
print(f"Model R2 Score: {r2:.4f}")

# 5. Export for Production
joblib.dump(model, 'bms_soh_model.pkl')
print("\n✅ Success! 'bms_soh_model.pkl' has been generated.")
print("You can now upload this .pkl file to your Render server.")
