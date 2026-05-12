from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import numpy as np

app = FastAPI()
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Shared system memory
latest_state = {
    "cell1": 0.0, "cell2": 0.0, "cell3": 0.0,
    "current": 0.0, "temp": 0.0, "charging": False,
    "discharge_active": True, "soh": 100.0 
}

# Load ML Model
try:
    soh_model = joblib.load('bms_soh_model.pkl')
    print("Sentinel-ML Model active.")
except:
    print("Warning: ML Model not found.")

class BMSData(BaseModel):
    cell1: float
    cell2: float
    cell3: float
    current: float
    temp: float
    charging: bool

class PowerState(BaseModel):
    discharge_active: bool

@app.post("/api/esp32_push")
async def receive_esp32_data(data: BMSData):
    global latest_state
    latest_state.update(data.dict())

    # CRITICAL HARDWARE INTERLOCK: Discharge must be OFF if charging
    if data.charging:
        latest_state["discharge_active"] = False

    # State of Health Inference during active discharge
    if not data.charging and abs(data.current) > 0.5:
        try:
            avg_v = (data.cell1 + data.cell2 + data.cell3) / 3.0
            features = np.array([[avg_v, abs(data.current), data.temp]])
            pred_soh = soh_model.predict(features)[0]
            latest_state["soh"] = (latest_state["soh"] * 0.98) + (pred_soh * 0.02)
        except:
            pass

    return {"status": "success", "discharge_enabled": latest_state["discharge_active"]}

@app.post("/api/toggle_power")
async def toggle_power(status: PowerState):
    global latest_state
    # Block toggle-on attempt if system is currently charging
    if latest_state["charging"] and status.discharge_active:
        return {"status": "error", "message": "Safety lock: Charging active"}
    
    latest_state["discharge_active"] = status.discharge_active
    return {"status": "success", "discharge_active": status.discharge_active}

@app.get("/api/react_pull")
async def serve_react_data():
    return latest_state

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)