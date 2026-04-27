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
        db.execute('''CREATE TABLE IF NOT EXISTS battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            score INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        db.commit()

# ---------- API Endpoints ----------
@app.route('/api/battle', methods=['POST'])
def record_battle():
    data = request.get_json()
    nickname = data.get('nickname', '').strip()
    city = data.get('city', '').strip()
    state = data.get('state', '').strip()
    score = int(data.get('score', 0))
    if not nickname or not city or not state or score <= 0:
        return jsonify({'error': 'Invalid data'}), 400
    db = get_db()
    db.execute('INSERT INTO battles (nickname, city, state, score) VALUES (?, ?, ?, ?)',
               (nickname, city, state, score))
    db.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/leaderboard')
def leaderboard():
    level = request.args.get('level', 'national')
    city = request.args.get('city', '')
    state = request.args.get('state', '')
    db = get_db()
    if level == 'local' and city:
        rows = db.execute(
            'SELECT nickname, city, state, MAX(score) as max_score FROM battles WHERE city = ? GROUP BY nickname, city, state ORDER BY max_score DESC LIMIT 10',
            (city,))
    elif level == 'state' and state:
        rows = db.execute(
            'SELECT nickname, city, state, MAX(score) as max_score FROM battles WHERE state = ? GROUP BY nickname, city, state ORDER BY max_score DESC LIMIT 10',
            (state,))
    else:
        rows = db.execute(
            'SELECT nickname, city, state, MAX(score) as max_score FROM battles GROUP BY nickname, city, state ORDER BY max_score DESC LIMIT 10')
    result = [{'nickname': r['nickname'], 'city': r['city'], 'state': r['state'], 'score': r['max_score']} for r in rows]
    return jsonify(result)

@app.route('/api/stats', methods=['POST'])
def user_stats():
    data = request.get_json()
    nickname = data.get('nickname')
    city = data.get('city')
    state = data.get('state')
    db = get_db()
    total = db.execute('SELECT COUNT(*) as total FROM battles WHERE nickname=? AND city=? AND state=?',
                       (nickname, city, state)).fetchone()['total']
    best = db.execute('SELECT MAX(score) as best FROM battles WHERE nickname=? AND city=? AND state=?',
                      (nickname, city, state)).fetchone()['best'] or 0
    rank_row = db.execute('''
        SELECT COUNT(DISTINCT nickname) + 1 as rank FROM battles b1
        WHERE b1.city = ? AND b1.score > (SELECT COALESCE(MAX(score),0) FROM battles b2 WHERE b2.nickname=? AND b2.city=? AND b2.state=?)
    ''', (city, nickname, city, state)).fetchone()
    rank = rank_row['rank'] if rank_row else 1
    return jsonify({'totalBattles': total, 'personalBest': best, 'cityRank': rank})

# ---------- Frontend (shoulder stability only, no plank check) ----------
FRONTEND_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
  <title>PUSHCLASH 🔥</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; font-family:'Poppins', sans-serif; }
    body { background:#0a0a0a; color:#fff; min-height:100vh; display:flex; justify-content:center; align-items:center; padding:20px; }
    .app-container { max-width:450px; width:100%; background:#111; border-radius:28px; padding:24px 20px; box-shadow:0 0 30px rgba(0,255,255,0.15); }
    h1 { text-align:center; font-size:2.4rem; background:linear-gradient(135deg, #00ffff, #ff00ff); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:16px; }
    .screen { display:none; }
    .screen.active { display:block; }
    input, button { width:100%; padding:15px 18px; margin:8px 0; border:none; border-radius:14px; font-size:1rem; background:#1e1e1e; color:white; outline:none; }
    input:focus { background:#2a2a2a; box-shadow:0 0 8px #00ffff; }
    button { background:linear-gradient(135deg, #00ffff, #ff00ff); color:#000; font-weight:bold; cursor:pointer; box-shadow:0 0 18px rgba(0,255,255,0.3); }
    button:active { transform:scale(0.97); }
    button.secondary { background:#2a2a2a; color:white; box-shadow:none; }
    .timer-big { font-size:5rem; text-align:center; font-weight:800; color:#00ffff; text-shadow:0 0 30px cyan; }
    .counter-big { font-size:4rem; text-align:center; font-weight:800; color:#ff00ff; }
    .tap-btn { width:160px; height:160px; border-radius:50%; font-size:2.2rem; font-weight:bold; margin:20px auto; display:flex; align-items:center; justify-content:center; background:conic-gradient(from 0deg, #00ffff, #ff00ff, #00ffff); color:black; box-shadow:0 0 40px rgba(255,0,255,0.5); cursor:pointer; user-select:none; }
    .tap-btn:active { transform:scale(0.9); }
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
  </style>
</head>
<body>
<div class="app-container" id="app">
  <h1>PUSHCLASH</h1>
  <!-- Setup -->
  <div id="setupScreen" class="screen active">
    <p style="text-align:center; margin-bottom:12px;">Enter your battle identity</p>
    <input type="text" id="nicknameInput" placeholder="Nickname" maxlength="20">
    <input type="text" id="cityInput" placeholder="City" maxlength="30">
    <input type="text" id="stateInput" placeholder="State" maxlength="30">
    <button onclick="saveProfile()">⚡ Enter Arena</button>
  </div>
  <!-- Dashboard -->
  <div id="dashboardScreen" class="screen">
    <p style="font-size:1.4rem;">Welcome, <span id="dashNickname"></span>!</p>
    <p class="small">📍 <span id="dashLocation"></span></p>
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
    <div class="mode-choice">
      <button onclick="startChallenge('manual')">👆 Manual Tap</button>
      <button onclick="startChallenge('ai')">🤖 AI Camera</button>
    </div>
    <button class="secondary" onclick="showLeaderboard('local')">🏆 Leaderboard</button>
    <button class="secondary" onclick="resetProfile()">🔄 Reset Identity</button>
  </div>
  <!-- Challenge -->
  <div id="challengeScreen" class="screen">
    <div id="countdownDisplay" class="timer-big" style="font-size:4rem;">3</div>
    <div id="challengeActiveUI" style="display:none;">
      <div class="timer-big" id="timerDisplay">60</div>
      <div class="counter-big" id="repCounter">0</div>
      <!-- Manual UI -->
      <div id="manualUI" style="display:none;">
        <div class="tap-btn" id="tapButton">REP</div>
        <p style="text-align:center; color:#aaa;">Tap or press spacebar</p>
      </div>
      <!-- AI UI -->
      <div id="aiCameraUI" style="display:none;">
        <video id="webcam" autoplay playsinline></video>
        <canvas id="poseCanvas"></canvas>
      </div>
    </div>
    <div id="battleResultUI" style="display:none; text-align:center;">
      <h2>⚔️ Battle Over!</h2>
      <div style="font-size:3rem; color:#00ffff;" id="finalScore">0</div>
      <div class="result-msg" id="trashTalk"></div>
      <button class="share-btn" onclick="shareScore()">📢 Share My Score</button>
      <button onclick="goToDashboard()" style="margin-top:10px;">Back to Dashboard</button>
    </div>
  </div>
  <!-- Leaderboard -->
  <div id="leaderboardScreen" class="screen">
    <div class="tabs">
      <div class="tab active" onclick="switchTab('local')">🏙️ Local</div>
      <div class="tab" onclick="switchTab('state')">🗺️ State</div>
      <div class="tab" onclick="switchTab('national')">🌍 National</div>
    </div>
    <div id="leaderboardList"></div>
    <button class="secondary" onclick="goToDashboard()" style="margin-top:16px;">← Back</button>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4"></script>
<script src="https://cdn.jsdelivr.net/npm/@tensorflow-models/pose-detection@2"></script>

<script>
  let currentUser = null;
  let repCount = 0;
  let timeLeft = 60;
  let challengeInterval, countdownInterval;
  let challengeMode = 'manual';
  let aiDetector = null;
  let aiStream = null;
  let aiRepState = 'up';
  let aiLastRepTime = 0;
  const trashTalks = ["Even my grandma does more! 💀","Weak sauce!","Push-up? More like push-over.","Bro, my cat reps more.","Too ez. Next!"];
  const BASE = window.location.origin;

  // ---------- Profile & Navigation ----------
  function saveProfile(){
    const n=document.getElementById('nicknameInput').value.trim();
    const c=document.getElementById('cityInput').value.trim();
    const s=document.getElementById('stateInput').value.trim();
    if(!n||!c||!s) return alert('Fill all fields!');
    currentUser = {nickname:n,city:c,state:s};
    localStorage.setItem('pushclash_user', JSON.stringify(currentUser));
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
    document.getElementById('dashNickname').textContent=currentUser.nickname;
    document.getElementById('dashLocation').textContent=`${currentUser.city}, ${currentUser.state}`;
    const res = await fetch('/api/stats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(currentUser)});
    const data = await res.json();
    document.getElementById('personalBest').textContent = data.personalBest;
    document.getElementById('totalBattles').textContent = data.totalBattles;
  }

  // ---------- Challenge Start ----------
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

    if (challengeMode === 'manual') {
      document.getElementById('manualUI').style.display='block';
      document.getElementById('aiCameraUI').style.display='none';
      document.getElementById('tapButton').onmousedown = function(e){ e.preventDefault(); tapRep(); };
      document.getElementById('tapButton').ontouchstart = function(e){ e.preventDefault(); tapRep(); };
      document.addEventListener('keydown', spaceHandler);
    } else {
      document.getElementById('manualUI').style.display='none';
      document.getElementById('aiCameraUI').style.display='block';
      await startAICamera();
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

  function tapRep(){ if(timeLeft<=0) return; repCount++; document.getElementById('repCounter').textContent=repCount; }
  function spaceHandler(e){ if(e.code==='Space'){ e.preventDefault(); tapRep(); } }

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

      // ---- Shoulder stability check ----
      const shoulderY = (leftShoulder && rightShoulder ? (leftShoulder.y + rightShoulder.y) / 2 : null);
      if (shoulderY !== null) {
        if (lastShoulderY === null) lastShoulderY = shoulderY;
        const movement = Math.abs(shoulderY - lastShoulderY);
        lastShoulderY = shoulderY;

        const stable = movement <= 80;

        ctx.font = 'bold 20px Poppins';
        ctx.fillStyle = stable ? '#00ff00' : '#ff0000';
        ctx.fillText(stable ? 'Stable' : 'Unstable', 20, 200);

        // If not stable, reset and skip counting
        if (!stable) {
          window._aiDownStart = null;
          aiRepState = 'up';
          requestAnimationFrame(detectPose);
          return;
        }

        // ---- Elbow angle counting (only if stable) ----
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
    document.removeEventListener('keydown', spaceHandler);
    if (aiStream) {
      aiStream.getTracks().forEach(track => track.stop());
      aiStream = null;
    }
    document.getElementById('challengeActiveUI').style.display='none';
    document.getElementById('battleResultUI').style.display='block';
    document.getElementById('finalScore').textContent=repCount;
    document.getElementById('trashTalk').textContent=trashTalks[Math.floor(Math.random()*trashTalks.length)];
    await fetch('/api/battle', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...currentUser, score:repCount})});
  }

  function shareScore(){
    const text = `I just did ${repCount} push-ups in PushClash! Can you beat me? 🔥 ${BASE}`;
    navigator.clipboard.writeText(text).then(()=>alert('Link copied!'));
  }

  // ---------- Leaderboard ----------
  async function showLeaderboard(tab){
    showScreen('leaderboardScreen');
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
    event.target.classList.add('active');
    let level = tab;
    let params = new URLSearchParams({level});
    if(level==='local' && currentUser) params.append('city', currentUser.city);
    if(level==='state' && currentUser) params.append('state', currentUser.state);
    const res = await fetch(`/api/leaderboard?${params.toString()}`);
    const data = await res.json();
    const container = document.getElementById('leaderboardList');
    if(!data.length){ container.innerHTML='<p style="text-align:center;color:#aaa;">No battles yet. Be the first!</p>'; return; }
    container.innerHTML = data.map((b,i)=>{
      const emojis = ['🥇','🥈','🥉'];
      const rankDisp = i<3 ? emojis[i] : `#${i+1}`;
      return `<div class="leaderboard-item"><span class="rank">${rankDisp}</span><span>${b.nickname}</span><span class="small">${b.city}</span><span class="score">${b.score}</span></div>`;
    }).join('');
  }

  function switchTab(tab){ showLeaderboard(tab); }

  // Init
  currentUser = JSON.parse(localStorage.getItem('pushclash_user'));
  if(currentUser){ showScreen('dashboardScreen'); loadStats(); }
  else { showScreen('setupScreen'); }
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
