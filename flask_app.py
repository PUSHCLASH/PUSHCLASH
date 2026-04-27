import sqlite3
import os
from flask import Flask, request, jsonify, g

# ---------- App definition ----------
app = Flask(__name__)

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
        # New schema: name, nationality, email
        db.execute('''CREATE TABLE IF NOT EXISTS battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            nationality TEXT NOT NULL,
            email TEXT NOT NULL,
            score INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        db.commit()

# ---------- API Endpoints ----------
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
    # Global leaderboard – top 10 by max score per player (using email as unique)
    rows = db.execute(
        'SELECT name, nationality, MAX(score) as max_score FROM battles GROUP BY email ORDER BY max_score DESC LIMIT 10')
    result = [{'name': r['name'], 'nationality': r['nationality'], 'score': r['max_score']} for r in rows]
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
    rank_row = db.execute('''
        SELECT COUNT(DISTINCT email) + 1 as rank FROM battles b1
        WHERE b1.score > (SELECT COALESCE(MAX(score),0) FROM battles b2 WHERE b2.email=?)
    ''', (email,)).fetchone()
    rank = rank_row['rank'] if rank_row else '-'
    return jsonify({'totalBattles': total, 'personalBest': best, 'rank': rank})

# ---------- Frontend (Battle‑themed, AI voice welcome) ----------
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

    /* Battle‑theme inputs */
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
    .result-msg { text-align:center; font-size:1.3rem; margin:12px 0; font-style:italic; color:#ff00ff; }
    .share-btn { background:#00ffff; color:black; }
    .small { font-size:0.85rem; color:#aaa; }
    nav { display:flex; gap:10px; margin:16px 0; }
    nav button { flex:1; font-size:0.8rem; padding:10px; }
    video, canvas { width:100%; border-radius:14px; display:none; }
    #aiCameraUI { position:relative; width:100%; height:250px; margin:10px 0; border-radius:14px; overflow:hidden; }
    #aiCameraUI video, #aiCameraUI canvas { display:block; position:absolute; top:0; left:0; width:100%; height:100%; object-fit:cover; }
    .mode-choice { display:flex; gap:10px; margin:20px 0; }
    .mode-choice button { flex:1; }

    /* Battle background elements */
    .arena-shield {
      font-size: 3rem;
      text-align: center;
      margin-bottom: 10px;
      filter: drop-shadow(0 0 20px #ff00ff);
    }
    .error-msg {
      color: #ff4444;
      font-size: 0.8rem;
      text-align: center;
      margin: 5px 0;
    }
  </style>
</head>
<body>
<div class="app-container" id="app">
  <!-- Setup Screen (Battle Arena Entry) -->
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

  <!-- Dashboard -->
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
    <button class="btn-primary" onclick="startChallenge('ai')">🤖 START AI BATTLE</button>
    <button class="btn-secondary" onclick="showLeaderboard()">🏆 Global Leaderboard</button>
    <button class="btn-secondary" onclick="resetProfile()">🔄 Leave Arena</button>
  </div>

  <!-- Challenge Screen -->
  <div id="challengeScreen" class="screen">
    <div id="countdownDisplay" class="timer-big" style="font-size:4rem;">3</div>
    <div id="challengeActiveUI" style="display:none;">
      <div class="timer-big" id="timerDisplay">60</div>
      <div class="counter-big" id="repCounter">0</div>
      <div id="aiCameraUI">
        <video id="webcam" autoplay playsinline></video>
        <canvas id="poseCanvas"></canvas>
      </div>
    </div>
    <div id="battleResultUI" style="display:none; text-align:center;">
      <h2>⚔️ Battle Over!</h2>
      <div style="font-size:3rem; color:#00ffff;" id="finalScore">0</div>
      <div class="result-msg" id="trashTalk"></div>
      <button class="btn-primary" onclick="shareScore()">📢 Share My Score</button>
      <button class="btn-secondary" onclick="goToDashboard()">Back to Arena</button>
    </div>
  </div>

  <!-- Leaderboard Screen -->
  <div id="leaderboardScreen" class="screen">
    <h1>GLOBAL RANKINGS</h1>
    <div id="leaderboardList"></div>
    <button class="btn-secondary" onclick="goToDashboard()" style="margin-top:16px;">← Back to Arena</button>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4"></script>
<script src="https://cdn.jsdelivr.net/npm/@tensorflow-models/pose-detection@2"></script>

<script>
  let currentUser = null;  // {name, nationality, email}
  let repCount = 0;
  let timeLeft = 60;
  let challengeInterval, countdownInterval;
  let challengeMode = 'ai';
  let aiDetector = null;
  let aiStream = null;
  let aiRepState = 'up';
  let aiLastRepTime = 0;
  const trashTalks = ["Even my grandma does more! 💀","Weak sauce!","Push-up? More like push-over.","Bro, my cat reps more.","Too ez. Next!"];
  const BASE = window.location.origin;

  // ---------- AI Voice function ----------
  function speakWelcome() {
    const msg = new SpeechSynthesisUtterance("Welcome to PushClash. This is the world where people battle for fitness.");
    msg.lang = 'en-US';
    msg.rate = 0.9;     // slightly slower for warmth
    msg.pitch = 1.1;    // a little higher for feminine tone

    // Try to select a female voice
    const voices = speechSynthesis.getVoices();
    const femaleVoice = voices.find(v => v.name.toLowerCase().includes('female') || v.name.toLowerCase().includes('samantha') || v.name.toLowerCase().includes('google uk female') || v.name.toLowerCase().includes('microsoft zira'));
    if (femaleVoice) msg.voice = femaleVoice;

    speechSynthesis.speak(msg);
  }

  // ---------- Profile & Navigation ----------
  function saveProfile(){
    const name = document.getElementById('nameInput').value.trim();
    const nationality = document.getElementById('nationalityInput').value.trim();
    const email = document.getElementById('emailInput').value.trim();
    const errorDiv = document.getElementById('setupError');

    // Basic validation
    if(!name || !nationality || !email) {
      errorDiv.textContent = 'All fields are required!';
      return;
    }
    // Simple email check
    if(!email.includes('@') || !email.includes('.')) {
      errorDiv.textContent = 'Please enter a valid email';
      return;
    }
    errorDiv.textContent = '';
    currentUser = {name, nationality, email};
    localStorage.setItem('pushclash_user', JSON.stringify(currentUser));

    // Speak the welcome message
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
  }

  function goToDashboard(){
    if (aiStream) {
      aiStream.getTracks().forEach(track => track.stop());
      aiStream = null;
    }
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

  // ---------- Challenge Start (AI only) ----------
  async function startChallenge(mode) {
    challengeMode = mode;
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
    // Only AI mode
    document.getElementById('aiCameraUI').style.display='block';
    await startAICamera();

    challengeInterval = setInterval(()=>{
      timeLeft--;
      document.getElementById('timerDisplay').textContent=timeLeft;
      if(timeLeft<=0){
        clearInterval(challengeInterval);
        endBattle();
      }
    },1000);
  }

  // ---------- AI Camera (shoulder stability only) ----------
  let lastShoulderY = null;

  async function startAICamera() {
    const video = document.getElementById('webcam');
    const canvas = document.getElementById('poseCanvas');
    const ctx = canvas.getContext('2d');

    aiStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
    video.srcObject = aiStream;
    await video.play();

    video.addEventListener('loadedmetadata', () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
    });

    const detectorConfig = { modelType: 'SinglePose.Lightning' };
    aiDetector = await poseDetection.createDetector(poseDetection.SupportedModels.MoveNet, detectorConfig);

    aiRepState = 'up';
    aiLastRepTime = Date.now();
    window._aiDownStart = null;
    lastShoulderY = null;
    requestAnimationFrame(detectPose);
  }

  async function detectPose() {
    if (timeLeft <= 0 || !aiDetector || !aiStream) return;

    const video = document.getElementById('webcam');
    const canvas = document.getElementById('poseCanvas');
    const ctx = canvas.getContext('2d');

    if (video.readyState < 2) {
      requestAnimationFrame(detectPose);
      return;
    }

    const poses = await aiDetector.estimatePoses(video, { flipHorizontal: false });
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (poses.length > 0) {
      const keypoints = poses[0].keypoints;
      drawSkeleton(ctx, keypoints);

      const leftShoulder = keypoints[5];
      const rightShoulder = keypoints[6];
      const leftElbow = keypoints[7];
      const leftWrist = keypoints[9];
      const rightElbow = keypoints[8];
      const rightWrist = keypoints[10];

      const shoulderY = (leftShoulder && rightShoulder ? (leftShoulder.y + rightShoulder.y) / 2 : null);
      if (shoulderY !== null) {
        if (lastShoulderY === null) lastShoulderY = shoulderY;
        const movement = Math.abs(shoulderY - lastShoulderY);
        lastShoulderY = shoulderY;

        const stable = movement <= 80;

        ctx.font = 'bold 20px Poppins';
        ctx.fillStyle = stable ? '#00ff00' : '#ff0000';
        ctx.fillText(stable ? 'Stable' : 'Unstable', 20, 200);

        if (!stable) {
          window._aiDownStart = null;
          aiRepState = 'up';
          requestAnimationFrame(detectPose);
          return;
        }

        if (leftShoulder && leftElbow && leftWrist && rightShoulder && rightElbow && rightWrist) {
          const leftAngle = calculateAngle(leftShoulder, leftElbow, leftWrist);
          const rightAngle = calculateAngle(rightShoulder, rightElbow, rightWrist);
          const avgAngle = (leftAngle + rightAngle) / 2;
          const now = Date.now();

          ctx.fillStyle = '#00ffff';
          ctx.fillText(`Angle: ${Math.round(avgAngle)}°`, 20, 40);

          if (aiRepState === 'up') {
            if (avgAngle < 95) {
              if (!window._aiDownStart) window._aiDownStart = now;
              const heldDuration = now - window._aiDownStart;
              ctx.fillStyle = '#ffaa00';
              ctx.fillText(`Hold down ${(heldDuration/1000).toFixed(1)}s`, 20, 80);
              if (heldDuration >= 300) {
                aiRepState = 'down';
                window._aiDownStart = null;
                ctx.fillStyle = '#ff00ff';
                ctx.fillText('DOWN - push up now!', 20, 80);
              }
            } else {
              window._aiDownStart = null;
            }
          } else if (aiRepState === 'down') {
            if (avgAngle > 145) {
              if (now - aiLastRepTime > 800) {
                repCount++;
                document.getElementById('repCounter').textContent = repCount;
                aiLastRepTime = now;
                ctx.fillStyle = '#00ff00';
                ctx.fillText('REP COUNTED!', 20, 120);
                aiRepState = 'up';
                window._aiDownStart = null;
              } else {
                ctx.fillStyle = '#ffff00';
                ctx.fillText('Too fast', 20, 120);
              }
            } else {
              ctx.fillStyle = '#ff00ff';
              ctx.fillText('DOWN - push up now!', 20, 80);
            }
          }

          ctx.fillStyle = '#ffffff';
          ctx.fillText(`State: ${aiRepState}`, 20, 160);
        }
      }
    }

    requestAnimationFrame(detectPose);
  }

  function calculateAngle(a, b, c) {
    const radians = Math.atan2(c.y - b.y, c.x - b.x) - Math.atan2(a.y - b.y, a.x - b.x);
    let angle = Math.abs(radians * 180.0 / Math.PI);
    if (angle > 180.0) angle = 360 - angle;
    return angle;
  }

  function drawSkeleton(ctx, keypoints) {
    const adjacentKeyPoints = poseDetection.util.getAdjacentPairs(poseDetection.SupportedModels.MoveNet);
    ctx.strokeStyle = '#00ffff';
    ctx.lineWidth = 2;
    for (const pair of adjacentKeyPoints) {
      const p1 = keypoints[pair[0]];
      const p2 = keypoints[pair[1]];
      if (p1.score > 0.3 && p2.score > 0.3) {
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }
    }
    for (const kp of keypoints) {
      if (kp.score > 0.3) {
        ctx.fillStyle = '#ff00ff';
        ctx.beginPath();
        ctx.arc(kp.x, kp.y, 4, 0, 2 * Math.PI);
        ctx.fill();
      }
    }
  }

  // ---------- End Battle ----------
  async function endBattle(){
    if (aiStream) {
      aiStream.getTracks().forEach(track => track.stop());
      aiStream = null;
    }
    document.getElementById('challengeActiveUI').style.display='none';
    document.getElementById('battleResultUI').style.display='block';
    document.getElementById('finalScore').textContent = repCount;
    document.getElementById('trashTalk').textContent = trashTalks[Math.floor(Math.random()*trashTalks.length)];

    // Save to server
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
  }

  function shareScore(){
    const text = `I just did ${repCount} push-ups in PushClash! Can you beat me? 🔥 ${BASE}`;
    navigator.clipboard.writeText(text).then(()=>alert('Link copied!'));
  }

  // ---------- Leaderboard (global, no tabs) ----------
  async function showLeaderboard(){
    showScreen('leaderboardScreen');
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    const container = document.getElementById('leaderboardList');
    if(!data.length){
      container.innerHTML = '<p style="text-align:center;color:#aaa;">No battles yet. Be the first!</p>';
      return;
    }
    container.innerHTML = data.map((b,i)=>{
      const emojis = ['🥇','🥈','🥉'];
      const rankDisp = i<3 ? emojis[i] : `#${i+1}`;
      return `<div class="leaderboard-item">
        <span class="rank">${rankDisp}</span>
        <span>${b.name}</span>
        <span class="small">${b.nationality}</span>
        <span class="score">${b.score}</span>
      </div>`;
    }).join('');
  }

  // Init on load
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

# ---------- Create tables on startup ----------
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
