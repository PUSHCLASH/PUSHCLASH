import sqlite3
import os
import base64
import cv2
import numpy as np
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, g
from flask_socketio import SocketIO, emit
import mediapipe as mp
import math
from collections import deque

# ---------- Flask & SocketIO setup ----------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'pushclash-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------- Database setup ----------
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pushclash.db')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.execute("PRAGMA table_info(battles)")
        columns = [row[1] for row in cursor.fetchall()] if cursor else []
        if 'nickname' in columns or 'city' in columns or 'state' in columns:
            db.execute('DROP TABLE IF EXISTS battles')
            db.commit()
        db.execute('''CREATE TABLE IF NOT EXISTS battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            nationality TEXT NOT NULL,
            email TEXT NOT NULL,
            score INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        db.commit()

# ---------- Push‑up counter class ----------
class PushUpCounter:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=2,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6
        )
        self.state = 'up'
        self.rep_count = 0
        self.last_transition_time = 0
        self.angle_buffer = deque(maxlen=5)
        self.angle = 180.0
        self.down_threshold = 85
        self.up_threshold = 155
        self.min_rep_interval = 0.4

    def process_frame(self, frame_rgb, timestamp_ms):
        results = self.pose.process(frame_rgb)
        rep_added = False

        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark

            def get_point(landmark_id):
                lm = landmarks[landmark_id]
                return (lm.x, lm.y) if lm.visibility > 0.5 else None

            left_shoulder = get_point(self.mp_pose.PoseLandmark.LEFT_SHOULDER)
            right_shoulder = get_point(self.mp_pose.PoseLandmark.RIGHT_SHOULDER)
            left_elbow = get_point(self.mp_pose.PoseLandmark.LEFT_ELBOW)
            right_elbow = get_point(self.mp_pose.PoseLandmark.RIGHT_ELBOW)
            left_wrist = get_point(self.mp_pose.PoseLandmark.LEFT_WRIST)
            right_wrist = get_point(self.mp_pose.PoseLandmark.RIGHT_WRIST)

            if left_shoulder and left_elbow and left_wrist and right_shoulder and right_elbow and right_wrist:
                left_angle = self._calculate_angle(left_shoulder, left_elbow, left_wrist)
                right_angle = self._calculate_angle(right_shoulder, right_elbow, right_wrist)
                current_angle = (left_angle + right_angle) / 2.0

                self.angle_buffer.append(current_angle)
                smoothed_angle = np.mean(self.angle_buffer)
                self.angle = smoothed_angle

                now_seconds = timestamp_ms / 1000.0
                if self.state == 'up' and smoothed_angle < self.down_threshold:
                    self.state = 'down'
                elif self.state == 'down' and smoothed_angle > self.up_threshold:
                    if now_seconds - self.last_transition_time > self.min_rep_interval:
                        self.rep_count += 1
                        rep_added = True
                    self.last_transition_time = now_seconds
                    self.state = 'up'

        return rep_added, self.rep_count, self.angle

    def _calculate_angle(self, a, b, c):
        a = np.array(a)
        b = np.array(b)
        c = np.array(c)
        radians = math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0])
        angle = math.degrees(abs(radians))
        if angle > 180.0:
            angle = 360 - angle
        return angle

    def reset(self):
        self.state = 'up'
        self.rep_count = 0
        self.last_transition_time = 0
        self.angle_buffer.clear()
        self.angle = 180.0

# Create a global counter instance (one per server – fine for single-user)
counter = PushUpCounter()

# ---------- WebSocket events ----------
@socketio.on('frame')
def handle_frame(data):
    # data: { image: base64 string, timestamp: ms }
    try:
        img_b64 = data['image'].split(',')[1] if ',' in data['image'] else data['image']
        img_bytes = base64.b64decode(img_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        timestamp = data['timestamp']
        rep_added, total_reps, angle = counter.process_frame(frame_rgb, timestamp)
        emit('update', {
            'rep_added': rep_added,
            'total_reps': total_reps,
            'angle': round(angle, 1)
        })
    except Exception as e:
        print('Frame error:', e)

@socketio.on('start_battle')
def handle_start_battle():
    counter.reset()
    emit('reset_confirmed')

# ---------- HTTP API Endpoints ----------
@app.route('/api/battle', methods=['POST'])
def record_battle():
    data = request.get_json()
    name = data.get('name', '').strip()
    nationality = data.get('nationality', '').strip()
    email = data.get('email', '').strip()
    score = int(data.get('score', 0))
    if not name or not nationality or not email or score <= 0:
        return jsonify({'error': 'Invalid data'}), 400
    db = get_db()
    db.execute('INSERT INTO battles (name, nationality, email, score) VALUES (?, ?, ?, ?)',
               (name, nationality, email, score))
    db.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/leaderboard')
def leaderboard():
    db = get_db()
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    rows = db.execute(
        'SELECT name, nationality, email, score, timestamp FROM battles WHERE timestamp >= ? ORDER BY timestamp DESC',
        (seven_days_ago.strftime('%Y-%m-%d %H:%M:%S'),)
    ).fetchall()
    best_map = {}
    for r in rows:
        email = r['email']
        if email not in best_map or r['score'] > best_map[email]['score']:
            best_map[email] = {
                'name': r['name'],
                'nationality': r['nationality'],
                'score': r['score'],
                'date': r['timestamp']
            }
    sorted_best = sorted(best_map.values(), key=lambda x: x['score'], reverse=True)[:10]
    result = []
    for entry in sorted_best:
        date_str = ''
        if entry['date']:
            try:
                dt = datetime.strptime(entry['date'], '%Y-%m-%d %H:%M:%S')
                date_str = dt.strftime('%b %d')
            except:
                pass
        result.append({
            'name': entry['name'],
            'nationality': entry['nationality'],
            'score': entry['score'],
            'date': date_str
        })
    return jsonify(result)

@app.route('/api/stats', methods=['POST'])
def user_stats():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'totalBattles': 0, 'personalBest': 0, 'rank': '-'})
    db = get_db()
    total = db.execute('SELECT COUNT(*) as total FROM battles WHERE email=?', (email,)).fetchone()['total']
    best = db.execute('SELECT MAX(score) as best FROM battles WHERE email=?', (email,)).fetchone()['best'] or 0
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    rank_row = db.execute('''
        SELECT COUNT(DISTINCT email) + 1 as rank FROM battles
        WHERE timestamp >= ? AND score > (SELECT COALESCE(MAX(score),0) FROM battles WHERE email=? AND timestamp >= ?)
    ''', (seven_days_ago.strftime('%Y-%m-%d %H:%M:%S'), email, seven_days_ago.strftime('%Y-%m-%d %H:%M:%S'))).fetchone()
    rank = rank_row['rank'] if rank_row else '-'
    return jsonify({'totalBattles': total, 'personalBest': best, 'rank': rank})

# ---------- Serve the HTML page (embedded, containing the client-side WebSocket logic) ----------
FRONTEND_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
  <title>PUSHCLASH 🔥</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; font-family:'Poppins', sans-serif; }
    body {
      background: #0a0a0a;
      color: #fff;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 20px;
      background-image: radial-gradient(circle at 50% 50%, #1a1a1a 0%, #000000 100%);
      overflow-x: hidden;
    }
    .app-container {
      max-width: 450px;
      width: 100%;
      background: #111;
      border-radius: 28px;
      padding: 24px 20px;
      box-shadow: 0 0 40px rgba(255,0,255,0.3), 0 0 80px rgba(0,255,255,0.2);
      border: 1px solid rgba(0,255,255,0.2);
    }
    h1 {
      text-align: center;
      font-size: 2.8rem;
      background: linear-gradient(135deg, #ff5500, #ff00ff);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
      text-shadow: 0 0 20px #ff00ff;
      letter-spacing: 2px;
    }
    .arena-subtitle {
      text-align: center;
      color: #aaa;
      font-size: 0.9rem;
      margin-bottom: 24px;
      letter-spacing: 1px;
    }
    .screen { display: none; }
    .screen.active { display: block; }
    .battle-input {
      width: 100%;
      padding: 15px 18px;
      margin: 10px 0;
      border: 1px solid rgba(0,255,255,0.4);
      border-radius: 14px;
      background: rgba(20,20,20,0.9);
      color: white;
      font-size: 1rem;
      outline: none;
      transition: 0.3s;
    }
    .battle-input:focus {
      background: #1e1e1e;
      box-shadow: 0 0 15px #00ffff;
      border-color: #00ffff;
    }
    .btn-primary {
      width: 100%;
      padding: 16px;
      margin: 12px 0;
      border: none;
      border-radius: 14px;
      background: linear-gradient(135deg, #ff5500, #ff00ff);
      color: #fff;
      font-weight: bold;
      font-size: 1.2rem;
      cursor: pointer;
      box-shadow: 0 0 25px rgba(255,0,255,0.4);
      transition: transform 0.1s, box-shadow 0.2s;
      letter-spacing: 1px;
    }
    .btn-primary:active { transform: scale(0.97); }
    .btn-secondary {
      width: 100%;
      padding: 14px;
      margin: 8px 0;
      border: 1px solid #00ffff;
      border-radius: 14px;
      background: transparent;
      color: #00ffff;
      font-weight: bold;
      cursor: pointer;
      transition: 0.2s;
    }
    .btn-secondary:hover { background: rgba(0,255,255,0.1); }
    .timer-big { font-size:5rem; text-align:center; font-weight:800; color:#00ffff; text-shadow:0 0 30px cyan; }
    .counter-big { font-size:4rem; text-align:center; font-weight:800; color:#ff00ff; }
    .tabs { display:flex; gap:8px; margin:16px 0; }
    .tab { flex:1; text-align:center; padding:10px; background:#1e1e1e; border-radius:12px; cursor:pointer; font-weight:bold; }
    .tab.active { background:#00ffff; color:black; }
    .leaderboard-item { display:flex; align-items:center; gap:12px; padding:10px; background:#1a1a1a; border-radius:12px; margin:6px 0; }
    .rank { font-size:1.5rem; font-weight:bold; width:40px; }
    .score { margin-left:auto; font-weight:bold; color:#00ffff; }
    .score-date { font-size:0.75rem; color:#888; margin-left:6px; }
    .result-msg { text-align:center; font-size:1.3rem; margin:12px 0; font-style:italic; color:#ff00ff; }
    .champion-voice-text {
      text-align: center;
      font-size: 1.1rem;
      color: #ff5500;
      font-weight: bold;
      margin: 12px 0;
      animation: fadeInUp 1s ease;
    }
    @keyframes fadeInUp {
      0% { opacity: 0; transform: translateY(20px); }
      100% { opacity: 1; transform: translateY(0); }
    }
    .share-btn { background:#00ffff; color:black; }
    .small { font-size:0.85rem; color:#aaa; }
    nav { display:flex; gap:10px; margin:16px 0; }
    nav button { flex:1; font-size:0.8rem; padding:10px; }
    video, canvas { width:100%; border-radius:14px; display:none; }
    #aiCameraUI { position:relative; width:100%; height:250px; margin:10px 0; border-radius:14px; overflow:hidden; }
    #aiCameraUI video { display:block; position:absolute; top:0; left:0; width:100%; height:100%; object-fit:cover; }
    .mode-choice { display:flex; gap:10px; margin:20px 0; }
    .mode-choice button { flex:1; }
    .arena-shield {
      font-size: 3rem;
      text-align: center;
      margin-bottom: 10px;
      filter: drop-shadow(0 0 20px #ff00ff);
    }
    .error-msg { color: #ff4444; font-size: 0.8rem; text-align: center; margin: 5px 0; }
    .success-msg { color: #00ff88; font-size: 0.9rem; text-align: center; margin: 10px 0; }
    .angle-overlay {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      font-size: 5rem;
      font-weight: 800;
      color: #00ffff;
      text-shadow: 0 0 30px cyan;
      pointer-events: none;
    }
    .rep-flash {
      position: absolute;
      top: 30%;
      left: 50%;
      transform: translate(-50%, -50%);
      font-size: 3rem;
      font-weight: 800;
      color: #00ff00;
      text-shadow: 0 0 30px #00ff00;
      pointer-events: none;
      animation: fadeInOut 0.8s ease;
    }
    @keyframes fadeInOut {
      0% { opacity: 0; transform: translate(-50%, -50%) scale(0.5); }
      50% { opacity: 1; transform: translate(-50%, -50%) scale(1.2); }
      100% { opacity: 0; transform: translate(-50%, -50%) scale(1); }
    }
  </style>
</head>
<body>
<div class="app-container" id="app">
  <!-- Setup Screen -->
  <div id="setupScreen" class="screen active">
    <h1>PUSHCLASH</h1>
    <div class="arena-subtitle">⚔️ ENTER THE ARENA ⚔️</div>
    <div class="arena-shield">🛡️🔥🛡️</div>
    <input class="battle-input" type="text" id="nameInput" placeholder="Your Warrior Name" maxlength="30">
    <input class="battle-input" type="text" id="nationalityInput" placeholder="Nationality (e.g. Indian, American)" maxlength="30">
    <input class="battle-input" type="email" id="emailInput" placeholder="Email (your battle ID)" maxlength="50">
    <div class="error-msg" id="setupError"></div>
    <button class="btn-primary" onclick="saveProfile()">⚡ ENTER ARENA ⚡</button>
    <p class="small" style="text-align:center; margin-top:16px;">Only real warriors dare to compete</p>
  </div>

  <!-- Dashboard Screen -->
  <div id="dashboardScreen" class="screen">
    <h1>PUSHCLASH</h1>
    <p style="font-size:1.4rem;">Welcome, <span id="dashName"></span>!</p>
    <p class="small">🌍 <span id="dashNationality"></span></p>
    <div style="display:flex; gap:12px; margin:20px 0;">
      <div style="flex:1; background:#1a1a1a; border-radius:14px; padding:12px; text-align:center;">
        <div style="font-size:2rem; font-weight:bold; color:#00ffff;" id="personalBest">0</div>
        <div class="small">Personal Best</div>
      </div>
      <div style="flex:1; background:#1a1a1a; border-radius:14px; padding:12px; text-align:center;">
        <div style="font-size:2rem; font-weight:bold; color:#ff00ff;" id="totalBattles">0</div>
        <div class="small">Total Battles</div>
      </div>
    </div>
    <button class="btn-primary" onclick="startChallenge()">🤖 START AI BATTLE</button>
    <button class="btn-secondary" onclick="showLeaderboard()">🏆 Weekly Leaderboard</button>
    <button class="btn-secondary" onclick="resetProfile()">🔄 Leave Arena</button>
    <div class="success-msg" id="saveConfirmation" style="display:none;">✅ Score saved to global arena!</div>
  </div>

  <!-- Challenge Screen -->
  <div id="challengeScreen" class="screen">
    <div id="countdownDisplay" class="timer-big" style="font-size:4rem;">3</div>
    <div id="challengeActiveUI" style="display:none;">
      <div class="timer-big" id="timerDisplay">60</div>
      <div class="counter-big" id="repCounter">0</div>
      <div id="aiCameraUI">
        <video id="webcam" autoplay playsinline></video>
      </div>
      <div class="angle-overlay" id="angleOverlay"></div>
      <div class="rep-flash" id="repFlash" style="display:none;">REP!</div>
    </div>
    <div id="battleResultUI" style="display:none; text-align:center;">
      <h2>⚔️ Battle Over!</h2>
      <div style="font-size:3rem; color:#00ffff;" id="finalScore">0</div>
      <div class="result-msg" id="trashTalk"></div>
      <div class="champion-voice-text" id="championText" style="display:none;">“Champions are built in losses, my friend. Come back stronger.”</div>
      <button class="btn-primary" onclick="shareScore()">📢 Share My Score</button>
      <button class="btn-secondary" onclick="goToDashboard()">Back to Arena</button>
    </div>
  </div>

  <!-- Leaderboard Screen -->
  <div id="leaderboardScreen" class="screen">
    <h1>WEEKLY RANKINGS</h1>
    <p class="small" style="text-align:center;">Top 10 of the last 7 days</p>
    <div id="leaderboardList"></div>
    <button class="btn-secondary" onclick="goToDashboard()" style="margin-top:16px;">← Back to Arena</button>
  </div>
</div>

<!-- Socket.IO client library -->
<script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>

<script>
  let currentUser = null;
  let repCount = 0;
  let timeLeft = 60;
  let challengeInterval, countdownInterval;
  let socket;
  let streaming = false;
  let localStream = null;

  const trashTalks = ["Even my grandma does more! 💀","Weak sauce!","Push-up? More like push-over.","Bro, my cat reps more.","Too ez. Next!"];
  const BASE = window.location.origin;

  // ---------- Voice functions ----------
  function speakWelcome() {
    const msg = new SpeechSynthesisUtterance("Welcome to PushClash. This is the world where people battle for fitness.");
    msg.lang = 'en-US'; msg.rate = 0.9; msg.pitch = 1.1;
    const voices = speechSynthesis.getVoices();
    const femaleVoice = voices.find(v => v.name.toLowerCase().includes('female') || v.name.toLowerCase().includes('samantha') || v.name.toLowerCase().includes('google uk female') || v.name.toLowerCase().includes('microsoft zira'));
    if (femaleVoice) msg.voice = femaleVoice;
    speechSynthesis.speak(msg);
  }
  function speakChampion() {
    const msg = new SpeechSynthesisUtterance("Champions are built in losses, my friend. Come back stronger.");
    msg.lang = 'en-US'; msg.rate = 0.85; msg.pitch = 0.8;
    const voices = speechSynthesis.getVoices();
    const maleVoice = voices.find(v => v.name.toLowerCase().includes('male') || v.name.toLowerCase().includes('google uk male') || v.name.toLowerCase().includes('microsoft david') || v.name.toLowerCase().includes('daniel'));
    if (maleVoice) msg.voice = maleVoice;
    speechSynthesis.speak(msg);
  }

  // ---------- User & navigation ----------
  function saveProfile(){
    const name = document.getElementById('nameInput').value.trim();
    const nationality = document.getElementById('nationalityInput').value.trim();
    const email = document.getElementById('emailInput').value.trim();
    const errorDiv = document.getElementById('setupError');
    if(!name || !nationality || !email) { errorDiv.textContent = 'All fields are required!'; return; }
    if(!email.includes('@') || !email.includes('.')) { errorDiv.textContent = 'Please enter a valid email'; return; }
    errorDiv.textContent = '';
    currentUser = {name, nationality, email};
    localStorage.setItem('pushclash_user', JSON.stringify(currentUser));
    speakWelcome();
    showScreen('dashboardScreen');
    loadStats();
  }
  function resetProfile(){
    localStorage.removeItem('pushclash_user');
    currentUser=null;
    showScreen('setupScreen');
  }
  function showScreen(id){
    document.querySelectorAll('.screen').forEach(el=>el.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    if(id !== 'dashboardScreen') {
      const conf = document.getElementById('saveConfirmation');
      if(conf) conf.style.display = 'none';
    }
  }
  function goToDashboard(){
    stopStreaming();
    loadStats();
    showScreen('dashboardScreen');
  }
  async function loadStats(){
    if(!currentUser) return;
    document.getElementById('dashName').textContent = currentUser.name;
    document.getElementById('dashNationality').textContent = currentUser.nationality;
    const res = await fetch('/api/stats', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email: currentUser.email})
    });
    const data = await res.json();
    document.getElementById('personalBest').textContent = data.personalBest;
    document.getElementById('totalBattles').textContent = data.totalBattles;
  }

  // ---------- Challenge start ----------
  async function startChallenge() {
    showScreen('challengeScreen');
    document.getElementById('countdownDisplay').style.display='block';
    document.getElementById('challengeActiveUI').style.display='none';
    document.getElementById('battleResultUI').style.display='none';
    repCount = 0;
    let count=3;
    document.getElementById('countdownDisplay').textContent=count;
    countdownInterval = setInterval(()=>{
      count--;
      if(count===0){
        document.getElementById('countdownDisplay').textContent='GO!';
        setTimeout(()=>{
          clearInterval(countdownInterval);
          document.getElementById('countdownDisplay').style.display='none';
          startActiveChallenge();
        },400);
      } else {
        document.getElementById('countdownDisplay').textContent=count;
      }
    },800);
  }

  async function startActiveChallenge(){
    timeLeft=60;
    document.getElementById('challengeActiveUI').style.display='block';
    document.getElementById('timerDisplay').textContent=timeLeft;
    document.getElementById('repCounter').textContent='0';
    document.getElementById('aiCameraUI').style.display='block';

    // Connect to WebSocket and start sending frames
    socket = io();
    socket.on('connect', () => {
      socket.emit('start_battle');
    });
    socket.on('update', (data) => {
      if (data.total_reps !== repCount) {
        repCount = data.total_reps;
        document.getElementById('repCounter').textContent = repCount;
        if (data.rep_added) {
          const flash = document.getElementById('repFlash');
          flash.style.display = 'block';
          setTimeout(() => { flash.style.display = 'none'; }, 800);
        }
      }
      document.getElementById('angleOverlay').textContent = Math.round(data.angle) + '°';
      document.getElementById('angleOverlay').style.display = 'block';
    });

    // Start webcam and streaming
    try {
      localStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: {ideal: 320}, height: {ideal: 240} } });
      const video = document.getElementById('webcam');
      video.srcObject = localStream;
      await video.play();
      streaming = true;
      captureAndSend();
    } catch(e) {
      alert('Camera access denied or not available.');
    }

    challengeInterval = setInterval(()=>{
      timeLeft--;
      document.getElementById('timerDisplay').textContent=timeLeft;
      if(timeLeft<=0){
        clearInterval(challengeInterval);
        endBattle();
      }
    },1000);
  }

  function captureAndSend() {
    if (!streaming) return;
    const video = document.getElementById('webcam');
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 320;
    canvas.height = video.videoHeight || 240;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataURL = canvas.toDataURL('image/jpeg', 0.6);
    socket.emit('frame', { image: dataURL, timestamp: Date.now() });
    requestAnimationFrame(captureAndSend);
  }

  function stopStreaming() {
    streaming = false;
    if (localStream) {
      localStream.getTracks().forEach(track => track.stop());
      localStream = null;
    }
    if (socket) {
      socket.disconnect();
      socket = null;
    }
  }

  async function endBattle(){
    stopStreaming();
    document.getElementById('challengeActiveUI').style.display='none';
    document.getElementById('battleResultUI').style.display='block';
    document.getElementById('finalScore').textContent = repCount;
    document.getElementById('trashTalk').textContent = trashTalks[Math.floor(Math.random()*trashTalks.length)];
    const championDiv = document.getElementById('championText');
    championDiv.style.display = 'block';
    speakChampion();

    await fetch('/api/battle', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        name: currentUser.name,
        nationality: currentUser.nationality,
        email: currentUser.email,
        score: repCount
      })
    });
    setTimeout(() => { championDiv.style.display = 'none'; }, 5000);
  }

  function shareScore(){
    const text = `I just did ${repCount} push-ups in PushClash! Can you beat me? 🔥 ${BASE}`;
    navigator.clipboard.writeText(text).then(()=>alert('Link copied!'));
  }

  async function showLeaderboard(){
    showScreen('leaderboardScreen');
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    const container = document.getElementById('leaderboardList');
    if(!data.length){
      container.innerHTML = '<p style="text-align:center;color:#aaa;">No battles in the last 7 days. Be the first!</p>';
      return;
    }
    container.innerHTML = data.map((b,i)=>{
      const emojis = ['🥇','🥈','🥉'];
      const rankDisp = i<3 ? emojis[i] : `#${i+1}`;
      const dateStr = b.date ? ` <span class="score-date">${b.date}</span>` : '';
      return `<div class="leaderboard-item">
        <span class="rank">${rankDisp}</span>
        <span>${b.name}</span>
        <span class="small">${b.nationality}</span>
        <span class="score">${b.score}${dateStr}</span>
      </div>`;
    }).join('');
  }

  // Init
  currentUser = JSON.parse(localStorage.getItem('pushclash_user'));
  if(currentUser){
    showScreen('dashboardScreen');
    loadStats();
  } else {
    showScreen('setupScreen');
  }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return FRONTEND_HTML

# ---------- Start server ----------
if __name__ == '__main__':
    with app.app_context():
        init_db()
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
