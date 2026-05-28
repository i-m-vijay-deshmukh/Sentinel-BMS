#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h> 
#include <DHT.h>
#include <ArduinoJson.h>

// --- NETWORK ---
const char* ssid = "Gaurav";
const char* password = "123456789";
const char* target_ip = "https://sentinel-bms.onrender.com/api/esp32_push";

// --- PINS ---
#define PIN_V1      34
#define PIN_V12     35
#define PIN_V123    32
#define PIN_CURRENT 33
#define PIN_DHT     4
#define PIN_BAL_1   27
#define PIN_BAL_2   26
#define PIN_BAL_3   25
#define PIN_CHG_FET 18
#define PIN_DIS_FET 19 // Used as Motor Control Switch

#define DHTTYPE DHT22

// --- CALIBRATION ---
const float CAL1 = 5.90;
const float CAL2 = 5.43;   
const float CAL3 = 5.23;   

// ACS712 CALIBRATION (const removed so it can be updated during auto-calibration)
float ACS_ZERO_VOLTAGE = 2.4; 
const float ACS_SENSITIVITY = 0.16; // 0.25 Volts per Ampere

// --- BMS SETTINGS ---
const float MAX_CELL_V = 4.25;
const float MIN_CELL_V = 3.00;
const float BAL_THRESHOLD = 4.10;
const float CHARGE_DETECT_AMPS = -0.15;
const float MAX_DISCHARGE_AMPS = 15.0; 

DHT dht(PIN_DHT, DHTTYPE);

// --- STATE VARIABLES ---
unsigned long lastNetworkUpdate = 0;
unsigned long lastHardwareCheck = 0;
unsigned long lastCalibrationTime = 0; // Added for current sensor calibration
bool motor_manual_off = false;    // Local Serial override
bool server_motor_enabled = true; // Server command state

// Averaging variables
float sum_c1 = 0, sum_c2 = 0, sum_c3 = 0, sum_amps = 0, sum_temp = 0;
int read_count = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("Sentinel-BMS: Ready");
  Serial.println("Commands: Type 'MOTOR_ON' or 'MOTOR_OFF' in Serial Monitor");

  dht.begin();
  analogSetAttenuation(ADC_11db);

  pinMode(PIN_CHG_FET, OUTPUT);
  pinMode(PIN_DIS_FET, OUTPUT);
  pinMode(PIN_BAL_1, OUTPUT);
  pinMode(PIN_BAL_2, OUTPUT);
  pinMode(PIN_BAL_3, OUTPUT);

  secureUnusedPins();
  connectWiFi();
}

