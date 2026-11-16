# LDR Sensor Calibration Guide

The system maps the 12-bit ADC reading (`0` to `4095`) from the LDR voltage divider on `GPIO 34` into an estimated illuminance reading (`0` to `1000 lux`).

Because individual LDR sensors and room window orientations vary, simple two-point calibration ensures optimal accuracy.

---

## 1. Finding Your Dark & Bright Calibration Values

1. Flash the firmware `smart_daylight_harvesting.ino` onto your ESP32.
2. Open the **Laptop Dashboard** at `http://127.0.0.1:8000/` or open the **Arduino Serial Monitor** (115200 baud).

### Dark Point Calibration (Night / Blinds Closed):
- Cover the LDR completely with an opaque object or a finger.
- Observe the reported `adc` value in the telemetry packet:
  ```json
  {"adc": 240, "lux": 0.0, ...}
  ```
- Note down this value (e.g. `240` - `280`). This is your `adcDarkThreshold`.

### Bright Daylight Calibration (Midday Sun / Torch):
- Expose the LDR to direct incoming daylight near the window (or shine a bright smartphone torch directly at it).
- Observe the reported `adc` value:
  ```json
  {"adc": 3820, "lux": 1000.0, ...}
  ```
- Note down this value (e.g. `3700` - `3950`). This is your `adcBrightThreshold`.

---

## 2. Applying Calibration

### Method A: Via the Laptop Dashboard
Send the calibration command directly over the serial interface from the laptop console or API:
```text
CALIBRATE:<dark_adc>,<bright_adc>
```
*Example:* `CALIBRATE:240,3850`

### Method B: Directly in the Firmware
Open `firmware/smart_daylight_harvesting/smart_daylight_harvesting.ino` and update lines 32–33:
```cpp
int adcDarkThreshold   = 240;   // ADC reading in completely dark room (~0 lux)
int adcBrightThreshold = 3850;  // ADC reading in bright sunlight (~1000 lux)
```
Then re-upload the sketch to the ESP32.
