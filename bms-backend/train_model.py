
import argparse
import os
import warnings
import joblib
import numpy as np
import pandas as pd

from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split, KFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

warnings.filterwarnings("ignore")

#  PHYSICS CONSTANTS 

NMC_SOC_PTS = np.array([
    0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35,
    0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75,
    0.80, 0.85, 0.90, 0.95, 1.00
])
NMC_OCV_PTS = np.array([
    3.000, 3.130, 3.250, 3.350, 3.420, 3.480, 3.530, 3.570,
    3.600, 3.625, 3.650, 3.670, 3.690, 3.710, 3.730, 3.750,
    3.780, 3.820, 3.870, 3.950, 4.200
])

R_FRESH_OHM   = 0.047    
R_AGED_OHM    = 0.252    
SOH_FRESH_PCT = 100.0
SOH_AGED_PCT  =  27.79

R0_NOMINAL_OHM = 0.050
EOL_SOH_PCT = 80.0
N_CELLS       = 3

#  PHYSICS HELPERS

def soh_to_r(soh_pct: np.ndarray) -> np.ndarray:
    r = R_FRESH_OHM + (soh_pct - SOH_FRESH_PCT) * (
        (R_AGED_OHM - R_FRESH_OHM) / (SOH_AGED_PCT - SOH_FRESH_PCT)
    )
    return np.clip(r, R_FRESH_OHM, R_AGED_OHM)


def v_terminal_to_ocv(v_terminal: np.ndarray,
                       current_a: np.ndarray,
                       r_internal: np.ndarray) -> np.ndarray:
    return v_terminal + current_a * r_internal


def ocv_to_soc(ocv: np.ndarray) -> np.ndarray:
    ocv_clipped = np.clip(ocv, NMC_OCV_PTS[0], NMC_OCV_PTS[-1])
    return np.interp(ocv_clipped, NMC_OCV_PTS, NMC_SOC_PTS)


#  FEATURE

def engineer_features(v: np.ndarray,
                       i: np.ndarray,
                       t: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float).ravel()
    i = np.asarray(i, dtype=float).ravel()
    t = np.asarray(t, dtype=float).ravel()

    return np.column_stack([
        v,
        i,
        t,
        v * i,                            
        v + i * R0_NOMINAL_OHM,           
        i ** 2 * R0_NOMINAL_OHM,          
        np.maximum(t - 30.0, 0.0),        
        4.2 - v,                           
        np.maximum(i - 1.0, 0.0),         
        v / np.maximum(i, 0.1),           
        (4.2 - v) * i,                    
        v ** 2,                            
        t ** 2,                            
    ])


#  CORE MODEL CLASS