void loop() {
  // 1. SERIAL COMMAND LISTENER (Local Override)
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim(); 
    if (cmd == "MOTOR_ON") {
      motor_manual_off = false;
      Serial.println(">>> SERIAL COMMAND: Motor Local Override Lifted (Yielding to Server)");
    } else if (cmd == "MOTOR_OFF") {
      motor_manual_off = true;
      Serial.println(">>> SERIAL COMMAND: Motor Disabled (Local Manual Cut)");
    }
  }

  // 2. AUTO-RECONNECT LOGIC
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
  }

  // 3. HARDWARE PROTECTION LOOP (100ms)
  if (millis() - lastHardwareCheck >= 100) {
    lastHardwareCheck = millis();

    // Analog Conversions
    float v1_raw = (analogRead(PIN_V1) / 4095.0) * 3.3 * CAL1;
    float v12_raw = (analogRead(PIN_V12) / 4095.0) * 3.3 * CAL2;
    float v123_raw = (analogRead(PIN_V123) / 4095.0) * 3.3 * CAL3;

    float cell1 = v1_raw;
    float cell2 = v12_raw - v1_raw;
    float cell3 = v123_raw - v12_raw;

    // --- ACS712 CURRENT READING LOGIC ---
    long rawADCValue = 0;
    int numSamples = 10;
    
    for (int i = 0; i < numSamples; i++) {
      rawADCValue += analogRead(PIN_CURRENT);
      delayMicroseconds(500); 
    }
    
    float averageADC = rawADCValue / (float)numSamples;
    float signalVoltage = (averageADC / 4095.0) * 3.3;
    float current = (signalVoltage - ACS_ZERO_VOLTAGE) / ACS_SENSITIVITY;

    // DEBUG FILTER
    if (current > -0.100 && current < 0.100) {
      current = 0.0;
    }
    // ------------------------------------------

    float temp = dht.readTemperature();
    if (isnan(temp)) temp = 25.0;

    sum_c1 += cell1; sum_c2 += cell2; sum_c3 += cell3;
    sum_amps += current; sum_temp += temp;
    read_count++;

    // --- SAFETY LOGIC ---
    bool ov_fault = (cell1 > MAX_CELL_V || cell2 > MAX_CELL_V || cell3 > MAX_CELL_V);
    bool uv_fault = (cell1 < MIN_CELL_V || cell2 < MIN_CELL_V || cell3 < MIN_CELL_V);
    bool oc_fault = (current > MAX_DISCHARGE_AMPS);

    // CHG FET logic - FORCED ALWAYS OFF
    digitalWrite(PIN_CHG_FET, LOW);
    
    // DIS/MOTOR FET logic with Manual AND Server Override
    bool motor_is_off = (uv_fault || oc_fault || motor_manual_off || !server_motor_enabled);
    if (motor_is_off) {
      digitalWrite(PIN_DIS_FET, LOW);
      
      // AUTO-CALIBRATE CURRENT SENSOR WHEN MOTOR IS OFF (Every 2 seconds)
      if (millis() - lastCalibrationTime >= 2000) {
        lastCalibrationTime = millis();
        ACS_ZERO_VOLTAGE = signalVoltage; // Re-zero the sensor
      }
    } else {
      digitalWrite(PIN_DIS_FET, HIGH);
    }

    // Balancing
    bool is_charging = (current < CHARGE_DETECT_AMPS);
    float max_v = max(cell1, max(cell2, cell3));
    if (is_charging && !ov_fault) {
      digitalWrite(PIN_BAL_1, (cell1 > BAL_THRESHOLD && cell1 >= max_v - 0.01));
      digitalWrite(PIN_BAL_2, (cell2 > BAL_THRESHOLD && cell2 >= max_v - 0.01));
      digitalWrite(PIN_BAL_3, (cell3 > BAL_THRESHOLD && cell3 >= max_v - 0.01));
    } else {
      digitalWrite(PIN_BAL_1, LOW); digitalWrite(PIN_BAL_2, LOW); digitalWrite(PIN_BAL_3, LOW);
    }
  }

  // 4. NETWORK & SERIAL LOGGING (2000ms)
  if (millis() - lastNetworkUpdate >= 2000) {
    lastNetworkUpdate = millis();
    if (read_count > 0) {
      float ac1 = sum_c1 / read_count;
      float ac2 = sum_c2 / read_count;
      float ac3 = sum_c3 / read_count;
      float aa = sum_amps / read_count;
      float at = sum_temp / read_count;

      Serial.println("\n--- BMS TELEMETRY ---");
      Serial.printf("CELLS: %.3fV | %.3fV | %.3fV\n", ac1, ac2, ac3);
      Serial.printf("TEMP: %.1fC | CURRENT: %.2fA\n", at, aa);
      
      // Detailed motor status for debugging
      Serial.print("MOTOR STATUS: ");
      if (motor_manual_off) {
        Serial.println("OFF (LOCAL SERIAL CUT)");
      } else if (!server_motor_enabled) {
        Serial.println("OFF (SERVER COMMAND)");
      } else {
        Serial.println("ON / AUTO");
      }
      Serial.println("---------------------");

      // Pass "false" for charging as it is permanently off
      sendData(ac1, ac2, ac3, aa, at, false);

      sum_c1 = 0; sum_c2 = 0; sum_c3 = 0; sum_amps = 0; sum_temp = 0;
      read_count = 0;
    }
  }
}

void sendData(float c1, float c2, float c3, float amps, float temp, bool charging) {
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClientSecure *client = new WiFiClientSecure;
    if (client) {
      client->setInsecure();
      HTTPClient http;
      http.begin(*client, target_ip);
      http.addHeader("Content-Type", "application/json");
      String json = "{\"cell1\":" + String(c1, 3) + ",\"cell2\":" + String(c2, 3) + ",\"cell3\":" + String(c3, 3) + 
                    ",\"current\":" + String(amps, 3) + ",\"temp\":" + String(temp, 1) + ",\"charging\":" + (charging ? "true" : "false") + "}";
      
      int code = http.POST(json);
      Serial.print("Cloud Push Code: "); Serial.println(code);

      // --- PARSE SERVER RESPONSE ---
      if (code == 200) {
        String response = http.getString();
        
        // Use ArduinoJson to safely parse the incoming JSON
        StaticJsonDocument<256> doc;
        DeserializationError error = deserializeJson(doc, response);
        
        if (!error) {
          if (doc.containsKey("discharge_enabled")) {
            server_motor_enabled = doc["discharge_enabled"];
          }
        } else {
          Serial.print("JSON Parse Error: ");
          Serial.println(error.c_str());
        }
      }

      http.end();
      delete client;
    }
  }
}

void connectWiFi() {
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nConnected!");
}

void secureUnusedPins() {
  int pins[] = {13, 14, 16, 17, 21, 22, 23};
  for (int i = 0; i < 7; i++) {
    pinMode(pins[i], OUTPUT); digitalWrite(pins[i], LOW);
  }
}