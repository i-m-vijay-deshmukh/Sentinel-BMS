#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h> // REQUIRED for Render HTTPS
#include <DHT.h>

// --- NETWORK ---
const char* ssid = "Vijay";
const char* password = "123456789";

// IMPORTANT: Change this to your Render URL when deploying to the cloud
// If testing locally, keep it as "http://YOUR_IPV4:8000/api/esp32_push"
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
#define PIN_DIS_FET 19

#define DHTTYPE DHT22

// --- CALIBRATION ---
const float CAL1 = 5.25;   
const float CAL2 = 5.02;   
const float CAL3 = 4.91;   

int ACS_NULL_VALUE = 2967;   
const float ACS_SENSITIVITY = 0.074;

// --- BMS SETTINGS ---
const float MAX_CELL_V = 4.25;
const float MIN_CELL_V = 3.00;
const float BAL_THRESHOLD = 4.10;
const float CHARGE_DETECT_AMPS = -0.15;
const float MAX_DISCHARGE_AMPS = 15.0; // Overcurrent limit

bool calibration_mode = false;  

DHT dht(PIN_DHT, DHTTYPE);

// --- TIMING VARIABLES ---
unsigned long lastNetworkUpdate = 0;
unsigned long lastHardwareCheck = 0;

// Averaging variables
float sum_c1 = 0, sum_c2 = 0, sum_c3 = 0, sum_amps = 0, sum_temp = 0;
int read_count = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting Sentinel ESP32 BMS PRO...");
  dht.begin();
  analogSetAttenuation(ADC_11db);

  pinMode(PIN_CHG_FET, OUTPUT);
  pinMode(PIN_DIS_FET, OUTPUT);
  pinMode(PIN_BAL_1, OUTPUT);
  pinMode(PIN_BAL_2, OUTPUT);
  pinMode(PIN_BAL_3, OUTPUT);

  secureUnusedPins();

  // Initial WiFi Connection
  connectWiFi();
}

void loop() {
  // 1. AUTO-RECONNECT LOGIC
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected! Attempting reconnect...");
    WiFi.disconnect();
    WiFi.reconnect();
    unsigned long startAttempt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 2000) {
      delay(50); // Keep delay short so we don't block hardware checks entirely
    }
  }

  // 2. HARDWARE PROTECTION LOOP (Runs every 100ms)
  if (millis() - lastHardwareCheck >= 100) {
    lastHardwareCheck = millis();

    // Read Voltages
    float v1_raw = (analogRead(PIN_V1) / 4095.0) * 3.3 * CAL1;
    float v12_raw = (analogRead(PIN_V12) / 4095.0) * 3.3 * CAL2;
    float v123_raw = (analogRead(PIN_V123) / 4095.0) * 3.3 * CAL3;

    float cell1 = v1_raw;
    float cell2 = v12_raw - v1_raw;
    float cell3 = v123_raw - v12_raw;

    // Read Current
    float v_adc = (analogRead(PIN_CURRENT) / 4095.0) * 3.3;
    float offset_v = (ACS_NULL_VALUE / 4095.0) * 3.3;
    float current = (v_adc - offset_v) / ACS_SENSITIVITY * -1.0;

    // Read Temp
    float temp = dht.readTemperature();
    if (isnan(temp)) temp = 25.0; // Fallback

    // Add to running totals for network averaging
    sum_c1 += cell1;
    sum_c2 += cell2;
    sum_c3 += cell3;
    sum_amps += current;
    sum_temp += temp;
    read_count++;

    // --- INSTANT HARDWARE PROTECTION ---
    bool ov_fault = (cell1 > MAX_CELL_V || cell2 > MAX_CELL_V || cell3 > MAX_CELL_V);
    bool uv_fault = (cell1 < MIN_CELL_V || cell2 < MIN_CELL_V || cell3 < MIN_CELL_V);
    bool oc_fault = (current > MAX_DISCHARGE_AMPS);

    digitalWrite(PIN_CHG_FET, ov_fault ? LOW : HIGH);
    digitalWrite(PIN_DIS_FET, (uv_fault || oc_fault) ? LOW : HIGH);

    // --- PASSIVE BALANCING ---
    bool is_charging = (current < CHARGE_DETECT_AMPS);
    float max_v = max(cell1, max(cell2, cell3));

    if (is_charging && !ov_fault) {
      digitalWrite(PIN_BAL_1, (cell1 > BAL_THRESHOLD && cell1 >= max_v - 0.01));
      digitalWrite(PIN_BAL_2, (cell2 > BAL_THRESHOLD && cell2 >= max_v - 0.01));
      digitalWrite(PIN_BAL_3, (cell3 > BAL_THRESHOLD && cell3 >= max_v - 0.01));
    } else {
      digitalWrite(PIN_BAL_1, LOW);
      digitalWrite(PIN_BAL_2, LOW);
      digitalWrite(PIN_BAL_3, LOW);
    }
  }

  // 3. NETWORK DATA PUSH (Runs every 2000ms)
  if (millis() - lastNetworkUpdate >= 2000) {
    lastNetworkUpdate = millis();

    // Calculate averages to filter out motor noise
    if (read_count > 0) {
      float avg_c1 = sum_c1 / read_count;
      float avg_c2 = sum_c2 / read_count;
      float avg_c3 = sum_c3 / read_count;
      float avg_amps = sum_amps / read_count;
      float avg_temp = sum_temp / read_count;
      bool charging_status = (avg_amps < CHARGE_DETECT_AMPS);

      // Reset counters
      sum_c1 = 0; sum_c2 = 0; sum_c3 = 0; sum_amps = 0; sum_temp = 0;
      read_count = 0;

      // Send to Render via HTTPS
      sendData(avg_c1, avg_c2, avg_c3, avg_amps, avg_temp, charging_status);
    }
  }
}

// --- SECURE HTTPS PUSH LOGIC ---
void sendData(float c1, float c2, float c3, float amps, float temp, bool charging) {
  if (WiFi.status() == WL_CONNECTED) {
    
    // Create an insecure client to bypass strict SSL validation (required for ESP32 -> Render)
    WiFiClientSecure *client = new WiFiClientSecure;
    if (client) {
      client->setInsecure(); 

      HTTPClient http;
      // Initialize connection using the secure client
      http.begin(*client, target_ip); 
      http.addHeader("Content-Type", "application/json");

      String json = "{";
      json += "\"cell1\":" + String(c1, 3) + ",";
      json += "\"cell2\":" + String(c2, 3) + ",";
      json += "\"cell3\":" + String(c3, 3) + ",";
      json += "\"current\":" + String(amps, 3) + ",";
      json += "\"temp\":" + String(temp, 1) + ",";
      json += "\"charging\":" + String(charging ? "true" : "false");
      json += "}";

      Serial.println("Pushing telemetry to cloud...");
      int code = http.POST(json);

      if (code > 0) {
        Serial.print("HTTP Success: "); Serial.println(code);
      } else {
        Serial.print("HTTP Error: "); Serial.println(http.errorToString(code).c_str());
      }

      http.end();
      delete client; // MUST delete to prevent memory leak
    }
  }
}

void connectWiFi() {
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  int timeout = 0;
  while (WiFi.status() != WL_CONNECTED && timeout < 20) {
    delay(500);
    Serial.print(".");
    timeout++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected!");
  } else {
    Serial.println("\nWiFi Failed.");
  }
}

void secureUnusedPins() {
  int pins[] = {13, 14, 16, 17, 21, 22, 23};
  for (int i = 0; i < 7; i++) {
    pinMode(pins[i], OUTPUT);
    digitalWrite(pins[i], LOW);
  }
}