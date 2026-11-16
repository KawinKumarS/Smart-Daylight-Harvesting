/*
 * Smart Daylight Harvesting System for Sustainable Buildings
 * ESP32 Firmware (Arduino Framework)
 *
 * Features:
 *  - Reads ambient natural daylight via an LDR voltage divider on GPIO 34 (ADC1)
 *  - Applies oversampling + Exponential Moving Average (EMA) filtering to avoid flicker
 *  - Smooth closed-loop daylight harvesting control with deadband hysteresis
 *  - Drives an N-Channel MOSFET (e.g., IRLZ44N / FQP30N06L) via PWM on GPIO 16
 *  - Streams JSON telemetry over USB Serial (115200 baud) every 500 ms
 *  - Accepts real-time commands from the Laptop Dashboard over Serial
 *
 * Compatible with ESP32 Arduino Core v2.x and v3.x.
 */

#include <Arduino.h>

// ===================== PIN CONFIGURATION =====================
const int LDR_PIN        = 34;  // ADC1_CH6 (input-only pin, safe alongside Wi-Fi)
const int LED_PWM_PIN    = 16;  // PWM output to MOSFET Gate (via 220 ohm resistor)
const int STATUS_LED_PIN = 2;   // Built-in ESP32 LED (ON when in AUTO mode)

// ===================== PWM CONFIGURATION =====================
const int PWM_CHANNEL    = 0;     // Used for ESP32 Arduino Core v2.x
const int PWM_FREQ_HZ    = 5000;  // 5 kHz flicker-free LED dimming
const int PWM_RESOLUTION = 8;     // 8-bit resolution (0 - 255)
const int PWM_MAX        = 255;

// ===================== SENSOR CALIBRATION ====================
// Set LDR_INVERTED = false if wiring is: 3.3V -> LDR -> GPIO34 -> 10k Resistor -> GND
// (More light => lower LDR resistance => higher ADC voltage)
// Set LDR_INVERTED = true if wiring is:  3.3V -> 10k Resistor -> GPIO34 -> LDR -> GND
const bool LDR_INVERTED = false;

int adcDarkThreshold   = 250;   // ADC reading in dark room (~0 lux)
int adcBrightThreshold = 3800;  // ADC reading in bright sunlight (~1000 lux)
const float MAX_LUX_REF = 1000.0f;

// ===================== CONTROL PARAMETERS ====================
const float EMA_ALPHA         = 0.20f;   // Smoothing factor (0.05 = very slow, 0.5 = fast)
const int   ADC_SAMPLES       = 16;      // Oversampling per loop
const float DEADBAND_LUX      = 20.0f;   // Prevents hunting/oscillation around target
const int   PWM_RAMP_STEP     = 4;       // Max PWM change per control step (smooth fade)
const float RATED_FIXTURE_W   = 12.0f;   // Rated LED load power in Watts (for telemetry)

const unsigned long CONTROL_INTERVAL_MS   = 50;   // 20 Hz smooth PWM update
const unsigned long TELEMETRY_INTERVAL_MS = 500;  // 2 Hz JSON stream to laptop

// ===================== RUNTIME STATE =========================
enum ControlMode {
  MODE_AUTO = 0,
  MODE_MANUAL = 1
};

ControlMode currentMode = MODE_AUTO;
float targetLux         = 500.0f;  // Desired indoor illumination (office/classroom ~300-500 lux)
float filteredAdc       = 0.0f;
float estimatedLux      = 0.0f;
int   targetPwm         = 0;
int   currentPwm        = 0;

unsigned long lastControlMs   = 0;
unsigned long lastTelemetryMs = 0;
String serialBuffer = "";

// ===================== HELPER FUNCTIONS ======================

void setupPwm() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcAttach(LED_PWM_PIN, PWM_FREQ_HZ, PWM_RESOLUTION);
#else
  ledcSetup(PWM_CHANNEL, PWM_FREQ_HZ, PWM_RESOLUTION);
  ledcAttachPin(LED_PWM_PIN, PWM_CHANNEL);
#endif
}

void writePwm(int duty) {
  duty = constrain(duty, 0, PWM_MAX);
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcWrite(LED_PWM_PIN, duty);
#else
  ledcWrite(PWM_CHANNEL, duty);
#endif
}

int readOversampledAdc() {
  long sum = 0;
  for (int i = 0; i < ADC_SAMPLES; i++) {
    sum += analogRead(LDR_PIN);
    delayMicroseconds(150);
  }
  int raw = (int)(sum / ADC_SAMPLES);
  return LDR_INVERTED ? (4095 - raw) : raw;
}

float adcToLux(float adcVal) {
  float span = (float)(adcBrightThreshold - adcDarkThreshold);
  if (span <= 1.0f) span = 1.0f;
  float normalized = (adcVal - adcDarkThreshold) / span;
  normalized = constrain(normalized, 0.0f, 1.2f);
  return normalized * MAX_LUX_REF;
}

