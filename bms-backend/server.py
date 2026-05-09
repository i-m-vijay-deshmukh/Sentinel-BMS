from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import numpy as np

app = FastAPI()

# Allow React to fetch data without CORS errors
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the ML Model
try:
    soh_model = joblib.load('bms_soh_model.pkl')
    print("Sentinel ML Model loaded successfully.")
except:
    print("Warning: bms_soh_model.pkl not found. Run train_model.py first.")

# Define ESP32 JSON payload structure
class BMSData(BaseModel):
    cell1: float
    cell2: float
    cell3: float
    current: float
    temp: float
    charging: bool

# Global state memory
latest_state = {
    "cell1": 0.0, "cell2": 0.0, "cell3": 0.0,
    "current": 0.0, "temp": 0.0, "charging": False,
    "soh": 100.0 
}

@app.post("/api/esp32_push")
async def receive_esp32_data(data: BMSData):
    global latest_state
    
    # 1. Update live state
    latest_state["cell1"] = data.cell1
    latest_state["cell2"] = data.cell2
    latest_state["cell3"] = data.cell3
    latest_state["current"] = data.current
    latest_state["temp"] = data.temp
    latest_state["charging"] = data.charging

    # 2. ML SHIELD LOGIC
    # Only run health prediction during active discharge. 
    # Ignore during charging or idle to prevent false degradation readings.
    if not data.charging and abs(data.current) > 0.5:
        avg_voltage = (data.cell1 + data.cell2 + data.cell3) / 3.0
        features = np.array([[avg_voltage, abs(data.current), data.temp]])
        
        try:
            predicted_soh = soh_model.predict(features)[0]
            # Exponential Moving Average to smooth the SOH reading
            latest_state["soh"] = (latest_state["soh"] * 0.95) + (predicted_soh * 0.05)
        except Exception as e:
            pass # Model might not be loaded yet

    return {"status": "success", "message": "Telemetry received"}

@app.get("/api/react_pull")
async def serve_react_data():
    return latest_state

if __name__ == "__main__":
    import uvicorn
    # Runs the server on all network interfaces on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)