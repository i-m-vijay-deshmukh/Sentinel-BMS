# Sentinel-BMS Pro: ML-Powered Battery Management System

A professional-grade, edge-monitored Battery Management System (BMS) featuring an ESP32 hardware client, a Python/FastAPI Machine Learning middleware, and a real-time React/Vite cockpit dashboard. 

Currently optimized for **3-cell series (3S) Lithium-Ion packs (e.g., 11.1V, 5000mAh)**, featuring a blended SOC (State of Charge) algorithm, dynamic thermal fault detection, and ML-driven State of Health (SOH) predictions.

---

## 📋 System Architecture
1. **ESP32 Hardware Node:** Reads 16-bit analog voltages, current, and temperature at 100ms intervals. Triggers hardware safety cut-offs and pushes averaged telemetry over WiFi every 2 seconds.
2. **Python Middleware (FastAPI):** Receives telemetry, buffers data, and runs a Random Forest Machine Learning model to predict battery degradation (SOH) based on discharge voltage sag.
3. **React Cockpit Dashboard:** A glassmorphic UI that fetches data from the Python server, calculates blended SOC and remaining runtime, and triggers dynamic safety alerts.

---

## 🛠️ Prerequisites
Before installing, ensure you have the following installed on your computer:
*   **Node.js** (v18+ recommended)
*   **Python** (v3.9+ recommended)
*   **Arduino IDE** (for flashing the ESP32)

---

## 🚀 Step-by-Step Installation

### Step 1: Python ML Middleware Setup
This server acts as the brain, running the Machine Learning predictions and bridging the ESP32 to the React frontend.

1. Open a terminal and create the backend directory:
   ```bash
   mkdir bms-backend
   cd bms-backend
   ```
2. Install the required Python dependencies:
   ```bash
   pip install fastapi uvicorn scikit-learn pandas numpy joblib pydantic
   
```
3. Place `server.py` and `train_model.py` in this folder.
4. **Generate the ML Model:** Run the training script *once* to generate the synthetic degradation profile for the 3S pack.
   ```bash
   python train_model.py
   
```
   *(You should see a `bms_soh_model.pkl` file appear in the folder).*

### Step 2: React Frontend Setup
This is the visual dashboard. We use Vite for a lightning-fast development environment.

1. Open a new terminal and initialize the Vite project:
   ```bash
   npm create vite@latest sentinel-bms-ui -- --template react
   cd sentinel-bms-ui
   ```
2. Install the core dependencies (Tailwind, Recharts, Lucide Icons):
   ```bash
   npm install
   npm install -D tailwindcss postcss autoprefixer
   npx tailwindcss init -p
   npm install recharts lucide-react
   
```
3. Configure `tailwind.config.js` to include standard React paths:
   ```javascript
   export default {
     content: [
       "./index.html",
       "./src/**/*.{js,ts,jsx,tsx}",
     ],
     theme: { extend: {} },
     plugins: [],
   }
   
```
4. Place the `BMSDashboard.jsx` file inside the `src/components/` directory and render it inside your `App.jsx`.

### Step 3: ESP32 Hardware Setup
1. Open the Arduino IDE.
2. Ensure you have the **ESP32 Board Manager** installed.
3. Go to **Sketch > Include Library > Manage Libraries** and install:
   * `DHT sensor library` (by Adafruit)
4. Flash your C++ code to the ESP32.

---

## ⚠️ CRITICAL: What You Must Change Before Running

Because this system runs across your local WiFi network, **you must update the IP addresses** so the devices can talk to each other. "Localhost" will not work across different devices!

1. **Find your computer's IPv4 Address** 
   * *Windows:* Open Command Prompt and type `ipconfig`.
   * *Mac/Linux:* Open Terminal and type `ifconfig`.
   * *(Example: `192.168.1.50`)*

2. **Update the ESP32 Code (C++)**
   Change the target IP to point to your computer running the Python server:
   ```cpp
   const char* target_ip = "[http://192.168.1.50:8000/api/esp32_push](http://192.168.1.50:8000/api/esp32_push)";
   
```

3. **Update the React Dashboard (`BMSDashboard.jsx`)**
   Change the fetch URL to point to your computer running the Python server:
   ```javascript
   const response = await fetch('[http://192.168.1.50:8000/api/react_pull](http://192.168.1.50:8000/api/react_pull)');
   
```

4. **Calibrate the ESP32 Hardware**
   Use a reliable multimeter to measure the actual voltage of each cell. Update the `CAL1`, `CAL2`, and `CAL3` multipliers at the top of your ESP32 code until the Serial Monitor output matches your multimeter exactly.

---

## 🏁 Final Commands to Run the System

Whenever you want to start the Sentinel-BMS Pro system, follow this exact sequence:

**1. Start the Python Middleware**
*(In your `bms-backend` terminal)*
```bash
python server.py
```
*Expected Output: "Uvicorn running on http://0.0.0.0:8000"*

**2. Start the React Frontend**
*(In your `sentinel-bms-ui` terminal)*
```bash
npm run dev
```
*Expected Output: A local network link (e.g., http://localhost:5173)*

**3. Power the Hardware**
Turn on your ESP32. Once it connects to WiFi, it will automatically begin pushing telemetry to the Python server, which will instantly reflect on your live dashboard.