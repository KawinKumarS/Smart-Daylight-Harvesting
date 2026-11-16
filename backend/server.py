"""
FastAPI Backend & WebSocket Server for the Smart Daylight Harvesting Dashboard.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.daylight_controller import DaylightEngine

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"

engine: Optional[DaylightEngine] = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global engine
    engine = DaylightEngine(log_dir=DATA_DIR)
    try:
        yield
    finally:
        if engine is not None:
            engine.shutdown()


app = FastAPI(
    title="Smart Daylight Harvesting System API",
    version="1.0.0",
    lifespan=lifespan,
)


class ConnectRequest(BaseModel):
    mode: str = "SIMULATOR"  # "ESP32" or "SIMULATOR"
    port: Optional[str] = None
    baudrate: int = 115200


class ControlRequest(BaseModel):
    mode: Optional[str] = None
    target_lux: Optional[float] = None
    manual_pct: Optional[float] = None
    rated_watts: Optional[float] = None
    tariff_per_kwh: Optional[float] = None
    sim_weather: Optional[str] = None
    sim_hour: Optional[float] = None
    sim_custom_lux: Optional[float] = None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ports")
def get_ports():
    return {"ports": DaylightEngine.list_serial_ports()}


@app.get("/api/state")
def get_state():
    assert engine is not None
    return engine.get_state()


@app.post("/api/connect")
def connect_device(req: ConnectRequest):
    assert engine is not None
    if req.mode.upper() == "ESP32":
        if not req.port:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Please select a COM port."},
            )
        result = engine.connect_serial(req.port, req.baudrate)
        if not result.get("ok"):
            return JSONResponse(status_code=400, content=result)
        return result
    return engine.switch_to_simulator()


@app.post("/api/control")
def update_control(req: ControlRequest):
    assert engine is not None
    payload = req.model_dump(exclude_none=True)
    return engine.update_control(payload)


@app.post("/api/reset")
def reset_stats():
    assert engine is not None
    return engine.reset_stats()


@app.get("/api/export/csv")
def export_csv():
    assert engine is not None
    csv_path = engine.get_csv_path()
    return FileResponse(
        path=str(csv_path),
        media_type="text/csv",
        filename="daylight_harvesting_telemetry.csv",
    )


@app.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    assert engine is not None
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(engine.get_state())
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@app.get("/")
@app.get("/index.html")
def get_index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/styles.css")
def get_styles():
    return FileResponse(FRONTEND_DIR / "styles.css")


@app.get("/app.js")
def get_script():
    return FileResponse(FRONTEND_DIR / "app.js")


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
