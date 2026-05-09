#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// --- NETWORK ---
const char* ssid = "Vijay";
const char* password = "123456789";
const char* target_ip = "http://192.168.1.100/api/bms_data";

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
const float CAL1 = 5.25;   // derived from your measurements
const float CAL2 = 5.02;   // derived from your measurements
const float CAL3 = 4.91;   // derived from your measurements

int ACS_NULL_VALUE = 2967;   // Updated from calibration
const float ACS_SENSITIVITY = 0.074;

// --- BMS SETTINGS ---
const float MAX_CELL_V = 4.25;
const float MIN_CELL_V = 3.00;
const float BAL_THRESHOLD = 4.10;
const float CHARGE_DETECT_AMPS = -0.15;

// --- MODES ---
bool calibration_mode = false;  // 🔥 SET FALSE AFTER CALIBRATION

DHT dht(PIN_DHT, DHTTYPE);
unsigned long lastUpdate = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting ESP32 BMS...");
  
  dht.begin();

  analogSetAttenuation(ADC_11db); // IMPORTANT

  pinMode(PIN_CHG_FET, OUTPUT);
  pinMode(PIN_DIS_FET, OUTPUT);

  pinMode(PIN_BAL_1, OUTPUT);
  pinMode(PIN_BAL_2, OUTPUT);
  pinMode(PIN_BAL_3, OUTPUT);

  secureUnusedPins();

  // --- WIFI ---
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");

  int timeout = 0;
  while (WiFi.status() != WL_CONNECTED && timeout < 20) {
    delay(500);
    Serial.print(".");
    timeout++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi Failed");
  }
}

void loop() {

  // --- CURRENT SENSOR CALIBRATION ---
  if (calibration_mode) {
    Serial.println("\n=== CALIBRATION MODE ===");

    // Turn OFF everything
    digitalWrite(PIN_CHG_FET, LOW);
    digitalWrite(PIN_DIS_FET, LOW);
    digitalWrite(PIN_BAL_1, LOW);
    digitalWrite(PIN_BAL_2, LOW);
    digitalWrite(PIN_BAL_3, LOW);

    long sum = 0;
    for (int i = 0; i < 50; i++) {
      sum += analogRead(PIN_CURRENT);
      delay(10);
    }

    ACS_NULL_VALUE = sum / 50;

    Serial.print("Calibrated ACS Offset: ");
    Serial.println(ACS_NULL_VALUE);

    delay(3000);
    return;
  }

  // --- NORMAL OPERATION ---
  if (millis() - lastUpdate >= 2000) {
    lastUpdate = millis();

    // --- VOLTAGES ---
    float v1_raw = (analogRead(PIN_V1) / 4095.0) * 3.3 * CAL1;
    float v12_raw = (analogRead(PIN_V12) / 4095.0) * 3.3 * CAL2;
    float v123_raw = (analogRead(PIN_V123) / 4095.0) * 3.3 * CAL3;

    float cell1 = v1_raw;
    float cell2 = v12_raw - v1_raw;
    float cell3 = v123_raw - v12_raw;

    // --- CURRENT ---
    int adc = analogRead(PIN_CURRENT);
    float v_adc = (adc / 4095.0) * 3.3;
    float offset_v = (ACS_NULL_VALUE / 4095.0) * 3.3;

    float current = (v_adc - offset_v) / ACS_SENSITIVITY*-1.0;

    // --- TEMP ---
    float temp = dht.readTemperature();
    if (isnan(temp)) temp = -99;

    // --- PROTECTION ---
    bool ov_fault = (cell1 > MAX_CELL_V || cell2 > MAX_CELL_V || cell3 > MAX_CELL_V);
    bool uv_fault = (cell1 < MIN_CELL_V || cell2 < MIN_CELL_V || cell3 < MIN_CELL_V);

    digitalWrite(PIN_CHG_FET, ov_fault ? LOW : HIGH);
    digitalWrite(PIN_DIS_FET, uv_fault ? LOW : HIGH);

    // --- BALANCING ---
    bool is_charging = (current < CHARGE_DETECT_AMPS);
    float max_v = max(cell1, max(cell2, cell3));

    if (is_charging) {
      digitalWrite(PIN_BAL_1, (cell1 > BAL_THRESHOLD && cell1 >= max_v - 0.01));
      digitalWrite(PIN_BAL_2, (cell2 > BAL_THRESHOLD && cell2 >= max_v - 0.01));
      digitalWrite(PIN_BAL_3, (cell3 > BAL_THRESHOLD && cell3 >= max_v - 0.01));
    } else {
      digitalWrite(PIN_BAL_1, LOW);
      digitalWrite(PIN_BAL_2, LOW);
      digitalWrite(PIN_BAL_3, LOW);
    }

    // --- DEBUG ---
    Serial.println("\n===== BMS DATA =====");
    Serial.print("C1: "); Serial.println(cell1);
    Serial.print("C2: "); Serial.println(cell2);
    Serial.print("C3: "); Serial.println(cell3);
    Serial.print("Current: "); Serial.println(current);
    Serial.print("Temp: "); Serial.println(temp);
    Serial.print("Charging: "); Serial.println(is_charging);

    Serial.print("Bal1: "); Serial.println(digitalRead(PIN_BAL_1));
    Serial.print("Bal2: "); Serial.println(digitalRead(PIN_BAL_2));
    Serial.print("Bal3: "); Serial.println(digitalRead(PIN_BAL_3));

    // --- SEND DATA ---
    sendData(cell1, cell2, cell3, current, temp, is_charging);
  }
}

void sendData(float c1, float c2, float c3, float amps, float temp, bool charging) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(target_ip);
    http.addHeader("Content-Type", "application/json");

    String json = "{";
    json += "\"cell1\":" + String(c1, 3) + ",";
    json += "\"cell2\":" + String(c2, 3) + ",";
    json += "\"cell3\":" + String(c3, 3) + ",";
    json += "\"current\":" + String(amps, 3) + ",";
    json += "\"temp\":" + String(temp, 1) + ",";
    json += "\"charging\":" + String(charging ? "true" : "false");
    json += "}";

    Serial.println("Sending JSON:");
    Serial.println(json);

    int code = http.POST(json);

    Serial.print("HTTP Response: ");
    Serial.println(code);

    http.end();
  }
}

void secureUnusedPins() {
  int pins[] = {13, 14, 16, 17, 21, 22, 23};
  for (int i = 0; i < 7; i++) {
    pinMode(pins[i], OUTPUT);
    digitalWrite(pins[i], LOW);
  }
}