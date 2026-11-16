# Smart Daylight Harvesting System for Sustainable Buildings

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: ESP32](https://img.shields.io/badge/Platform-ESP32-red.svg)](https://www.espressif.com/)
[![Framework: Arduino / FastAPI](https://img.shields.io/badge/Stack-C%2B%2B%20%7C%20FastAPI%20%7C%20WebSockets-green.svg)](https://fastapi.tiangolo.com/)
[![Build: Tests Passed](https://img.shields.io/badge/Tests-4%2F4%20Passing-brightgreen.svg)]()

An intelligent, sensor-driven daylight harvesting lighting management system designed to significantly reduce electricity consumption in commercial and residential buildings by dynamically utilizing natural sunlight.

---

## 📌 Table of Contents
1. [Project Overview](#-project-overview)
2. [Working Principle & Control Mathematics](#-working-principle--control-mathematics)
3. [System Architecture](#-system-architecture)
4. [Hardware Design & Bill of Materials](#-hardware-design--bill-of-materials)
5. [Software Architecture & Features](#-software-architecture--features)
6. [Repository Structure](#-repository-structure)
7. [Getting Started & Installation](#-getting-started--installation)
8. [Telemetry Format & Serial Protocol](#-telemetry-format--serial-protocol)
9. [Automated Verification Tests](#-automated-verification-tests)
10. [Sustainability & Energy Impact](#-sustainability--energy-impact)

---

## 🌟 Project Overview

Artificial lighting accounts for up to **20–35% of total electrical energy** consumed in office and institutional buildings. In many buildings, artificial lights operate at full power even when ample natural sunlight floods the room through windows and skylights.

The **Smart Daylight Harvesting System** solves this inefficiency by:
- Continuously sensing incoming natural daylight using an ambient **LDR sensor** voltage divider.
- Processing light intensity with an **ESP32 microcontroller** using hardware oversampling and Exponential Moving Average (EMA) filtering to prevent noise and flickering.
- Adjusting the brightness of supplemental indoor LED luminaires via a **Logic-Level N-Channel MOSFET** driven by **5 kHz PWM** control.
- Streaming real-time telemetry over bidirectional USB serial to an interactive **Laptop Dashboard** that displays room illumination balance, real-time daylight vs. dimming charts, and live energy, financial, and $\text{CO}_2$ emissions savings.
- Providing a **Built-in Solar Daylight Simulator** so the entire system can be tested, demonstrated, and validated without requiring physical hardware connected.

---

## 🔬 Working Principle & Control Mathematics

### 1. Light Sensing & Filtering
An LDR sensor on `GPIO 34` (ESP32 ADC1) measures ambient daylight. To prevent flickering from shadows or electrical noise, the firmware samples the ADC 16 times per cycle and applies an Exponential Moving Average (EMA):

$$\bar{ADC}_{k} = \alpha \cdot ADC_{raw} + (1 - \alpha) \cdot \bar{ADC}_{k-1} \quad (\alpha = 0.20)$$

The filtered ADC is mapped to estimated illuminance:
$$\text{Lux} = \text{constrain}\left(\frac{\bar{ADC} - ADC_{dark}}{ADC_{bright} - ADC_{dark}} \times 1000, 0, 1000\right)$$

### 2. Closed-Loop Daylight Harvesting
Given a target indoor illuminance setpoint $L_{target}$ (default 500 lux for offices/classrooms) and deadband $\delta = 20\text{ lux}$:
- **Case 1: Natural sunlight is sufficient** ($\text{Lux} \ge L_{target} + \delta$):
  $$\text{PWM Duty} = 0 \quad (\text{LED completely OFF, 100\% energy saved})$$
- **Case 2: Natural light is deficient** ($\text{Lux} < L_{target}$):
  $$\text{Deficit} = L_{target} - \text{Lux}$$
  $$\text{PWM Duty} = \text{round}\left(\frac{\text{Deficit}}{L_{target}} \times 255\right)$$

### 3. Smooth PWM Ramping
To prevent jarring transitions for building occupants as clouds pass by, the PWM duty cycle ramps in small steps ($\pm 4$ steps per 50 ms cycle) ensuring smooth, natural daylight compensation.

---

## 🏗 System Architecture

```text
  +-------------------------------------------------------------+
  |                   NATURAL DAYLIGHT (SUN)                    |
  +-------------------------------------------------------------+
                               |
                               v
                       [ LDR Sensor ]
                               | (Analog Voltage: 0-3.3V)
                               v
  +-------------------------------------------------------------+
  |                     ESP32 MICROCONTROLLER                   |
  |  - ADC1 Channel 6 (GPIO 34) 16x Oversampling + EMA Filter   |
  |  - Proportional Closed-Loop Daylight Harvesting Logic        |
  |  - 5 kHz Hardware PWM Generator on GPIO 16                  |
  |  - Bidirectional JSON Telemetry on USB Serial (115200 baud) |
  +-------------------------------------------------------------+
                               |
                               v (5 kHz PWM Signal)
                     [ N-Channel MOSFET ]
                 (IRLZ44N / FQP30N06L / RFP30N06LE)
                               |
                               v (Low-Side PWM Dimming)
  +-------------------------------------------------------------+
  |                  12V LED FIXTURE / STRIP                    |
  |          (Supplies only supplemental illumination)          |
  +-------------------------------------------------------------+
                               ^
                               | USB Serial (115200 baud)
                               v
  +-------------------------------------------------------------+
  |             LAPTOP MONITORING & CONTROL DASHBOARD           |
  |  - Python FastAPI Backend + Real-time WebSockets (2 Hz)     |
  |  - Interactive Room Illumination SVG Visualizer             |
  |  - Real-Time Dual-Axis Canvas Chart (Daylight vs. LED PWM)  |
  |  - Live Energy, Cost (INR), and CO2 Emissions Calculator    |
  |  - Built-in Solar Simulator (Sunny, Cloudy, Night, 24h)     |
  |  - Automatic CSV Telemetry Logging & One-Click Export       |
  +-------------------------------------------------------------+
```

---

## 🔌 Hardware Design & Bill of Materials

### Circuit Wiring Schematic
```text
              +12V External Power Supply
                         |
                         +-----------------------+
                                                 |
                                            [+] LED Load (12V)
                                            [-]
                                                 |
                                                 | Drain (D)
   ESP32 Dev Module                        +-----+-----+
   +-------------------+                   |  MOSFET   |
   |                   |    220 ohm        | (IRLZ44N) |
   |           GPIO 16 |---[ R_gate ]------| Gate (G)  |
   |                   |       |           |           |
   |                   |    [10k pull-down]| Source (S)|
   |                   |       |           +-----+-----+
   |               GND |-------+-----------------+
   |                   |                         |
   |              3.3V |-------+                 |
   |                   |       |                 |
   |                   |     [LDR]               |
   |                   |       |                 |
   |           GPIO 34 |-------+                 |
   |            (ADC1) |       |                 |
   |                   |     [10k]               |
   |                   |       |                 |
   |               GND |-------+-----------------+
   +-------------------+                         |
                                                 |
                                         GND (Common Ground)
                                                 |
                                    (-) 12V Power Supply GND
```

See [hardware/WIRING_AND_SCHEMATIC.md](hardware/WIRING_AND_SCHEMATIC.md) and [hardware/BOM.md](hardware/BOM.md) for complete pin tables, component datasheets, and step-by-step assembly guides.

---

## 💻 Software Architecture & Features

1. **ESP32 Firmware (`firmware/smart_daylight_harvesting/`):**
   - Written in C++ for the Arduino framework.
   - Compatible with ESP32 core v2.x and v3.x (`ledcAttach` / `ledcSetup`).
   - 115200 baud JSON telemetry emitted every 500 ms.
2. **Backend Engine (`backend/`):**
   - FastAPI REST API + WebSockets.
   - Thread-safe serial communication with auto-reconnection and descriptive error messaging.
   - Live energy analytics calculating:
     - Instantaneous power saved ($W$)
     - Cumulative energy saved ($Wh$)
     - Avoided $\text{CO}_2$ emissions ($0.82\text{ g } \text{CO}_2/\text{Wh}$)
     - Financial savings based on customizable electricity tariffs.
3. **Frontend Dashboard (`frontend/` & `Smart-Daylight-Dashboard.html`):**
   - Modern, zero-dependency dark UI with responsive grid.
   - Live SVG cross-section of a room illustrating sunlight beams and LED cones dynamically responding to ambient conditions.
   - Real-time dual-axis HTML5 canvas graph (Daylight lux vs. LED brightness % vs. target setpoint).
   - One-click CSV export and session statistics reset.

---

## 📁 Repository Structure

```text
Smart-Daylight-Harvesting/
├── firmware/
│   └── smart_daylight_harvesting/
│       └── smart_daylight_harvesting.ino   # ESP32 C++ firmware (LDR + 5kHz PWM + Serial telemetry)
├── hardware/
│   ├── WIRING_AND_SCHEMATIC.md             # Detailed circuit schematics and pinout tables
│   ├── BOM.md                              # Complete Bill of Materials and component specs
│   └── CALIBRATION_GUIDE.md                # LDR dark/bright calibration procedures
├── backend/
│   ├── __init__.py
│   ├── daylight_controller.py              # Closed-loop engine, Serial driver, Simulator & CO2 analytics
│   └── server.py                           # FastAPI REST & WebSocket streaming server
├── frontend/
│   ├── index.html                          # Laptop dashboard UI
│   ├── styles.css                          # Modern sustainable-energy dark theme
│   └── app.js                              # Real-time WebSocket sync, Room SVG, dual-axis Canvas chart
├── tests/
│   └── test_daylight.py                    # Automated test suite (dimming, manual mode, reset)
├── data/
│   └── telemetry_log.csv                   # Sample / logged telemetry dataset
├── Smart-Daylight-Dashboard.html           # Standalone zero-install single-file dashboard
├── requirements.txt                        # Python dependencies (fastapi, uvicorn, pyserial)
├── run_dashboard.bat                       # One-click Windows desktop launcher
└── README.md                               # Project documentation
```

---

## 🚀 Getting Started & Installation

### Option 1: Standalone Dashboard (Instant, Zero Install)
Double-click `Smart-Daylight-Dashboard.html` to open it in any web browser. It runs a full client-side solar simulator with interactive controls and charts without requiring any Python or backend server.

### Option 2: Full Server & ESP32 Hardware Integration

#### 1. Clone the Repository
```bash
git clone https://github.com/KawinKumarS/Smart-Daylight-Harvesting.git
cd Smart-Daylight-Harvesting
```

#### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 3. Flash the ESP32
1. Open `firmware/smart_daylight_harvesting/smart_daylight_harvesting.ino` in Arduino IDE.
2. Select **ESP32 Dev Module** and your USB COM port.
3. Upload the sketch. *(Remember to close the Arduino Serial Monitor once flashed so the COM port is free for the dashboard).*

#### 4. Run the Dashboard
- On Windows: Double-click `run_dashboard.bat`, or
- Run via terminal:
  ```bash
  python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000
  ```
- Open `http://127.0.0.1:8000/` in your browser.
- Select your ESP32's COM port from the dropdown and click **Connect**.

---

## 📊 Telemetry Format & Serial Protocol

### Telemetry Packet (ESP32 $\rightarrow$ Laptop, 2 Hz)
```json
{
  "adc": 2450,
  "lux": 582.3,
  "daylight_pct": 58.2,
  "led_pwm": 0,
  "led_pct": 0.0,
  "target_lux": 500.0,
  "mode": "AUTO",
  "power_w": 0.00,
  "saved_w": 12.00,
  "uptime_s": 142
}
```

### Serial Control Commands (Laptop $\rightarrow$ ESP32)
| Command | Description |
| :--- | :--- |
| `MODE:AUTO` | Activates autonomous closed-loop daylight harvesting |
| `MODE:MANUAL` | Overrides automatic control with manual brightness |
| `SET_TARGET:<lux>` | Updates indoor target illuminance (e.g. `SET_TARGET:500`) |
| `SET_PCT:<%>` | Sets manual LED brightness percentage (0–100%) |
| `SET_PWM:<duty>` | Sets raw PWM duty cycle (0–255) |
| `CALIBRATE:<dark>,<bright>` | Updates dark and bright ADC calibration bounds |

---

## 🧪 Automated Verification Tests

A unit test suite verifies closed-loop dimming behavior, dark-room compensation, manual overrides, and energy statistic resets:

```bash
python -m unittest discover -s tests -v
```
All tests execute against the daylight harvesting engine with verified assertions.

---

## 🌍 Sustainability & Energy Impact

By supplying only the supplemental artificial light missing from incoming daylight:
* **Sunny Midday (Daylight $\ge 500$ lux):** Artificial lights dim to **0%**, saving **100% of lighting energy**.
* **Overcast / Cloudy ($150–350$ lux):** Artificial lights operate at **30–70%**, maintaining target comfort while saving **30–70% of energy**.
* **Night / Blinds Closed (< 40 lux):** Artificial lights supply **100%** illumination to maintain visual task comfort.

For a commercial floor with 50 fixtures (20W each operating 10 hours daily), daylight harvesting typically saves **40–60% of daily lighting electricity**, translating to significant reductions in utility bills and carbon footprints.

---

## 📜 License
This project is open-source under the [MIT License](LICENSE).
