(() => {
  const $ = (id) => document.getElementById(id);

  // DOM References
  const connectionPill = $("connectionPill");
  const connectionText = $("connectionText");
  const modePill = $("modePill");
  const portSelect = $("portSelect");
  const refreshPortsBtn = $("refreshPortsBtn");
  const connectBtn = $("connectBtn");
  const exportCsvBtn = $("exportCsvBtn");
  const resetStatsBtn = $("resetStatsBtn");

  const btnModeAuto = $("btnModeAuto");
  const btnModeManual = $("btnModeManual");
  const targetLuxSlider = $("targetLuxSlider");
  const targetLuxDisplay = $("targetLuxDisplay");
  const manualPctSlider = $("manualPctSlider");
  const manualPctDisplay = $("manualPctDisplay");
  const manualDimmerGroup = $("manualDimmerGroup");
  const ratedWattsInput = $("ratedWattsInput");
  const tariffInput = $("tariffInput");

  const simulatorControls = $("simulatorControls");
  const simBadge = $("simBadge");
  const simHourSlider = $("simHourSlider");
  const simHourDisplay = $("simHourDisplay");
  const simCustomLuxSlider = $("simCustomLuxSlider");
  const simCustomLuxDisplay = $("simCustomLuxDisplay");
  const presetBtns = Array.from(document.querySelectorAll(".preset-btn"));

  const consoleLog = $("consoleLog");
  const chartCanvas = $("telemetryChart");

  let activeEditing = new Set();
  let latestState = null;

  // ------------------------------------------------------------------
  // API Helpers
  // ------------------------------------------------------------------
  async function apiPost(url, body = {}) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Request failed");
    }
    return data;
  }

  async function scanPorts() {
    try {
      const res = await fetch("/api/ports");
      const data = await res.json();
      const prev = portSelect.value;
      portSelect.innerHTML = '<option value="SIMULATOR">Built-in Daylight Simulator</option>';
      for (const p of data.ports || []) {
        const opt = document.createElement("option");
        opt.value = p.device;
        opt.textContent = `${p.device} — ${p.description}`;
        portSelect.appendChild(opt);
      }
      if ([...portSelect.options].some((o) => o.value === prev)) {
        portSelect.value = prev;
      }
    } catch (err) {
      console.error("Failed to scan ports:", err);
    }
  }

  async function sendControl(payload) {
    try {
      const state = await apiPost("/api/control", payload);
      renderState(state);
    } catch (err) {
      console.error("Control error:", err);
    }
  }

  // ------------------------------------------------------------------
  // Event Wiring
  // ------------------------------------------------------------------
  refreshPortsBtn.addEventListener("click", scanPorts);

  connectBtn.addEventListener("click", async () => {
    const selected = portSelect.value;
    try {
      if (selected === "SIMULATOR") {
        await apiPost("/api/connect", { mode: "SIMULATOR" });
      } else {
        await apiPost("/api/connect", { mode: "ESP32", port: selected });
      }
    } catch (err) {
      alert(`Connection error: ${err.message}`);
    }
  });

  exportCsvBtn.addEventListener("click", () => {
    window.location.href = "/api/export/csv";
  });

  resetStatsBtn.addEventListener("click", async () => {
    const state = await apiPost("/api/reset");
    renderState(state);
  });

  btnModeAuto.addEventListener("click", () => sendControl({ mode: "AUTO" }));
  btnModeManual.addEventListener("click", () => sendControl({ mode: "MANUAL" }));

  function bindSlider(el, key, formatter, onCommit) {
    el.addEventListener("pointerdown", () => activeEditing.add(key));
    el.addEventListener("pointerup", () => activeEditing.delete(key));
    el.addEventListener("input", () => {
      formatter(el.value);
    });
    el.addEventListener("change", () => {
      activeEditing.delete(key);
      onCommit(parseFloat(el.value));
    });
  }

  bindSlider(
    targetLuxSlider,
    "target_lux",
    (v) => { targetLuxDisplay.textContent = `${v} lux`; },
    (v) => sendControl({ target_lux: v })
  );

  bindSlider(
    manualPctSlider,
    "manual_pct",
    (v) => { manualPctDisplay.textContent = `${v}%`; },
    (v) => sendControl({ manual_pct: v, mode: "MANUAL" })
  );

  bindSlider(
    simHourSlider,
    "sim_hour",
    (v) => { simHourDisplay.textContent = formatHour(parseFloat(v)); },
    (v) => sendControl({ sim_hour: v })
  );

  bindSlider(
    simCustomLuxSlider,
    "sim_custom_lux",
    (v) => { simCustomLuxDisplay.textContent = `${v} lux`; },
    (v) => sendControl({ sim_custom_lux: v, sim_weather: "custom" })
  );

  ratedWattsInput.addEventListener("focus", () => activeEditing.add("rated_watts"));
  ratedWattsInput.addEventListener("blur", () => activeEditing.delete("rated_watts"));
  ratedWattsInput.addEventListener("change", () => {
    const v = parseFloat(ratedWattsInput.value);
    if (v >= 1) sendControl({ rated_watts: v });
  });

  tariffInput.addEventListener("focus", () => activeEditing.add("tariff"));
  tariffInput.addEventListener("blur", () => activeEditing.delete("tariff"));
  tariffInput.addEventListener("change", () => {
    const v = parseFloat(tariffInput.value);
    if (v >= 0) sendControl({ tariff_per_kwh: v });
  });

  presetBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      sendControl({ sim_weather: btn.dataset.weather });
    });
  });

  function formatHour(hourFloat) {
    const totalMins = Math.round((hourFloat % 24) * 60);
    const hh = String(Math.floor(totalMins / 60) % 24).padStart(2, "0");
    const mm = String(totalMins % 60).padStart(2, "0");
    return `${hh}:${mm}`;
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------
  function renderState(state) {
    latestState = state;
    const t = state.telemetry;
    const cfg = state.config || {};

    // Connection badge
    if (state.connected_source === "ESP32") {
      connectionPill.className = "pill connected";
      connectionText.textContent = `ESP32 (${state.port})`;
      simulatorControls.classList.add("disabled-block");
      simBadge.textContent = "Paused (Live Hardware Active)";
    } else {
      connectionPill.className = "pill sim";
      connectionText.textContent = "Simulator Mode";
      simulatorControls.classList.remove("disabled-block");
      simBadge.textContent = "Active (Interactive Demo)";
    }

    // Mode pill & buttons
    const mode = t ? t.mode : cfg.mode || "AUTO";
    if (mode === "AUTO") {
      modePill.textContent = "AUTO HARVESTING";
      modePill.className = "pill mode-pill";
      btnModeAuto.classList.add("active");
      btnModeManual.classList.remove("active");
      manualDimmerGroup.classList.add("disabled-block");
    } else {
      modePill.textContent = "MANUAL OVERRIDE";
      modePill.className = "pill mode-pill manual";
      btnModeManual.classList.add("active");
      btnModeAuto.classList.remove("active");
      manualDimmerGroup.classList.remove("disabled-block");
    }

    // Sync inputs if not actively edited
    if (!activeEditing.has("target_lux") && cfg.target_lux !== undefined) {
      targetLuxSlider.value = cfg.target_lux;
      targetLuxDisplay.textContent = `${Math.round(cfg.target_lux)} lux`;
    }
    if (!activeEditing.has("manual_pct") && cfg.manual_pct !== undefined) {
      manualPctSlider.value = cfg.manual_pct;
      manualPctDisplay.textContent = `${Math.round(cfg.manual_pct)}%`;
    }
    if (!activeEditing.has("rated_watts") && cfg.rated_watts !== undefined) {
      ratedWattsInput.value = cfg.rated_watts;
    }
    if (!activeEditing.has("tariff") && cfg.tariff_per_kwh !== undefined) {
      tariffInput.value = cfg.tariff_per_kwh;
    }
    if (!activeEditing.has("sim_hour") && cfg.sim_hour !== undefined) {
      simHourSlider.value = cfg.sim_hour;
      simHourDisplay.textContent = formatHour(cfg.sim_hour);
    }
    if (!activeEditing.has("sim_custom_lux") && cfg.sim_custom_lux !== undefined) {
      simCustomLuxSlider.value = cfg.sim_custom_lux;
      simCustomLuxDisplay.textContent = `${Math.round(cfg.sim_custom_lux)} lux`;
    }

    presetBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.weather === cfg.sim_weather);
    });

    if (t) {
      $("luxValue").textContent = t.lux.toFixed(0);
      $("daylightBar").style.width = `${Math.min(100, t.daylight_pct)}%`;
      $("daylightPct").textContent = `${t.daylight_pct.toFixed(0)}%`;
      $("adcValue").textContent = t.adc;
      $("daylightConditionBadge").textContent = t.daylight_condition;

      $("ledPctValue").textContent = t.led_pct.toFixed(0);
      $("ledBar").style.width = `${Math.min(100, t.led_pct)}%`;
      $("pwmValue").textContent = t.led_pwm;
      $("powerValue").textContent = `${t.power_w.toFixed(1)} W`;
      $("lightingStatusBadge").textContent = t.lighting_status;

      $("savedPctValue").textContent = t.energy_saved_pct.toFixed(0);
      $("savedBar").style.width = `${Math.min(100, t.energy_saved_pct)}%`;
      $("savedWattsValue").textContent = `${t.saved_w.toFixed(1)} W`;
      $("ratedWattsLabel").textContent = `${t.rated_watts.toFixed(0)} W`;

      $("savedWhValue").textContent = t.saved_wh.toFixed(2);
      $("co2Value").textContent =
        t.co2_saved_g >= 1000
          ? `${(t.co2_saved_g / 1000).toFixed(2)} kg`
          : `${t.co2_saved_g.toFixed(1)} g`;
      $("costValue").textContent = `₹${t.cost_saved.toFixed(2)}`;
      $("totalRoomLux").textContent = `${t.total_room_lux.toFixed(0)} lux`;
      $("targetLuxLabel").textContent = `${t.target_lux.toFixed(0)} lux`;

      // Update Room SVG
      const sunNorm = Math.max(0, Math.min(1, t.lux / 900));
      const ledNorm = Math.max(0, Math.min(1, t.led_pct / 100));
      $("sunBeam").setAttribute("opacity", (0.04 + sunNorm * 0.85).toFixed(2));
      $("ledCone").setAttribute("opacity", (ledNorm * 0.88).toFixed(2));
      $("ledBarGlow").setAttribute("opacity", (0.12 + ledNorm * 0.88).toFixed(2));
      $("skyStopTop").setAttribute("stop-color", sunNorm < 0.08 ? "#0f172a" : "#38bdf8");
      $("skyStopBottom").setAttribute("stop-color", sunNorm < 0.08 ? "#1e293b" : "#fef08a");
      $("svgLuxText").textContent = `${t.lux.toFixed(0)} lux`;
      $("svgLedText").textContent = `${t.led_pct.toFixed(0)}%`;
    }

    // Logs
    if (Array.isArray(state.logs)) {
      const wasAtBottom =
        consoleLog.scrollHeight - consoleLog.scrollTop - consoleLog.clientHeight < 24;
      consoleLog.textContent = state.logs.join("\n");
      if (wasAtBottom) {
        consoleLog.scrollTop = consoleLog.scrollHeight;
      }
    }

    drawChart(state.history || [], cfg.target_lux || 500);
  }

  // ------------------------------------------------------------------
  // Real-Time Dual Chart (HTML5 Canvas, zero external dependencies)
  // ------------------------------------------------------------------
  function drawChart(history, targetLux) {
    const rect = chartCanvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(300, Math.floor(rect.width - 16));
    const height = Math.max(180, Math.floor(rect.height - 16));

    if (chartCanvas.width !== width * dpr || chartCanvas.height !== height * dpr) {
      chartCanvas.width = width * dpr;
      chartCanvas.height = height * dpr;
    }

    const ctx = chartCanvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const padL = 44;
    const padR = 44;
    const padT = 16;
    const padB = 26;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;

    // Grid lines
    ctx.strokeStyle = "#1e293b";
    ctx.lineWidth = 1;
    ctx.font = "11px Segoe UI, sans-serif";
    ctx.fillStyle = "#94a3b8";

    for (let i = 0; i <= 4; i++) {
      const frac = i / 4;
      const y = padT + plotH * (1 - frac);
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(padL + plotW, y);
      ctx.stroke();

      // Left axis: Lux (0 - 1000)
      ctx.textAlign = "right";
      ctx.fillText(`${Math.round(frac * 1000)}`, padL - 6, y + 4);

      // Right axis: PWM % (0 - 100)
      ctx.textAlign = "left";
      ctx.fillText(`${Math.round(frac * 100)}%`, padL + plotW + 6, y + 4);
    }

    // Target Lux dashed line
    const targetY = padT + plotH * (1 - Math.min(1, targetLux / 1000));
    ctx.save();
    ctx.strokeStyle = "#22c55e";
    ctx.setLineDash([5, 5]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(padL, targetY);
    ctx.lineTo(padL + plotW, targetY);
    ctx.stroke();
    ctx.restore();

    const samples = history.slice(-90);
    if (samples.length < 2) {
      ctx.fillStyle = "#64748b";
      ctx.textAlign = "center";
      ctx.fillText("Collecting live telemetry...", padL + plotW / 2, padT + plotH / 2);
      return;
    }

    const xFor = (idx) => padL + (idx / (samples.length - 1)) * plotW;

    // Daylight Lux line (Yellow/Amber)
    ctx.beginPath();
    samples.forEach((pt, idx) => {
      const x = xFor(idx);
      const y = padT + plotH * (1 - Math.max(0, Math.min(1, pt.lux / 1000)));
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#facc15";
    ctx.lineWidth = 2.4;
    ctx.stroke();

    // LED Brightness % line (Cyan)
    ctx.beginPath();
    samples.forEach((pt, idx) => {
      const x = xFor(idx);
      const y = padT + plotH * (1 - Math.max(0, Math.min(1, pt.led_pct / 100)));
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2.4;
    ctx.stroke();

    // Bottom axis caption
    ctx.fillStyle = "#64748b";
    ctx.textAlign = "center";
    ctx.fillText(`Showing last ${samples.length} readings (live 2 Hz stream)`, padL + plotW / 2, height - 6);
  }

  window.addEventListener("resize", () => {
    if (latestState) drawChart(latestState.history || [], latestState.config?.target_lux || 500);
  });

  // ------------------------------------------------------------------
  // WebSocket Stream
  // ------------------------------------------------------------------
  function connectWebSocket() {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws`);

    ws.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data);
        renderState(state);
      } catch (e) {
        console.error("Invalid WS payload:", e);
      }
    };

    ws.onclose = () => {
      connectionPill.className = "pill";
      connectionText.textContent = "Reconnecting...";
      setTimeout(connectWebSocket, 1500);
    };
  }

  scanPorts();
  connectWebSocket();
})();