void updateControlLoop() {
  int rawAdc = readOversampledAdc();
  if (filteredAdc == 0.0f) {
    filteredAdc = (float)rawAdc;
  } else {
    filteredAdc = (EMA_ALPHA * rawAdc) + ((1.0f - EMA_ALPHA) * filteredAdc);
  }

  estimatedLux = adcToLux(filteredAdc);

  if (currentMode == MODE_AUTO) {
    digitalWrite(STATUS_LED_PIN, HIGH);

    // Compute artificial light deficit needed to reach targetLux
    float deficit = targetLux - estimatedLux;

    if (estimatedLux >= targetLux + DEADBAND_LUX) {
      // Natural sunlight alone is sufficient -> turn LED completely OFF
      targetPwm = 0;
    } else if (deficit <= 0.0f) {
      // Inside upper deadband -> gently hold or zero out
      if (targetPwm > 0 && estimatedLux > targetLux) {
        targetPwm = max(0, targetPwm - 1);
      }
    } else {
      // Proportional daylight harvesting: supply only the missing light
      float ratio = constrain(deficit / targetLux, 0.0f, 1.0f);
      targetPwm = (int)roundf(ratio * PWM_MAX);
    }
  } else {
    digitalWrite(STATUS_LED_PIN, LOW);
  }

  // Smooth ramping so LED brightness changes gradually without jarring jumps
  if (currentPwm < targetPwm) {
    currentPwm = min(targetPwm, currentPwm + PWM_RAMP_STEP);
  } else if (currentPwm > targetPwm) {
    currentPwm = max(targetPwm, currentPwm - PWM_RAMP_STEP);
  }

  writePwm(currentPwm);
}

void sendTelemetryJson() {
  float daylightPct = constrain((estimatedLux / MAX_LUX_REF) * 100.0f, 0.0f, 100.0f);
  float ledPct      = ((float)currentPwm / (float)PWM_MAX) * 100.0f;
  float powerW      = (ledPct / 100.0f) * RATED_FIXTURE_W;
  float savedW      = RATED_FIXTURE_W - powerW;

  Serial.print("{");
  Serial.print("\"adc\":");          Serial.print((int)roundf(filteredAdc));
  Serial.print(",\"lux\":");         Serial.print(estimatedLux, 1);
  Serial.print(",\"daylight_pct\":");Serial.print(daylightPct, 1);
  Serial.print(",\"led_pwm\":");     Serial.print(currentPwm);
  Serial.print(",\"led_pct\":");     Serial.print(ledPct, 1);
  Serial.print(",\"target_lux\":");  Serial.print(targetLux, 1);
  Serial.print(",\"mode\":\"");      Serial.print(currentMode == MODE_AUTO ? "AUTO" : "MANUAL");
  Serial.print("\",\"power_w\":");   Serial.print(powerW, 2);
  Serial.print(",\"saved_w\":");     Serial.print(savedW, 2);
  Serial.print(",\"uptime_s\":");    Serial.print(millis() / 1000UL);
  Serial.println("}");
}

void handleSerialCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.equalsIgnoreCase("MODE:AUTO")) {
    currentMode = MODE_AUTO;
    Serial.println("{\"ack\":\"MODE:AUTO\"}");
  } else if (cmd.equalsIgnoreCase("MODE:MANUAL")) {
    currentMode = MODE_MANUAL;
    Serial.println("{\"ack\":\"MODE:MANUAL\"}");
  } else if (cmd.startsWith("SET_PWM:")) {
    int val = cmd.substring(8).toInt();
    currentMode = MODE_MANUAL;
    targetPwm = constrain(val, 0, PWM_MAX);
    Serial.print("{\"ack\":\"SET_PWM\",\"value\":");
    Serial.print(targetPwm);
    Serial.println("}");
  } else if (cmd.startsWith("SET_PCT:")) {
    float pct = cmd.substring(8).toFloat();
    pct = constrain(pct, 0.0f, 100.0f);
    currentMode = MODE_MANUAL;
    targetPwm = (int)roundf((pct / 100.0f) * PWM_MAX);
    Serial.print("{\"ack\":\"SET_PCT\",\"value\":");
    Serial.print(pct, 1);
    Serial.println("}");
  } else if (cmd.startsWith("SET_TARGET:")) {
    float t = cmd.substring(11).toFloat();
    targetLux = constrain(t, 50.0f, 1000.0f);
    Serial.print("{\"ack\":\"SET_TARGET\",\"value\":");
    Serial.print(targetLux, 1);
    Serial.println("}");
  } else if (cmd.startsWith("CALIBRATE:")) {
    String args = cmd.substring(10);
    int commaIdx = args.indexOf(',');
    if (commaIdx > 0) {
      int minA = args.substring(0, commaIdx).toInt();
      int maxA = args.substring(commaIdx + 1).toInt();
      if (maxA > minA + 50) {
        adcDarkThreshold = constrain(minA, 0, 4000);
        adcBrightThreshold = constrain(maxA, adcDarkThreshold + 50, 4095);
        Serial.println("{\"ack\":\"CALIBRATE\"}");
      }
    }
  } else if (cmd.equalsIgnoreCase("STATUS")) {
    sendTelemetryJson();
  }
}

void pollSerialInput() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        handleSerialCommand(serialBuffer);
        serialBuffer = "";
      }
    } else if (serialBuffer.length() < 128) {
      serialBuffer += c;
    }
  }
}

// ===================== ARDUINO LIFECYCLE =====================

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);       // 0 - 4095
  analogSetAttenuation(ADC_11db); // Full 0 - 3.3V input range

  pinMode(STATUS_LED_PIN, OUTPUT);
  setupPwm();
  writePwm(0);

  delay(200);
  Serial.println("{\"event\":\"BOOT\",\"project\":\"Smart Daylight Harvesting System\"}");
}

void loop() {
  unsigned long now = millis();

  pollSerialInput();

  if (now - lastControlMs >= CONTROL_INTERVAL_MS) {
    lastControlMs = now;
    updateControlLoop();
  }

  if (now - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = now;
    sendTelemetryJson();
  }
}
