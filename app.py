import os
import sys
import time
import math
import threading
from dataclasses import dataclass

import serial
from serial.tools import list_ports
from flask import Flask, request, jsonify, send_file

# =========================================================
# SERIAL + DEVICE CONFIG
# =========================================================
BAUD = 9600
ADDR = 0x01

PORT_OVERRIDE = None              # e.g. "COM6" to force
PORT_KEYWORD = "USB Serial Port"  # adapter is the same model as your current setup

# =========================================================
# CALIBRATION (CONFIRMED)
# =========================================================
AZ_HOME_DEG = 175.0
EL_HORIZON_DEG = 32.0
EL_MAX_DEG = 55.0                # safe "max" elevation used for demo arc

# =========================================================
# PASS GEOMETRY (SAFE FRONT SWEEP)
# =========================================================
AZ_MIN_SAFE = 15.0
AZ_MAX_SAFE = 335.0

AZ_START_DEG = 90.0
AZ_END_DEG = 260.0

USE_CENTERED_SWEEP = False
AZ_SWEEP_WIDTH_DEG = 170.0

# =========================================================
# SMOOTHNESS + SPEED TUNING
# =========================================================
UPDATE_HZ = 25.0

PAN_RATE_DEG_S = 6.0
TILT_RATE_DEG_S = 1.50

TARGET_FILTER_ALPHA = 0.12

ENABLE_THRESHOLD = True
AZ_SEND_THRESHOLD_DEG = 0.08
EL_SEND_THRESHOLD_DEG = 0.08

PASS_TIME_MULTIPLIER = 1.0

# =========================================================
# WEB SERVER CONFIG
# =========================================================
HOST = "127.0.0.1"
PORT = 5000

