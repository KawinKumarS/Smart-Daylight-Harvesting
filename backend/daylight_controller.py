"""
Core Daylight Harvesting Engine & Hardware/Simulator Controller.

Supports two data sources:
  1. USB Serial connection to an ESP32 running smart_daylight_harvesting.ino
  2. Built-in Solar Daylight Simulator for offline testing & live demos
"""

from __future__ import annotations

import csv
import json
import math
import random
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


MAX_LUX_REF = 1000.0
PWM_MAX = 255
CO2_GRAMS_PER_WH = 0.82  # Standard grid emission factor (0.82 kg CO2 / kWh)
DEFAULT_TARIFF_PER_KWH = 7.0  # INR per kWh (editable via API)


@dataclass
class TelemetryPoint:
    timestamp: str
    epoch_s: float
    source: str          # "ESP32" or "SIMULATOR"
    adc: int
    lux: float
    daylight_pct: float
    led_pwm: int
    led_pct: float
    target_lux: float
    total_room_lux: float
    mode: str            # "AUTO" or "MANUAL"
    power_w: float
    saved_w: float
    rated_watts: float
    energy_saved_pct: float
    baseline_wh: float
    actual_wh: float
    saved_wh: float
    co2_saved_g: float
    cost_saved: float
    lighting_status: str
    daylight_condition: str
    sim_hour: float
    sim_weather: str


def classify_daylight(lux: float) -> str:
    if lux < 40:
        return "Night / Dark"
    if lux < 180:
        return "Low / Dusk"
    if lux < 450:
        return "Moderate / Overcast"
    if lux < 750:
        return "Bright Daylight"
    return "Peak Sunlight"


def classify_lighting_status(mode: str, led_pct: float) -> str:
    if mode == "MANUAL":
        return f"Manual Override ({led_pct:.0f}%)"
    if led_pct <= 1.0:
        return "Daylight Sufficient (LED Off)"
    if led_pct < 35.0:
        return "Eco Dimmed (Low Supplement)"
    if led_pct < 75.0:
        return "Balanced Harvesting"
    return "Full Supplement Needed"


