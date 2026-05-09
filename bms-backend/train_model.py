import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib

print("Generating Sentinel-BMS training data (3S 5000mAh VIPOW Profile)...")

# Simulate 5000 data points of battery aging over time
np.random.seed(42)
cycles = np.random.uniform(0, 1000, 5000)

# Feature 1: Pack Voltage (Drops as health declines and cycles increase)
pack_voltage = 12.6 - (cycles * 0.0004) + np.random.normal(0, 0.05, 5000)

# Feature 2: Current Draw (Simulating a motor load between 0A and 15A)
current_draw = np.random.uniform(0.1, 15.0, 5000)

# Feature 3: Temperature (Pack runs hotter as internal resistance increases)
temperature = 25 + (cycles * 0.008) + (current_draw * 1.2) + np.random.normal(0, 1, 5000)

# Label: State of Health (SOH)
soh_actual = 100 - (cycles * 0.025) + np.random.normal(0, 0.5, 5000)
soh_actual = np.clip(soh_actual, 0, 100)

df = pd.DataFrame({
    'pack_voltage': pack_voltage,
    'current': current_draw,
    'temperature': temperature,
    'soh': soh_actual
})

# Isolate Inputs and Outputs
X = df[['pack_voltage', 'current', 'temperature']]
y = df['soh']

print("Training Machine Learning Model...")
model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
model.fit(X, y)

# Save the trained brain
joblib.dump(model, 'bms_soh_model.pkl')
print("✅ Success! 'bms_soh_model.pkl' generated and ready for deployment.")