class SentinelBMSModel(BaseEstimator, RegressorMixin):

    def __init__(self,
                 n_estimators: int = 1000,
                 learning_rate: float = 0.02,
                 max_depth: int = 4,
                 min_samples_leaf: int = 5,
                 subsample: float = 0.75):
        self.n_estimators      = n_estimators
        self.learning_rate     = learning_rate
        self.max_depth         = max_depth
        self.min_samples_leaf  = min_samples_leaf
        self.subsample         = subsample

        self.scaler_     = StandardScaler()
        self.gbr_        = None
        self.calibrator_ = IsotonicRegression(out_of_bounds="clip")
        self.train_metrics_ = {}

    def fit(self, X_raw: np.ndarray, y_soh: np.ndarray) -> "SentinelBMSModel":
        Xe = engineer_features(X_raw[:, 0], X_raw[:, 1], X_raw[:, 2])
        Xs = self.scaler_.fit_transform(Xe)

        self.gbr_ = GradientBoostingRegressor(
            n_estimators     = self.n_estimators,
            learning_rate    = self.learning_rate,
            max_depth        = self.max_depth,
            min_samples_leaf = self.min_samples_leaf,
            subsample        = self.subsample,
            loss             = "huber",   
            random_state     = 42,
        )
        self.gbr_.fit(Xs, y_soh)

        train_raw_preds = self.gbr_.predict(Xs)
        self.calibrator_.fit(train_raw_preds, y_soh)

        return self

    def _predict_soh_single(self, v: float, i_abs: float, t: float) -> float:
        Xe = engineer_features([v], [i_abs], [t])
        Xs = self.scaler_.transform(Xe)
        raw = self.gbr_.predict(Xs)[0]
        cal = float(self.calibrator_.predict([raw])[0])
        return float(np.clip(cal, SOH_AGED_PCT, SOH_FRESH_PCT))

    def predict(self,
                cell1_v: float,
                cell2_v: float,
                cell3_v: float,
                current: float,
                temp: float) -> dict:
        """
        Full 3S pack minimal inference pipeline.
        Filters out non-required outputs while ensuring physical sag 
        corrections execute properly under the hood.
        """
        i_abs = abs(current)   
        cell_voltages = [cell1_v, cell2_v, cell3_v]

        # ── Internal Calculation: SOH per cell ────────────────────────
        soh_cells = [
            self._predict_soh_single(v, i_abs, temp)
            for v in cell_voltages
        ]

        # ── Internal Calculation: Resistance & Sag-corrected OCV ──────
        r_cells = [float(soh_to_r(np.array([s]))[0]) for s in soh_cells]
        ocv_cells = [
            float(v_terminal_to_ocv(np.array([v]), np.array([current]), np.array([r]))[0])
            for v, r in zip(cell_voltages, r_cells)
        ]

        # ── Internal Calculation: Individual SOC tracking ─────────────
        soc_cells = [float(ocv_to_soc(np.array([ocv]))[0]) for ocv in ocv_cells]

        # ── Final Processing: Compute SOH-weighted pack SOC ───────────
        soh_weights = np.array(soh_cells)
        soh_weights = soh_weights / soh_weights.sum()
        soc_pack = float(np.dot(soh_weights, soc_cells))

        # Output payload minimized strictly to your core required keys
        return {
            "soh_cell1": round(soh_cells[0], 2),
            "soh_cell2": round(soh_cells[1], 2),
            "soh_cell3": round(soh_cells[2], 2),
            "soc_pack":  round(soc_pack, 4)
        }

    def predict_array(self, X_raw: np.ndarray) -> np.ndarray:
        Xe = engineer_features(X_raw[:, 0], X_raw[:, 1], X_raw[:, 2])
        Xs = self.scaler_.transform(Xe)
        raw = self.gbr_.predict(Xs)
        cal = self.calibrator_.predict(raw)
        return np.clip(cal, SOH_AGED_PCT, SOH_FRESH_PCT)

    def save(self, path: str) -> None:
        joblib.dump(self, path, compress=3)
        size_kb = os.path.getsize(path) / 1024
        print(f"  [SAVE] {path}  ({size_kb:.1f} KB)")

    @staticmethod
    def load(path: str) -> "SentinelBMSModel":
        return joblib.load(path)


#  TRAINING PIPELINE

def load_dataset(csv_path: str) -> tuple:
    print(f"\n  [DATA] Loading: {csv_path}")
    df = pd.read_csv(csv_path)
    X_raw = df[["Voltage", "Current", "Temperature"]].values.copy()
    X_raw[:, 1] = np.abs(X_raw[:, 1])   
    y_soh = df["SOH"].values
    return X_raw, y_soh, df


def cross_validate(model: SentinelBMSModel, X_raw: np.ndarray, y_soh: np.ndarray, n_folds: int = 5) -> dict:
    kf = KFold(n_splits=n_folds, shuffle=True, random_state=42)
    fold_rmses, fold_maes = [], []

    for fold, (tr_idx, te_idx) in enumerate(kf.split(X_raw), 1):
        m = SentinelBMSModel(
            n_estimators     = model.n_estimators,
            learning_rate    = model.learning_rate,
            max_depth        = model.max_depth,
            min_samples_leaf = model.min_samples_leaf,
            subsample        = model.subsample,
        )
        m.fit(X_raw[tr_idx], y_soh[tr_idx])
        preds = m.predict_array(X_raw[te_idx])
        fold_rmses.append(np.sqrt(mean_squared_error(y_soh[te_idx], preds)))
        fold_maes.append(mean_absolute_error(y_soh[te_idx], preds))
    return {
        "cv_rmse_mean": float(np.mean(fold_rmses)),
        "cv_rmse_std":  float(np.std(fold_rmses)),
        "cv_mae_mean":  float(np.mean(fold_maes)),
        "cv_mae_std":   float(np.std(fold_maes)),
    }