class DaylightEngine:
    """Thread-safe controller managing ESP32 Serial I/O, simulation, and analytics."""

    def __init__(self, log_dir: Path) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._csv_path = self._log_dir / "telemetry_log.csv"
        self._init_csv()

        # Connection state
        self._source = "SIMULATOR"
        self._port_name: Optional[str] = None
        self._baudrate = 115200
        self._serial: Optional[Any] = None
        self._last_error: Optional[str] = None
        self._serial_logs: Deque[str] = deque(maxlen=60)

        # Control parameters
        self._mode = "AUTO"
        self._target_lux = 500.0
        self._manual_pct = 50.0
        self._rated_watts = 12.0
        self._tariff_per_kwh = DEFAULT_TARIFF_PER_KWH

        # Simulator parameters
        self._sim_weather = "sunny"   # auto_cycle | sunny | cloudy | overcast | night | custom
        self._sim_hour = 10.5         # 0..24 hour clock for simulator
        self._sim_custom_lux = 620.0
        self._sim_speed = 0.0         # hours per second when auto_cycle is active
        self._sim_pwm = 80
        self._sim_lux = 620.0

        # Cumulative energy counters
        self._baseline_wh = 0.0
        self._actual_wh = 0.0
        self._last_energy_ts = time.monotonic()

        # Telemetry history (last 300 samples)
        self._history: Deque[Dict[str, Any]] = deque(maxlen=300)
        self._latest: Optional[TelemetryPoint] = None

        self._worker_thread = threading.Thread(
            target=self._run_loop, name="DaylightEngineLoop", daemon=True
        )
        self._worker_thread.start()
        self._append_log("System initialized in SIMULATOR mode.")

    def _init_csv(self) -> None:
        if not self._csv_path.exists():
            with self._csv_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow([
                    "timestamp", "source", "adc", "lux", "daylight_pct",
                    "led_pwm", "led_pct", "target_lux", "total_room_lux",
                    "mode", "power_w", "saved_w", "saved_wh", "co2_saved_g"
                ])

    def _append_csv(self, point: TelemetryPoint) -> None:
        try:
            with self._csv_path.open("a", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow([
                    point.timestamp, point.source, point.adc, f"{point.lux:.1f}",
                    f"{point.daylight_pct:.1f}", point.led_pwm, f"{point.led_pct:.1f}",
                    f"{point.target_lux:.1f}", f"{point.total_room_lux:.1f}",
                    point.mode, f"{point.power_w:.2f}", f"{point.saved_w:.2f}",
                    f"{point.saved_wh:.4f}", f"{point.co2_saved_g:.3f}",
                ])
        except OSError:
            pass

    def _append_log(self, msg: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._serial_logs.append(f"[{stamp}] {msg}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def list_serial_ports() -> List[Dict[str, str]]:
        if not SERIAL_AVAILABLE:
            return []
        ports = []
        for p in serial.tools.list_ports.comports():
            ports.append({
                "device": p.device,
                "description": p.description or "Serial Device",
                "hwid": p.hwid or "",
            })
        return ports

    def connect_serial(self, port: str, baudrate: int = 115200) -> Dict[str, Any]:
        if not SERIAL_AVAILABLE:
            return {"ok": False, "error": "pyserial is not installed."}

        with self._lock:
            self._close_serial_locked()
            try:
                ser = serial.Serial(port=port, baudrate=baudrate, timeout=0.25)
                self._serial = ser
                self._port_name = port
                self._baudrate = baudrate
                self._source = "ESP32"
                self._last_error = None
                self._append_log(f"Connected to ESP32 on {port} @ {baudrate} baud.")
                # Sync current dashboard settings to the ESP32
                self._send_serial_locked(f"SET_TARGET:{self._target_lux:.0f}")
                self._send_serial_locked(f"MODE:{self._mode}")
                return {"ok": True, "source": "ESP32", "port": port}
            except Exception as exc:
                self._source = "SIMULATOR"
                self._port_name = None
                err_msg = str(exc)
                if "Access is denied" in err_msg or isinstance(exc, PermissionError):
                    err_msg = (
                        f"Port '{port}' is already in use by another program (such as the Arduino IDE Serial Monitor or Serial Plotter). "
                        "Please close the Serial Monitor tab in Arduino IDE, then click Connect again."
                    )
                self._last_error = err_msg
                self._append_log(f"Serial connection failed ({port}): {err_msg}")
                return {"ok": False, "error": err_msg}

    def switch_to_simulator(self) -> Dict[str, Any]:
        with self._lock:
            self._close_serial_locked()
            self._source = "SIMULATOR"
            self._last_error = None
            self._append_log("Switched to Built-in Daylight Simulator.")
            return {"ok": True, "source": "SIMULATOR"}

    def update_control(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if "mode" in payload and payload["mode"] in ("AUTO", "MANUAL"):
                self._mode = payload["mode"]
                if self._source == "ESP32":
                    self._send_serial_locked(f"MODE:{self._mode}")
                self._append_log(f"Mode changed to {self._mode}.")

            if "target_lux" in payload and payload["target_lux"] is not None:
                self._target_lux = max(50.0, min(1000.0, float(payload["target_lux"])))
                if self._source == "ESP32":
                    self._send_serial_locked(f"SET_TARGET:{self._target_lux:.0f}")
                self._append_log(f"Target illumination set to {self._target_lux:.0f} lux.")

            if "manual_pct" in payload and payload["manual_pct"] is not None:
                self._manual_pct = max(0.0, min(100.0, float(payload["manual_pct"])))
                self._mode = "MANUAL"
                if self._source == "ESP32":
                    self._send_serial_locked(f"SET_PCT:{self._manual_pct:.1f}")
                self._append_log(f"Manual LED brightness set to {self._manual_pct:.0f}%.")

            if "rated_watts" in payload and payload["rated_watts"] is not None:
                self._rated_watts = max(1.0, min(50000.0, float(payload["rated_watts"])))

            if "tariff_per_kwh" in payload and payload["tariff_per_kwh"] is not None:
                self._tariff_per_kwh = max(0.0, float(payload["tariff_per_kwh"]))

            if "sim_weather" in payload and payload["sim_weather"]:
                self._sim_weather = str(payload["sim_weather"])
                if self._sim_weather == "auto_cycle":
                    self._sim_speed = 0.25  # 1 simulated hour every 4 seconds
                else:
                    self._sim_speed = 0.0
                self._append_log(f"Simulator preset: {self._sim_weather}")

            if "sim_hour" in payload and payload["sim_hour"] is not None:
                self._sim_hour = max(0.0, min(24.0, float(payload["sim_hour"])))

            if "sim_custom_lux" in payload and payload["sim_custom_lux"] is not None:
                self._sim_custom_lux = max(0.0, min(1000.0, float(payload["sim_custom_lux"])))
                self._sim_weather = "custom"

        return self.get_state()

    def reset_stats(self) -> Dict[str, Any]:
        with self._lock:
            self._baseline_wh = 0.0
            self._actual_wh = 0.0
            self._last_energy_ts = time.monotonic()
            self._history.clear()
            self._append_log("Energy statistics & chart history reset.")
        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            latest_dict = asdict(self._latest) if self._latest else None
            return {
                "connected_source": self._source,
                "port": self._port_name,
                "serial_available": SERIAL_AVAILABLE,
                "last_error": self._last_error,
                "telemetry": latest_dict,
                "history": list(self._history),
                "logs": list(self._serial_logs),
                "config": {
                    "mode": self._mode,
                    "target_lux": self._target_lux,
                    "manual_pct": self._manual_pct,
                    "rated_watts": self._rated_watts,
                    "tariff_per_kwh": self._tariff_per_kwh,
                    "sim_weather": self._sim_weather,
                    "sim_hour": round(self._sim_hour, 2),
                    "sim_custom_lux": self._sim_custom_lux,
                },
            }

    def get_csv_path(self) -> Path:
        return self._csv_path

    def shutdown(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._close_serial_locked()

    # ------------------------------------------------------------------
    # Internal helpers & background loop
    # ------------------------------------------------------------------

    def _close_serial_locked(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def _send_serial_locked(self, command: str) -> None:
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.write((command.strip() + "\n").encode("utf-8"))
            except Exception as exc:
                self._last_error = str(exc)
                self._append_log(f"Serial write error: {exc}")

    def _compute_solar_lux(self, dt_s: float) -> float:
        if self._sim_weather == "custom":
            return self._sim_custom_lux

        if self._sim_weather == "night":
            return 8.0 + random.uniform(-2.0, 2.0)

        if self._sim_weather == "auto_cycle":
            self._sim_hour = (self._sim_hour + self._sim_speed * dt_s) % 24.0

        # Smooth daytime bell curve between 06:00 and 18:30
        if 6.0 <= self._sim_hour <= 18.5:
            phase = (self._sim_hour - 6.0) / 12.5
            solar_base = math.sin(phase * math.pi) * 950.0
        else:
            solar_base = 12.0

        if self._sim_weather == "sunny":
            lux = max(solar_base, 650.0 if 7.0 <= self._sim_hour <= 17.5 else 15.0)
            lux += random.uniform(-8.0, 8.0)
        elif self._sim_weather == "cloudy":
            # Passing cloud waves
            cloud_dip = 0.55 + 0.45 * math.sin(time.monotonic() * 0.45)
            lux = solar_base * cloud_dip + random.uniform(-15.0, 15.0)
        elif self._sim_weather == "overcast":
            lux = min(solar_base * 0.35, 280.0) + random.uniform(-10.0, 10.0)
        else:  # auto_cycle
            lux = solar_base + random.uniform(-6.0, 6.0)

        return max(0.0, min(MAX_LUX_REF, lux))

    def _step_simulator(self, dt_s: float) -> TelemetryPoint:
        target_sim_lux = self._compute_solar_lux(dt_s)
        # Smooth sensor response
        self._sim_lux += 0.35 * (target_sim_lux - self._sim_lux)
        lux = max(0.0, min(MAX_LUX_REF, self._sim_lux))
        adc = int(round(250 + (lux / MAX_LUX_REF) * (3800 - 250)))
        daylight_pct = min(100.0, (lux / MAX_LUX_REF) * 100.0)

        if self._mode == "AUTO":
            deficit = self._target_lux - lux
            if lux >= self._target_lux + 20.0:
                target_pwm = 0
            elif deficit <= 0.0:
                target_pwm = max(0, self._sim_pwm - 4)
            else:
                ratio = max(0.0, min(1.0, deficit / max(1.0, self._target_lux)))
                target_pwm = int(round(ratio * PWM_MAX))
        else:
            target_pwm = int(round((self._manual_pct / 100.0) * PWM_MAX))

        # Smooth PWM ramping (2 Hz simulator tick -> ~4s full 0-100% transition)
        step = 32
        if self._sim_pwm < target_pwm:
            self._sim_pwm = min(target_pwm, self._sim_pwm + step)
        elif self._sim_pwm > target_pwm:
            self._sim_pwm = max(target_pwm, self._sim_pwm - step)

        led_pct = (self._sim_pwm / PWM_MAX) * 100.0
        return self._build_point(
            source="SIMULATOR",
            adc=adc,
            lux=lux,
            daylight_pct=daylight_pct,
            led_pwm=self._sim_pwm,
            led_pct=led_pct,
            mode=self._mode,
            dt_s=dt_s,
        )

    def _read_esp32_packet(self, dt_s: float) -> Optional[TelemetryPoint]:
        if self._serial is None or not self._serial.is_open:
            return None

        latest_json: Optional[Dict[str, Any]] = None
        try:
            while self._serial.in_waiting > 0:
                raw_line = self._serial.readline().decode("utf-8", errors="ignore").strip()
                if not raw_line:
                    continue
                if raw_line.startswith("{"):
                    try:
                        parsed = json.loads(raw_line)
                        if "lux" in parsed and "led_pwm" in parsed:
                            latest_json = parsed
                        elif "ack" in parsed or "event" in parsed:
                            self._append_log(f"ESP32: {raw_line}")
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            self._last_error = str(exc)
            self._append_log(f"ESP32 disconnected ({exc}). Falling back to Simulator.")
            self._close_serial_locked()
            self._source = "SIMULATOR"
            return None

        if latest_json is None:
            return None

        lux = float(latest_json.get("lux", 0.0))
        adc = int(latest_json.get("adc", 0))
        daylight_pct = float(latest_json.get("daylight_pct", min(100.0, lux / 10.0)))
        led_pwm = int(latest_json.get("led_pwm", 0))
        led_pct = float(latest_json.get("led_pct", (led_pwm / PWM_MAX) * 100.0))
        mode = str(latest_json.get("mode", self._mode))

        return self._build_point(
            source="ESP32",
            adc=adc,
            lux=lux,
            daylight_pct=daylight_pct,
            led_pwm=led_pwm,
            led_pct=led_pct,
            mode=mode,
            dt_s=dt_s,
        )

    def _build_point(
        self,
        *,
        source: str,
        adc: int,
        lux: float,
        daylight_pct: float,
        led_pwm: int,
        led_pct: float,
        mode: str,
        dt_s: float,
    ) -> TelemetryPoint:
        rated = self._rated_watts
        power_w = (led_pct / 100.0) * rated
        saved_w = max(0.0, rated - power_w)
        energy_saved_pct = max(0.0, min(100.0, 100.0 - led_pct))

        dt_hours = max(0.0, min(dt_s, 5.0)) / 3600.0
        self._baseline_wh += rated * dt_hours
        self._actual_wh += power_w * dt_hours
        saved_wh = max(0.0, self._baseline_wh - self._actual_wh)
        co2_saved_g = saved_wh * CO2_GRAMS_PER_WH
        cost_saved = (saved_wh / 1000.0) * self._tariff_per_kwh

        # Estimated combined room illumination = natural daylight + artificial LED contribution
        artificial_lux = (led_pct / 100.0) * self._target_lux
        total_room_lux = min(1200.0, lux + artificial_lux)

        return TelemetryPoint(
            timestamp=datetime.now(timezone.utc).isoformat(),
            epoch_s=time.time(),
            source=source,
            adc=adc,
            lux=round(lux, 1),
            daylight_pct=round(daylight_pct, 1),
            led_pwm=led_pwm,
            led_pct=round(led_pct, 1),
            target_lux=round(self._target_lux, 1),
            total_room_lux=round(total_room_lux, 1),
            mode=mode,
            power_w=round(power_w, 2),
            saved_w=round(saved_w, 2),
            rated_watts=round(rated, 1),
            energy_saved_pct=round(energy_saved_pct, 1),
            baseline_wh=round(self._baseline_wh, 4),
            actual_wh=round(self._actual_wh, 4),
            saved_wh=round(saved_wh, 4),
            co2_saved_g=round(co2_saved_g, 3),
            cost_saved=round(cost_saved, 4),
            lighting_status=classify_lighting_status(mode, led_pct),
            daylight_condition=classify_daylight(lux),
            sim_hour=round(self._sim_hour, 2),
            sim_weather=self._sim_weather,
        )

    def _run_loop(self) -> None:
        csv_tick = 0
        while not self._stop_event.is_set():
            now = time.monotonic()
            with self._lock:
                dt_s = now - self._last_energy_ts
                self._last_energy_ts = now

                point: Optional[TelemetryPoint] = None
                if self._source == "ESP32":
                    point = self._read_esp32_packet(dt_s)
                else:
                    point = self._step_simulator(dt_s)

                if point is not None:
                    self._latest = point
                    point_dict = asdict(point)
                    self._history.append(point_dict)
                    csv_tick += 1
                    if csv_tick % 2 == 0:  # Log to CSV once per second
                        self._append_csv(point)

            time.sleep(0.5)
