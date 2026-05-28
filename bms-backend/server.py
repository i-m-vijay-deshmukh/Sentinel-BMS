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

latest_state = {
    "cell1": 0.0, "cell2": 0.0, "cell3": 0.0,
    "current": 0.0, "temp": 0.0, "charging": False,
    "discharge_active": True, 
    "soh": 100.0,
    "soc_pack": 0.0,
    "soh_cell1": 100.0,
    "soh_cell2": 100.0,
    "soh_cell3": 100.0
}

try:
    soh_model = joblib.load('bms_soh_model.pkl')
    print("Sentinel-BMS Multiplexed Model active.")
except Exception as e:
    print(f"Warning: ML Model not found. Error: {e}")

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

    # State of Health & Charge Estimation Inference during active discharge
    if not data.charging and abs(data.current) > 0.5:
        try:
            # Call the predictive layout with individual data coordinates
            result = soh_model.predict(
                cell1_v=data.cell1,
                cell2_v=data.cell2,
                cell3_v=data.cell3,
                current=data.current,
                temp=data.temp
            )
            # 1. Individual SOH allocations
            latest_state["soh_cell1"] = result["soh_cell1"]
            latest_state["soh_cell2"] = result["soh_cell2"]
            latest_state["soh_cell3"] = result["soh_cell3"]
            
            # 2. SOH-weighted Pack SOC estimation
            latest_state["soc_pack"] = result["soc_pack"]
            
            # maps directly to the weakest link (pack SOH)
            latest_state["soh"] = result["soh_pack"]
            
        except Exception as e:
            print(f"Inference computation error: {e}")
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