def evaluate_final(model: SentinelBMSModel, X_raw: np.ndarray, y_soh: np.ndarray) -> dict:
    X_tr, X_te, y_tr, y_te = train_test_split(X_raw, y_soh, test_size=0.20, random_state=42, shuffle=True)
    model.fit(X_tr, y_tr)
    preds = model.predict_array(X_te)

    rmse = float(np.sqrt(mean_squared_error(y_te, preds)))
    mae  = float(mean_absolute_error(y_te, preds))
    r2   = float(r2_score(y_te, preds))
    return {"test_rmse": rmse, "test_mae": mae, "test_r2": r2}


def smoke_test(model: SentinelBMSModel) -> None:
    print("\n  [SMOKE TEST] 3S Pack minimal scenarios:")
    print(f"  {'Scenario':<35s} {'C1-SOH':>7} {'C2-SOH':>7} {'C3-SOH':>7} {'Pack-SOC':>9}")
    print("  " + "─" * 70)

    scenarios = [
        ("Fresh pack, no load", 4.10, 4.08, 4.09, 0.01, 25.0),
        ("Fresh pack, 1C load", 4.05, 4.03, 4.04, 2.50, 26.0),
        ("Mid-aged, 1C load",   3.70, 3.65, 3.68, 2.50, 27.0),
        ("Imbalanced (C2 weak)",3.80, 3.40, 3.78, 2.00, 28.0),
    ]

    for label, v1, v2, v3, I, T in scenarios:
        r = model.predict(v1, v2, v3, I, T)
        print(f"  {label:<35s} {r['soh_cell1']:>6.1f}% {r['soh_cell2']:>6.1f}% {r['soh_cell3']:>6.1f}% {r['soc_pack']:>8.3f}")


def write_summary(out_dir: str, metrics_cv: dict, metrics_test: dict) -> None:
    path = os.path.join(out_dir, "training_summary.txt")
    with open(path, "w") as f:
        f.write("====================================================\n")
        f.write("  Sentinel-BMS  —  Training Summary (Optimized)\n")
        f.write("====================================================\n\n")
        f.write("MINIMIZED MODEL OUTPUTS\n")
        f.write("-" * 30 + "\n")
        for k in ["soh_cell1", "soh_cell2", "soh_cell3", "soc_pack"]:
            f.write(f"  {k}\n")
    print(f"  [SAVE] {path}")


def main():

    parser = argparse.ArgumentParser(description="Sentinel-BMS train.py — Optimized Minimal Output")
    parser.add_argument("--data", default="battery_dataset.csv", help="Path to the dataset CSV")
    parser.add_argument("--output", default=".", help="Output directory")
    parser.add_argument("--no-cv", action="store_true", help="Skip cross-validation")
    args = parser.parse_args()

    print()
    print("=" * 65)
    print("  Sentinel-BMS  —  Model Training Pipeline (Minimized)")
    print("=" * 65)

    X_raw, y_soh, df = load_dataset(args.data)

    metrics_cv = {}
    if not args.no_cv:
        print(f"\n  [CV] Running 5-fold cross-validation …")
        tmp_model = SentinelBMSModel()
        metrics_cv = cross_validate(tmp_model, X_raw, y_soh)

    print(f"\n  [TRAIN] Training evaluation model …")
    eval_model = SentinelBMSModel()
    metrics_test = evaluate_final(eval_model, X_raw, y_soh)

    print(f"\n  [TRAIN] Refitting full dataset for production pkl …")
    final_model = SentinelBMSModel()
    final_model.fit(X_raw, y_soh)
    final_model.train_metrics_ = {**metrics_cv, **metrics_test}

    smoke_test(final_model)

    os.makedirs(args.output, exist_ok=True)
    pkl_path = os.path.join(args.output, "bms_soh_model.pkl")
    final_model.save(pkl_path)
    write_summary(args.output, metrics_cv, metrics_test)

    print(f"\n  [VERIFY] Loading pkl and testing predictive map …")
    loaded = SentinelBMSModel.load(pkl_path)
    test_result = loaded.predict(cell1_v=3.75, cell2_v=3.68, cell3_v=3.71, current=2.50, temp=27.0)
    print(f"    Output Channels Returned:")
    for k, v in test_result.items():
        print(f"      {k:<15s}: {v}")
    print("\n  Done. Optimized binary exported.")


if __name__ == "__main__":
    main()