# =========================================================
# Resource handling (works for normal run + PyInstaller)
# =========================================================
def resource_base_dir() -> str:
    """
    Return base directory for resources for both:
    - normal python run
    - PyInstaller (onefile/onedir)
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def resource_path(relative_path: str) -> str:
    return os.path.join(resource_base_dir(), relative_path)

def first_existing_path(*candidates: str) -> str | None:
    for c in candidates:
        p = resource_path(c)
        if os.path.isfile(p):
            return p
    return None

# =========================================================
# Helpers: math + frames
# =========================================================
def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def cosine_ease(x: float) -> float:
    x = clamp(x, 0.0, 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * x)

def pelco_abs_frame(addr: int, cmd2: int, angle_deg: float) -> bytes:
    """
    Pelco-D extended absolute:
      [FF][ADDR][00][CMD2][DATA1][DATA2][CHECKSUM]
    DATA = int(angle_deg * 100) (0.01° units)
    CHECKSUM = (ADDR + 00 + CMD2 + DATA1 + DATA2) & 0xFF
    """
    value = int(round(angle_deg * 100.0))
    value = max(0, min(65535, value))
    d1 = (value >> 8) & 0xFF
    d2 = value & 0xFF
    cmd1 = 0x00
    checksum = (addr + cmd1 + cmd2 + d1 + d2) & 0xFF
    return bytes([0xFF, addr & 0xFF, cmd1, cmd2 & 0xFF, d1, d2, checksum])

def find_port_auto(keyword: str):
    ports = list(list_ports.comports())
    if not ports:
        return None, []
    kw = (keyword or "").lower().strip()
    if kw:
        for p in ports:
            desc = (p.description or "").lower()
            if kw in desc:
                return p.device, ports
    if len(ports) == 1:
        return ports[0].device, ports
    return None, ports

def compute_pass_bounds():
    if not USE_CENTERED_SWEEP:
        a0, a1 = AZ_START_DEG, AZ_END_DEG
    else:
        half = AZ_SWEEP_WIDTH_DEG / 2.0
        a0 = AZ_HOME_DEG - half
        a1 = AZ_HOME_DEG + half

    a0 = clamp(a0, AZ_MIN_SAFE, AZ_MAX_SAFE)
    a1 = clamp(a1, AZ_MIN_SAFE, AZ_MAX_SAFE)

    if a1 <= a0:
        a1 = min(AZ_MAX_SAFE, a0 + 5.0)
    return a0, a1

# =========================================================
# Controller (thread-safe)
# =========================================================
@dataclass
class Status:
    running: bool = False
    message: str = "Idle"
    progress: float = 0.0   # 0..1
    port: str = ""
    baud: int = BAUD
    last_error: str = ""

class PelcoController:
    def __init__(self):
        self._lock = threading.Lock()
        self._ser = None
        self._port = None

        self.status = Status()
        self._worker = None
        self._stop_event = threading.Event()

    def _ensure_serial(self):
        if self._ser and self._ser.is_open:
            return

        port = PORT_OVERRIDE
        ports = []
        if not port:
            port, ports = find_port_auto(PORT_KEYWORD)
            if not port:
                if ports:
                    port = ports[0].device
                else:
                    raise RuntimeError("No serial ports found. Plug in USB-RS485 adapter and try again.")

        self._port = port
        self._ser = serial.Serial(port, baudrate=BAUD, bytesize=8, parity='N', stopbits=1, timeout=0.2)
        time.sleep(0.25)

        self.status.port = port
        self.status.baud = BAUD

    def _write_payload(self, payload: bytes):
        self._ser.write(payload)
        self._ser.flush()

    def _stop_frames(self, repeats=2):
        frame = bytes([0xFF, ADDR, 0x00, 0x00, 0x00, 0x00, (ADDR + 0) & 0xFF])
        for _ in range(repeats):
            self._ser.write(frame)
            self._ser.flush()
            time.sleep(0.01)

    def _home_payload(self) -> bytes:
        return (
            pelco_abs_frame(ADDR, 0x4B, AZ_HOME_DEG) +
            pelco_abs_frame(ADDR, 0x4D, EL_HORIZON_DEG)
        )

    def stop(self):
        """
        Request stop; also push STOP frames immediately.
        """
        with self._lock:
            self._stop_event.set()
            self._ensure_serial()
            self._stop_frames(repeats=2)
        self.status.message = "Stop requested"

    def home_fast(self):
        """
        Fast HOME:
        - stop_event set to prevent further pass writes
        - brief STOP then HOME (AZ+EL) repeated a few times
        """
        with self._lock:
            self._ensure_serial()
            self._stop_event.set()

            self._stop_frames(repeats=2)
            payload = self._home_payload()

            for _ in range(3):
                self._write_payload(payload)
                time.sleep(0.02)

            self.status.message = "Homing fast (North + Horizon)"
            self.status.progress = 0.0

    def start_pass(self, minutes: float):
        minutes = float(minutes)
        if minutes < 5.0:
            raise ValueError("เวลาสาธิตขั้นต่ำ 5 นาที (แนะนำ 5–15 นาที)")

        with self._lock:
            self._ensure_serial()
            if self.status.running:
                raise RuntimeError("Pass is already running.")

            self._stop_event.clear()
            self.status.running = True
            self.status.message = f"Running pass: {minutes:g} min"
            self.status.progress = 0.0
            self.status.last_error = ""

            self._worker = threading.Thread(target=self._run_pass_worker, args=(minutes,), daemon=True)
            self._worker.start()

    def _run_pass_worker(self, minutes: float):
        try:
            with self._lock:
                self._ensure_serial()
                self._stop_frames(repeats=2)
                self._write_payload(self._home_payload())

            time.sleep(0.6)  # settle a bit

            T = max(5.0, minutes * 60.0) * max(0.5, PASS_TIME_MULTIPLIER)
            dt = 1.0 / max(5.0, UPDATE_HZ)

            az0, az1 = compute_pass_bounds()

            cmd_az = az0
            cmd_el = EL_HORIZON_DEG
            filt_az = az0
            filt_el = EL_HORIZON_DEG
            last_sent_az = None
            last_sent_el = None

            alpha = clamp(TARGET_FILTER_ALPHA, 0.01, 1.0)

            t0 = time.time()
            next_tick = t0

            while True:
                if self._stop_event.is_set():
                    break

                now = time.time()
                t = now - t0
                if t >= T:
                    break

                self.status.progress = clamp(t / T, 0.0, 1.0)

                if now < next_tick:
                    time.sleep(0.001)
                    continue
                next_tick += dt

                x = t / T

                s = cosine_ease(x)
                raw_az = az0 + (az1 - az0) * s
                raw_el = EL_HORIZON_DEG + (EL_MAX_DEG - EL_HORIZON_DEG) * math.sin(math.pi * clamp(x, 0.0, 1.0))

                # EMA filter
                filt_az = (1.0 - alpha) * filt_az + alpha * raw_az
                filt_el = (1.0 - alpha) * filt_el + alpha * raw_el

                # Coordinated step
                d_az = filt_az - cmd_az
                d_el = filt_el - cmd_el

                max_step_az = PAN_RATE_DEG_S * dt
                max_step_el = TILT_RATE_DEG_S * dt

                k = 1.0
                if abs(d_az) > 1e-9:
                    k = min(k, max_step_az / abs(d_az))
                if abs(d_el) > 1e-9:
                    k = min(k, max_step_el / abs(d_el))
                k = clamp(k, 0.0, 1.0)

                cmd_az = clamp(cmd_az + k * d_az, AZ_MIN_SAFE, AZ_MAX_SAFE)
                cmd_el = clamp(cmd_el + k * d_el, EL_HORIZON_DEG, EL_MAX_DEG)

                # Threshold decision (as a pair)
                send_pair = True
                if ENABLE_THRESHOLD and (last_sent_az is not None) and (last_sent_el is not None):
                    da = abs(cmd_az - last_sent_az)
                    de = abs(cmd_el - last_sent_el)
                    send_pair = (da >= AZ_SEND_THRESHOLD_DEG) or (de >= EL_SEND_THRESHOLD_DEG)

                if send_pair:
                    payload = (
                        pelco_abs_frame(ADDR, 0x4B, cmd_az) +
                        pelco_abs_frame(ADDR, 0x4D, cmd_el)
                    )
                    with self._lock:
                        if self._stop_event.is_set():
                            break
                        self._write_payload(payload)
                    last_sent_az = cmd_az
                    last_sent_el = cmd_el

            # Finish: FAST HOME
            with self._lock:
                self._stop_frames(repeats=2)
                payload = self._home_payload()
                for _ in range(3):
                    self._write_payload(payload)
                    time.sleep(0.02)
                self._stop_frames(repeats=1)

        except Exception as e:
            self.status.last_error = str(e)
        finally:
            self.status.running = False
            self.status.message = "Stopped" if self._stop_event.is_set() else "Done"
            self.status.progress = 0.0
            self._stop_event.clear()

# =========================================================
# Flask Web App
# =========================================================
app = Flask(__name__)
controller = PelcoController()

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Satellite Pass Simulator</title>
  <style>
    :root{
      --bg: #0b1220;
      --card: rgba(255,255,255,0.08);
      --text: #eaf0ff;
      --muted: rgba(234,240,255,0.72);
      --good: #9cffc6;
      --warn: #ffd79c;
      --bad: #ff9c9c;
      --btn: rgba(255,255,255,0.14);
      --btnHover: rgba(255,255,255,0.20);
      --shadow: 0 12px 40px rgba(0,0,0,0.45);
      --radius: 18px;
    }
    body{
      margin:0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, "Noto Sans Thai", sans-serif;
      background: radial-gradient(1200px 800px at 20% 10%, rgba(124,218,255,0.22), transparent 55%),
                  radial-gradient(1000px 700px at 90% 30%, rgba(156,255,198,0.14), transparent 55%),
                  radial-gradient(900px 600px at 50% 90%, rgba(255,215,156,0.10), transparent 60%),
                  var(--bg);
      color: var(--text);
      min-height: 100vh;
      display:flex;
      align-items:center;
      justify-content:center;
      padding: 18px;
    }
    .wrap{ width:min(900px, 100%); display:grid; gap: 14px; }
    .header{ display:flex; align-items:flex-end; justify-content:space-between; gap: 12px; }
    .title{ font-size: clamp(22px, 3vw, 34px); font-weight: 900; margin:0; line-height:1.1; }
    .subtitle{ margin: 6px 0 0 0; color: var(--muted); font-size: 14px; line-height: 1.4; }
    .chip{
      background: rgba(255,255,255,0.10);
      border: 1px solid rgba(255,255,255,0.12);
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 13px;
      color: var(--muted);
      display:flex; gap: 8px; align-items:center;
      white-space:nowrap;
    }
    .card{
      background: var(--card);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 18px;
    }
    .grid{ display:grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    @media (max-width: 780px){ .grid{ grid-template-columns: 1fr; } }
    .label{ font-size: 13px; color: var(--muted); margin-bottom: 8px; }
    .inputRow{ display:flex; gap: 10px; align-items:center; }
    input[type="number"]{
      width: 220px; max-width: 100%;
      font-size: 22px; font-weight: 800;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.18);
      background: rgba(0,0,0,0.28);
      color: var(--text);
      outline:none;
    }
    .unit{ color: var(--muted); font-size: 18px; font-weight: 800; }
    .btnRow{ display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
    @media (max-width: 520px){ .btnRow{ grid-template-columns: 1fr; } }
    button{
      cursor:pointer;
      border: 1px solid rgba(255,255,255,0.18);
      background: var(--btn);
      color: var(--text);
      padding: 14px 16px;
      border-radius: 16px;
      font-size: 18px;
      font-weight: 900;
      transition: transform 0.05s ease, background 0.2s ease, opacity 0.2s ease;
      user-select:none;
    }
    button:hover{ background: var(--btnHover); }
    button:active{ transform: translateY(1px); }
    button[disabled]{ opacity: 0.5; cursor:not-allowed; }
    .btnStart{ border-color: rgba(124,218,255,0.40); }
    .btnHome{ border-color: rgba(156,255,198,0.35); }
    .btnStop{ border-color: rgba(255,156,156,0.45); }

    .statusBox{ display:flex; gap: 12px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
    .statusText{ display:flex; flex-direction:column; gap: 4px; min-width: 260px; }
    .statusLine{ font-size: 16px; font-weight: 900; }
    .statusMeta{ color: var(--muted); font-size: 13px; }
    .pill{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(255,255,255,0.08);
      color: var(--muted);
      font-size: 13px;
      display:flex; gap:8px; align-items:center;
    }
    .dot{
      width: 10px; height: 10px; border-radius: 99px;
      background: var(--warn);
      box-shadow: 0 0 0 4px rgba(255,215,156,0.10);
    }
    .dot.good{ background: var(--good); box-shadow: 0 0 0 4px rgba(156,255,198,0.12); }
    .dot.bad{ background: var(--bad); box-shadow: 0 0 0 4px rgba(255,156,156,0.10); }

    .barWrap{
      margin-top: 12px;
      background: rgba(255,255,255,0.10);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 999px;
      overflow:hidden;
      height: 16px;
    }
    .bar{
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, rgba(124,218,255,0.85), rgba(156,255,198,0.80));
      transition: width 0.15s ease;
    }
    .hint{ margin-top: 10px; color: var(--muted); font-size: 13px; line-height: 1.6; }
    .err{
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid rgba(255,156,156,0.45);
      background: rgba(255,156,156,0.08);
      color: rgba(255,220,220,0.95);
      font-size: 13px;
      display:none;
      white-space: pre-wrap;
    }
    footer{
      margin-top: 6px;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.06);
      color: rgba(234,240,255,0.78);
      font-size: 12.5px;
      line-height: 1.6;
      text-align: center;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <div>
        <h1 class="title">Satellite Pass Simulator</h1>
        <p class="subtitle">
          กรอกเวลาเป็น “นาที” แล้วกด Start • ปุ่ม Home จะกลับ North + Horizon แบบเร็วที่สุด<br/>
          คำแนะนำการสาธิต: 5–15 นาที
        </p>
      </div>
      <div class="chip" id="chipPort">PORT: - • BAUD: -</div>
    </div>

    <div class="card">
      <div class="grid">
        <div>
          <div class="label">เวลาสาธิต (แนะนำ 5–15 นาที)</div>
          <div class="inputRow">
            <input id="minutes" type="number" min="5" step="1" value="5" />
            <div class="unit">นาที</div>
          </div>
          <div class="hint">
            เริ่มต้นที่ 5 นาทีเพื่อให้เห็นเส้นทางการเคลื่อนที่ครบถ้วน และหากต้องการความชัดเจนมากขึ้นให้เพิ่มเวลาในช่วง 5–15 นาที
          </div>
        </div>

        <div>
          <div class="label">คำสั่ง</div>
          <div class="btnRow">
            <button class="btnHome" id="btnHome">Home</button>
            <button class="btnStart" id="btnStart">Start</button>
            <button class="btnStop" id="btnStop">Stop</button>
          </div>
          <div class="hint">
            ระหว่างหมุน ระบบจะเล่นเสียง <b>ding</b> ทุก 10 วินาที • หากจำเป็นให้กด Stop เพื่อหยุดทันที
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="statusBox">
        <div class="statusText">
          <div class="statusLine" id="statusLine">สถานะ: -</div>
          <div class="statusMeta" id="statusMeta">-</div>
        </div>
        <div class="pill">
          <span class="dot" id="dot"></span>
          <span id="pillText">กำลังตรวจสอบสถานะ...</span>
        </div>
      </div>

      <div class="barWrap">
        <div class="bar" id="bar"></div>
      </div>

      <div class="err" id="errBox"></div>
    </div>

    <footer>
      โครงการส่งเสริมการเรียนรู้ทางด้านโทรคมนาคมในโรงเรียนทั่วประเทศ<br/>
      โดย คณะวิศวกรรมศาสตร์ มหาวิทยาลัยธรรมศาสตร์ และ สถาบันวิจัยและให้คำปรึกษาแห่งมหาวิทยาลัยธรรมศาสตร์<br/><br/>
      สนับสนุนโดย กองทุนวิจัยและพัฒนากิจการกระจายเสียง กิจการโทรทัศน์ และกิจการโทรคมนาคม เพื่อประโยชน์สาธารณะ
    </footer>
  </div>

  <audio id="dingAudio" src="/ding.mp3" preload="auto"></audio>

<script>
  const btnHome = document.getElementById('btnHome');
  const btnStart = document.getElementById('btnStart');
  const btnStop = document.getElementById('btnStop');
  const minutes = document.getElementById('minutes');

  const statusLine = document.getElementById('statusLine');
  const statusMeta = document.getElementById('statusMeta');
  const bar = document.getElementById('bar');
  const dot = document.getElementById('dot');
  const pillText = document.getElementById('pillText');
  const chipPort = document.getElementById('chipPort');
  const errBox = document.getElementById('errBox');

  // ====== DING SOUND ======
  const dingAudio = document.getElementById("dingAudio");
  let dingIntervalId = null;

  async function unlockAudio(){
    try{
      dingAudio.muted = true;
      await dingAudio.play();
      dingAudio.pause();
      dingAudio.currentTime = 0;
      dingAudio.muted = false;
    }catch(e){
      // ignore
    }
  }

  async function playDing(){
    try{
      dingAudio.currentTime = 0;
      await dingAudio.play();
    }catch(e){
      // ignore silently
    }
  }

  function startDingLoop(){
    if(dingIntervalId) return;
    dingIntervalId = setInterval(playDing, 10000);
  }

  function stopDingLoop(){
    if(!dingIntervalId) return;
    clearInterval(dingIntervalId);
    dingIntervalId = null;
  }
  // ========================

  function showError(msg){
    if(!msg){ errBox.style.display = "none"; errBox.textContent = ""; return; }
    errBox.style.display = "block";
    errBox.textContent = msg;
  }

  async function apiPost(url, body){
    const res = await fetch(url, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body || {})
    });
    const data = await res.json().catch(()=> ({}));
    if(!res.ok){
      throw new Error(data.error || ("HTTP " + res.status));
    }
    return data;
  }

  async function apiGet(url){
    const res = await fetch(url);
    const data = await res.json().catch(()=> ({}));
    if(!res.ok){
      throw new Error(data.error || ("HTTP " + res.status));
    }
    return data;
  }

  function setRunningUI(running){
    btnStart.disabled = running;
    minutes.disabled = running;
    btnHome.disabled = false;
    btnStop.disabled = !running;
  }

  async function refreshStatus(){
    try{
      const s = await apiGet("/api/status");
      chipPort.textContent = `PORT: ${s.port || "-"} • BAUD: ${s.baud || "-"}`;
      statusLine.textContent = `สถานะ: ${s.running ? "Running" : "Idle"} — ${s.message || ""}`;
      statusMeta.textContent = s.running ? "กำลังหมุนตามเส้นทางสาธิต" : "พร้อมสาธิต (แนะนำ 5–15 นาที)";

      const p = Math.max(0, Math.min(1, s.progress || 0));
      bar.style.width = (p*100).toFixed(0) + "%";

      if(s.last_error){
        showError("Error:\n" + s.last_error);
      }else{
        showError("");
      }

      if(s.running){
        dot.className = "dot good";
        pillText.textContent = "กำลังทำงาน";
        startDingLoop();
      }else{
        dot.className = "dot";
        pillText.textContent = "พร้อมใช้งาน";
        stopDingLoop();
      }
      setRunningUI(!!s.running);

    }catch(e){
      showError("ไม่สามารถอ่านสถานะได้:\n" + e.message);
      dot.className = "dot bad";
      pillText.textContent = "เชื่อมต่อไม่ได้";
      stopDingLoop();
    }
  }

  btnHome.addEventListener("click", async ()=>{
    try{
      await unlockAudio();
      showError("");
      await apiPost("/api/home", {});
      await refreshStatus();
    }catch(e){
      showError(e.message);
    }
  });

  btnStart.addEventListener("click", async ()=>{
    try{
      await unlockAudio();
      showError("");
      const m = parseFloat(minutes.value);
      if(!(m >= 5)){
        showError("กรุณาใส่เวลาอย่างน้อย 5 นาที (แนะนำ 5–15 นาที)");
        return;
      }
      await apiPost("/api/start", {minutes: m});
      await playDing(); // ding once at start
      await refreshStatus();
    }catch(e){
      showError(e.message);
    }
  });

  btnStop.addEventListener("click", async ()=>{
    try{
      await unlockAudio();
      showError("");
      await apiPost("/api/stop", {});
      stopDingLoop();
      await refreshStatus();
    }catch(e){
      showError(e.message);
    }
  });

  refreshStatus();
  setInterval(refreshStatus, 500);
</script>
</body>
</html>
"""

