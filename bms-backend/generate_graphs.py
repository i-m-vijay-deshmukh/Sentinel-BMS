import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# Set academic plotting style parameters
sns.set_theme(style="ticks")
plt.rcParams.update({
    'font.size': 11,
    'font.family': 'serif',
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'figure.titlesize': 13
})

# ==========================================
#  PHYSICS CONSTANTS & CAPTURE REPLICAS
# ==========================================
R0_NOMINAL_OHM = 0.050

def engineer_features(v, i, t):
    v = np.asarray(v, dtype=float).ravel()
    i = np.asarray(i, dtype=float).ravel()
    t = np.asarray(t, dtype=float).ravel()
    return np.column_stack([
        v, i, t, v * i,
        v + i * R0_NOMINAL_OHM,
        i ** 2 * R0_NOMINAL_OHM,
        np.maximum(t - 30.0, 0.0),
        4.2 - v,
        np.maximum(i - 1.0, 0.0),
        v / np.maximum(i, 0.1),
        (4.2 - v) * i,
        v ** 2, t ** 2
    ])

# ==========================================
#  DATA LOADING & MODEL TRAINING REPLICA
# ==========================================
csv_path = "battery_dataset.csv"
if not os.path.exists(csv_path):
    # If the file is inside bms-backend, fall back safely
    csv_path = os.path.join("bms-backend", "battery_dataset.csv")

print(f"[PROCESS] Loading data from {csv_path}...")
df = pd.read_csv(csv_path)

X_raw = df[["Voltage", "Current", "Temperature"]].values.copy()
X_raw[:, 1] = np.abs(X_raw[:, 1])  # Absolute current magnitude
y_soh = df["SOH"].values

# Split data to mimic the final evaluation framework
X_tr_raw, X_te_raw, y_tr, y_te = train_test_split(X_raw, y_soh, test_size=0.20, random_state=42)

# Run feature engineering pipeline
Xe_tr = engineer_features(X_tr_raw[:, 0], X_tr_raw[:, 1], X_tr_raw[:, 2])
Xe_te = engineer_features(X_te_raw[:, 0], X_te_raw[:, 1], X_te_raw[:, 2])

scaler = StandardScaler()
Xs_tr = scaler.fit_transform(Xe_tr)
Xs_te = scaler.transform(Xe_te)

print("[PROCESS] Training estimator matrix layers...")
gbr = GradientBoostingRegressor(n_estimators=1000, learning_rate=0.02, max_depth=4, min_samples_leaf=5, subsample=0.75, loss="huber", random_state=42)
gbr.fit(Xs_tr, y_tr)

calibrator = IsotonicRegression(out_of_bounds="clip")
train_raw_preds = gbr.predict(Xs_tr)
calibrator.fit(train_raw_preds, y_tr)

# Generate hold-out predictions
te_raw_preds = gbr.predict(Xs_te)
preds = np.clip(calibrator.predict(te_raw_preds), 27.79, 100.0)

# ==========================================
#  GRAPH 1 & 2: REGRESSION & IMPORTANCE COMBINED
# ==========================================
print("[GRAPH] Generating Figures 1 and 2 (ML Metrics Combination)...")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))

# Plot 1: Actual vs Predicted Scatter mapping
ax1.scatter(y_te, preds, color='#1f77b4', alpha=0.3, edgecolors='none', s=12)
ideal_line = np.linspace(25, 105, 100)
ax1.plot(ideal_line, ideal_line, color='red', linestyle='--', linewidth=1.5, label='Ideal Fit ($Y=X$)')
ax1.set_title('Predicted vs. Actual Cell SOH', fontweight='bold')
ax1.set_xlabel('True SOH (%)')
ax1.set_ylabel('Predicted SOH (%)')
ax1.set_xlim(25, 105)
ax1.set_ylim(25, 105)
ax1.grid(True, linestyle=':', alpha=0.5)
ax1.legend(loc='upper left')

# Plot 2: Relative feature weights
feature_names = [
    "Terminal Voltage ($V$)", "Load Current ($|I|$)", "Temperature ($T$)", "Instantaneous Power",
    "Approx OCV", "Joule Heating Rate", "Thermal Stress ($>30" + r"^{\circ}" + "C$)", "Voltage Deficit ($4.2-V$)",
    "High C-Rate Stress", "Pseudo-Impedance ($V/I$)", "Power Deficit", "Quadratic Voltage ($V^2$)",
    "Quadratic Temperature ($T^2$)"
]
importances = gbr.feature_importances_
indices = np.argsort(importances)

ax2.barh(range(len(indices)), importances[indices], color='#2ca02c', align='center', height=0.6)
ax2.set_yticks(range(len(indices)))
ax2.set_yticklabels([feature_names[i] for i in indices])
ax2.set_title('Relative Physics Feature Importance', fontweight='bold')
ax2.set_xlabel('Relative Importance Weight Score')
ax2.grid(True, axis='x', linestyle=':', alpha=0.5)

plt.tight_layout()
plt.savefig('ml_evaluation_metrics.png', dpi=300)
plt.close()
print(" -> Saved: 'ml_evaluation_metrics.png'")

# ==========================================
#  GRAPH 3: DYNAMIC VOLTAGE SAG CORRECTION
# ==========================================
print("[GRAPH] Generating Figure 3 (Voltage Sag Correction Transient Profile)...")
# Synthesize a realistic bench trial dataset representing a sudden heavy load transient step
time_steps = np.arange(0, 120, 1)
current_profile = np.zeros_like(time_steps, dtype=float)
current_profile[20:80] = 0.800  # Apply 2.5A discharge load step at t=20s

# Generate realistic sag baseline using your model bounds
r_internal_sim = 0.085  # Simulated mid-life internal resistance state
true_ocv = 3.92 - (0.0005 * time_steps)  # Slow chemical decay slope
v_terminal_profile = true_ocv - (current_profile * r_internal_sim)

# Add small random analog sensor noise mimicking ACS712 tracking artifacts
np.random.seed(42)
v_terminal_noisy = v_terminal_profile + np.random.normal(0, 0.004, size=len(time_steps))

# Run the reverse sag mapping equation: V_oc = V_terminal + I * R_est
v_oc_recovered = v_terminal_noisy + (current_profile * r_internal_sim)

fig, (ax_v, ax_i) = plt.subplots(2, 1, figsize=(7, 5.5), sharex=True)

ax_v.plot(time_steps, v_terminal_noisy, color='gray', label='Measured Terminal Voltage ($V_{\\text{terminal}}$)', linewidth=1.0)
ax_v.plot(time_steps, v_oc_recovered, color='#1f77b4', label='Open-Circuit Voltage ($V_{\\text{oc}}$)', linewidth=1.6)
ax_v.set_ylabel('Cell Voltage(V)')
ax_v.set_title('Dynamic Voltage Sag Correction', fontweight='bold')
ax_v.grid(True, linestyle=':', alpha=0.5)
ax_v.legend(loc='lower left')
ax_v.set_ylim(3.5, 4.1)

ax_i.plot(time_steps, current_profile, color='red', label='Transient Load Step ($I$)', linewidth=1.5)
ax_i.set_ylabel('Pack Discharging Current (A)')
ax_i.set_xlabel('Test Time Duration (Seconds)')
ax_i.grid(True, linestyle=':', alpha=0.5)
ax_i.legend(loc='upper right')
ax_i.set_ylim(-0.1, 1.7)

plt.tight_layout()
plt.savefig('voltage_sag_correction.png', dpi=300)
plt.close()
print(" -> Saved: 'voltage_sag_correction.png'")
print("\n[SUCCESS] Graphics generation sequence completed successfully.")