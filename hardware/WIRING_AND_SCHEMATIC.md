# Hardware Wiring & Circuit Schematics

## 1. System Architecture Overview

```text
  +-------------------------------------------------------------+
  |                   NATURAL DAYLIGHT (SUN)                    |
  +-------------------------------------------------------------+
                               |
                               v
                       [ LDR Sensor ]
                               |
                               v (Analog Voltage)
  +-------------------------------------------------------------+
  |                     ESP32 MICROCONTROLLER                   |
  |  - ADC1 Channel 6 (GPIO 34) with 16x Oversampling + EMA    |
  |  - Closed-Loop Proportional Daylight Harvesting Algorithm   |
  |  - 5 kHz PWM Generator on GPIO 16                          |
  |  - Bidirectional JSON Telemetry on USB Serial (115200)      |
  +-------------------------------------------------------------+
                               |
                               v (PWM Gate Drive)
                     [ N-Channel MOSFET ]
                 (IRLZ44N / FQP30N06L / RFP30N06LE)
                               |
                               v (Low-Side PWM Dimming)
  +-------------------------------------------------------------+
  |                  12V LED FIXTURE / STRIP                    |
  |          (Supplies only supplemental illumination)          |
  +-------------------------------------------------------------+
```

---

## 2. Complete Circuit Schematic (ASCII)

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

---

## 3. Pin Connection Table

| ESP32 Pin | Connected Component | Function / Signal Description |
| :--- | :--- | :--- |
| **3.3V** | LDR Pin 1 | Supplies 3.3V regulated power to the daylight sensor voltage divider. |
| **GPIO 34 (ADC1_CH6)** | Junction of LDR & 10 kΩ Resistor | Reads light-dependent analog voltage (0–3.3V mapped to 0–4095). |
| **GND** | 10 kΩ Resistor Pin 2 | Completes the sensor voltage divider ground path. |
| **GPIO 16** | 220 Ω Resistor to MOSFET Gate | 5 kHz PWM signal for flicker-free LED dimming. |
| **GND** | 10 kΩ Gate Pull-Down Resistor | Holds Gate LOW during bootup/reset to keep LEDs strictly OFF. |
| **GND** | MOSFET Source & 12V Supply GND | **CRITICAL: Common ground connection** between ESP32 and 12V supply. |

---

## 4. Subsystem Design Calculations

### 4.1 LDR Voltage Divider Circuit
The LDR resistance decreases as daylight intensity increases:
* **Dark (~10 lux):** $R_{ldr} \approx 50\text{ k}\Omega$ to $200\text{ k}\Omega$
* **Ambient Daylight (~500 lux):** $R_{ldr} \approx 2\text{ k}\Omega$ to $8\text{ k}\Omega$
* **Direct Bright Sunlight (>1000 lux):** $R_{ldr} \approx 300\,\Omega$ to $1\text{ k}\Omega$

The analog voltage at GPIO 34 is:
$$V_{out} = 3.3\text{V} \times \frac{R_{fixed}}{R_{ldr} + R_{fixed}}$$

With $R_{fixed} = 10\text{ k}\Omega$:
* In the dark: $V_{out} \approx 3.3\text{V} \times \frac{10}{200 + 10} \approx 0.15\text{V}$ (ADC ~ 190)
* In bright sun: $V_{out} \approx 3.3\text{V} \times \frac{10}{1 + 10} \approx 3.0\text{V}$ (ADC ~ 3720)

### 4.2 MOSFET Selection & Gate Drive
* **Why Logic-Level?** The ESP32 outputs 3.3V logic. Standard MOSFETs (e.g., IRF540N) require 10V gate-to-source ($V_{gs}$) to fully saturate. Using a **logic-level N-channel MOSFET** (such as **IRLZ44N**, **FQP30N06L**, or **RFP30N06LE**) ensures full saturation ($R_{ds(on)} < 0.03\,\Omega$) at 3.3V, preventing MOSFET overheating.
* **Gate Resistor ($220\,\Omega$):** Dampens high-frequency ringing and limits gate charging current spikes to protect ESP32 GPIO 16.
* **Gate Pull-Down Resistor ($10\text{ k}\Omega$):** Prevents the gate from floating while the ESP32 is booting, ensuring lights remain OFF until the firmware initializes.
