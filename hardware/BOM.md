# Bill of Materials (BOM)

| # | Item Name | Specifications / Part Number | Qty | Approximate Cost | Purpose |
| :- | :--- | :--- | :-: | :-: | :--- |
| 1 | **Microcontroller Board** | ESP32 NodeMCU Dev Module (30-pin or 38-pin, Dual Core 240MHz, 4MB Flash) | 1 | ~$4.00 - $5.50 | Main controller: ADC reading, daylight harvesting loop, PWM output, USB serial telemetry |
| 2 | **Light Sensor** | 5mm Light Dependent Resistor (LDR GL5528 or GL5539) | 1 | ~$0.20 | Detects incoming natural daylight intensity through room windows |
| 3 | **Fixed Resistor (Divider)** | 10 kΩ 1/4W Metal Film Resistor (±1% or ±5%) | 1 | ~$0.05 | Forms voltage divider with LDR on GPIO 34 |
| 4 | **Logic-Level Power MOSFET** | IRLZ44N / FQP30N06L / RFP30N06LE (N-Channel, TO-220, $V_{gs(th)} \le 2.0\text{V}$) | 1 | ~$0.80 - $1.20 | Low-side PWM switching for high-current 12V LED lighting load |
| 5 | **Gate Protection Resistor** | 220 Ω 1/4W Resistor | 1 | ~$0.05 | Limits gate surge current from ESP32 GPIO 16 |
| 6 | **Gate Pull-down Resistor** | 10 kΩ 1/4W Resistor | 1 | ~$0.05 | Pulls MOSFET gate to GND during boot to prevent LED flicker |
| 7 | **LED Lighting Load** | 12V DC White LED Strip (SMD 2835 / 5050) or 12V COB LED Fixture (rated 10W - 20W) | 1 | ~$3.00 - $6.00 | Supplemental artificial indoor light fixture |
| 8 | **External DC Power Supply** | 12V 2A (or 3A) DC Regulated Adapter | 1 | ~$4.00 - $6.00 | Powers the 12V LED lighting fixture |
| 9 | **Solderless Breadboard / PCB** | 400-point Breadboard or Prototype Perfboard | 1 | ~$1.50 - $2.50 | Circuit prototyping and mounting |
| 10 | **Jumper Wires** | Male-to-Male and Male-to-Female Dupont Wires | 1 set | ~$1.00 | Breadboard & pin connections |
| 11 | **Micro-USB Cable** | Data-capable Micro-USB cable | 1 | ~$1.00 | Powers ESP32 and provides serial telemetry communication to Laptop |

---

### Total Estimated Hardware Cost: **~$15 – $22 USD** (Affordable, scalable smart building solution)