# =========================================================
# Routes
# =========================================================
@app.get("/")
def index():
    return HTML_PAGE

@app.get("/ding.mp3")
def ding_mp3():
    # Try both root and assets/ for repo hygiene
    p = first_existing_path("ding.mp3", os.path.join("assets", "ding.mp3"))
    if not p:
        return ("ding.mp3 not found. Place it next to app.py or in assets/ding.mp3", 404)
    return send_file(p, mimetype="audio/mpeg")

@app.get("/api/status")
def api_status():
    s = controller.status
    return jsonify({
        "running": s.running,
        "message": s.message,
        "progress": s.progress,
        "port": s.port,
        "baud": s.baud,
        "last_error": s.last_error
    })

@app.post("/api/home")
def api_home():
    try:
        controller.home_fast()
        return jsonify({"ok": True})
    except Exception as e:
        controller.status.last_error = str(e)
        return jsonify({"error": str(e)}), 500

@app.post("/api/start")
def api_start():
    try:
        payload = request.get_json(force=True) or {}
        minutes = payload.get("minutes", None)
        controller.start_pass(minutes)
        return jsonify({"ok": True})
    except Exception as e:
        controller.status.last_error = str(e)
        return jsonify({"error": str(e)}), 500

@app.post("/api/stop")
def api_stop():
    try:
        controller.stop()
        return jsonify({"ok": True})
    except Exception as e:
        controller.status.last_error = str(e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
