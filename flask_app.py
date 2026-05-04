import sqlite3
import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g

app = Flask(__name__)
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

# ---------- PWA Routes ----------
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "PushClash",
        "short_name": "PushClash",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0a0a0a",
        "theme_color": "#ff00ff",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "https://cdn-icons-png.flaticon.com/128/2548/2548538.png", "sizes": "128x128", "type": "image/png"},
            {"src": "https://cdn-icons-png.flaticon.com/192/2548/2548538.png", "sizes": "192x192", "type": "image/png"},
            {"src": "https://cdn-icons-png.flaticon.com/512/2548/2548538.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    })

@app.route('/sw.js')
def service_worker():
    return app.response_class(
        response="""const CACHE_NAME='pushclash-v2';self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE_NAME).then(c=>c.addAll(['/','/manifest.json']))) });self.addEventListener('fetch',e=>{e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request))) });""",
        mimetype='application/javascript'
    )

# ---------- Frontend (Luffy Gear 5 base64 image badge) ----------
FRONTEND_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
<link rel="manifest" href="/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<script>navigator.serviceWorker?.register('/sw.js')</script>
<title>PUSHCLASH 🔥</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box;font-family:'Poppins',sans-serif}
  body{background:#0a0a0a;color:#fff;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:20px;background-image:radial-gradient(circle at 50% 50%,#1a1a1a 0%,#000 100%);overflow-x:hidden}
  .app-container{max-width:450px;width:100%;background:#111;border-radius:28px;padding:24px 20px;box-shadow:0 0 40px rgba(255,0,255,.3),0 0 80px rgba(0,255,255,.2);border:1px solid rgba(0,255,255,.2);position:relative}
  h1{text-align:center;font-size:2.8rem;background:linear-gradient(135deg,#ff5500,#ff00ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}
  .arena-subtitle{text-align:center;color:#aaa;font-size:.9rem;margin-bottom:24px}
  .screen{display:none}.screen.active{display:block}
  .battle-input{width:100%;padding:15px 18px;margin:10px 0;border:1px solid rgba(0,255,255,.4);border-radius:14px;background:rgba(20,20,20,.9);color:#fff;font-size:1rem;outline:none}
  .battle-input:focus{background:#1e1e1e;box-shadow:0 0 15px #0ff;border-color:#0ff}
  .btn-primary{width:100%;padding:16px;margin:12px 0;border:none;border-radius:14px;background:linear-gradient(135deg,#ff5500,#ff00ff);color:#fff;font-weight:bold;font-size:1.2rem;cursor:pointer;box-shadow:0 0 25px rgba(255,0,255,.4);transition:transform .1s}
  .btn-primary:active{transform:scale(.97)}
  .btn-secondary{width:100%;padding:14px;margin:8px 0;border:1px solid #0ff;border-radius:14px;background:transparent;color:#0ff;font-weight:bold;cursor:pointer}
  .timer-big{font-size:5rem;text-align:center;font-weight:800;color:#0ff;text-shadow:0 0 30px cyan}
  .counter-big{font-size:4rem;text-align:center;font-weight:800;color:#f0f}
  .leaderboard-item{display:flex;align-items:center;gap:12px;padding:10px;background:#1a1a1a;border-radius:12px;margin:6px 0}
  .rank{font-size:1.5rem;font-weight:bold;width:40px}.score{margin-left:auto;font-weight:bold;color:#0ff}
  .score-date{font-size:.75rem;color:#888;margin-left:6px}
  .result-msg{text-align:center;font-size:1.3rem;margin:12px 0;font-style:italic;color:#f0f}
  .small{font-size:.85rem;color:#aaa}.share-btn{background:#0ff;color:black}
  video,canvas{width:100%;border-radius:14px;display:none}
  #aiCameraUI{position:relative;width:100%;height:250px;margin:10px 0;border-radius:14px;overflow:hidden}
  #aiCameraUI video,#aiCameraUI canvas{position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover}
  .angle-overlay{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:5rem;font-weight:800;color:#0ff;text-shadow:0 0 30px cyan;pointer-events:none}
  .rep-flash{position:absolute;top:30%;left:50%;transform:translate(-50%,-50%);font-size:3rem;font-weight:800;color:#0f0;animation:fadeInOut .8s ease}
  @keyframes fadeInOut{0%{opacity:0;transform:translate(-50%,-50%) scale(.5)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.2)}100%{opacity:0;transform:translate(-50%,-50%) scale(1)}}
  .debug-msg{position:absolute;bottom:10px;left:10px;background:rgba(0,0,0,.7);color:#fa0;padding:4px 8px;border-radius:6px;font-size:14px;pointer-events:none}

  /* CEO Badge with embedded Luffy image */
  .luffy-badge{position:fixed;top:15px;right:15px;z-index:10000;cursor:pointer;display:flex;flex-direction:column;align-items:center}
  .luffy-img{width:55px;height:55px;border-radius:50%;object-fit:cover;border:2px solid #ff4500;box-shadow:0 0 15px #ff4500,0 0 25px #00bfff}
  .ceo-label{font-size:.7rem;color:#aaa;margin-top:4px;text-align:center}
  .ceo-arrow{position:fixed;top:28px;right:75px;font-size:1.8rem;color:#fa0;animation:arrowBounce .8s ease-in-out infinite;pointer-events:none;z-index:10000}
  @keyframes arrowBounce{0%,100%{transform:translateX(0)}50%{transform:translateX(8px)}}

  /* CEO Modal */
  .ceo-modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);backdrop-filter:blur(10px);z-index:20000;display:none;align-items:center;justify-content:center}
  .ceo-modal-overlay.active{display:flex}
  .ceo-modal{background:#1a1a1a;border-radius:24px;padding:30px 24px;max-width:320px;width:90%;text-align:center;border:1px solid rgba(0,255,255,.3);box-shadow:0 0 40px rgba(0,255,255,.2)}
  .ceo-modal h2{font-size:1.6rem;margin:8px 0;background:linear-gradient(135deg,#ff4500,#00bfff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
  .ceo-modal .title{color:#fa0;font-weight:bold;margin-bottom:10px;font-size:.95rem}
  .ceo-modal .phone{color:#0ff;font-size:1.3rem;margin:8px 0;font-weight:bold}
  .close-btn{background:none;border:1px solid #555;color:#aaa;padding:6px 20px;border-radius:20px;margin-top:18px;cursor:pointer}
</style>
</head>
<body>

<!-- LUFFY GEAR 5 IMAGE BADGE (base64) -->
<div class="luffy-badge" onclick="document.getElementById('ceoModal').classList.add('active')">
  <img class="luffy-img" src="data:image/jpeg;base64,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" alt="Luffy Gear 5">
  <span class="ceo-label">CEO of App</span>
</div>
<div class="ceo-arrow">👉</div>

<!-- CEO Modal -->
<div id="ceoModal" class="ceo-modal-overlay" onclick="this.classList.remove('active')">
  <div class="ceo-modal" onclick="event.stopPropagation()">
    <div style="font-size:2rem;margin-bottom:8px">👑</div>
    <h2>KAUSHTUBH</h2>
    <div class="title">CEO OF PUSH CLASH</div>
    <div style="color:#ccc;font-size:0.9rem;margin:6px 0">Have a query? Get in touch</div>
    <div class="phone">📞 8950592855</div>
    <div style="color:#aaa;font-size:0.7rem">Tap to call (coming soon)</div>
    <button class="close-btn" onclick="document.getElementById('ceoModal').classList.remove('active')">Close</button>
  </div>
</div>

<div class="app-container" id="app">
  <!-- Setup Screen -->
  <div id="setupScreen" class="screen active">
    <h1>PUSHCLASH</h1>
    <div class="arena-subtitle">⚔️ ENTER THE ARENA ⚔️</div>
    <div style="font-size:3rem;text-align:center;margin-bottom:10px">🛡️🔥🛡️</div>
    <input class="battle-input" id="nameInput" placeholder="Your Warrior Name" maxlength="30">
    <input class="battle-input" id="nationalityInput" placeholder="Nationality" maxlength="30">
    <input class="battle-input" id="emailInput" placeholder="Email (your battle ID)" maxlength="50">
    <div class="error-msg" id="setupError"></div>
    <button class="btn-primary" onclick="saveProfile()">⚡ ENTER ARENA ⚡</button>
    <p class="small" style="text-align:center;margin-top:16px">Only real warriors dare to compete</p>
  </div>

  <!-- Dashboard -->
  <div id="dashboardScreen" class="screen">
    <h1>PUSHCLASH</h1>
    <p style="font-size:1.4rem">Welcome, <span id="dashName"></span>!</p>
    <p class="small">🌍 <span id="dashNationality"></span></p>
    <div style="display:flex;gap:12px;margin:20px 0">
      <div style="flex:1;background:#1a1a1a;border-radius:14px;padding:12px;text-align:center"><div style="font-size:2rem;font-weight:bold;color:#0ff" id="personalBest">0</div><div class="small">Personal Best</div></div>
      <div style="flex:1;background:#1a1a1a;border-radius:14px;padding:12px;text-align:center"><div style="font-size:2rem;font-weight:bold;color:#f0f" id="totalBattles">0</div><div class="small">Total Battles</div></div>
    </div>
    <button class="btn-primary" onclick="startChallenge('ai')">🤖 START AI BATTLE</button>
    <button class="btn-secondary" onclick="showLeaderboard()">🏆 Weekly Leaderboard</button>
    <button class="btn-secondary" onclick="resetProfile()">🔄 Leave Arena</button>
    <div class="success-msg" id="saveConfirmation" style="display:none">✅ Score saved to global arena!</div>
  </div>

  <!-- Challenge Screen -->
  <div id="challengeScreen" class="screen">
    <div id="countdownDisplay" class="timer-big" style="font-size:4rem">3</div>
    <div id="challengeActiveUI" style="display:none">
      <div class="timer-big" id="timerDisplay">60</div>
      <div class="counter-big" id="repCounter">0</div>
      <div id="aiCameraUI"><video id="webcam" autoplay playsinline></video><canvas id="poseCanvas"></canvas><div class="angle-overlay" id="angleOverlay"></div><div class="rep-flash" id="repFlash" style="display:none">REP!</div><div class="debug-msg" id="debugMsg"></div></div>
    </div>
    <div id="battleResultUI" style="display:none;text-align:center">
      <h2>⚔️ Battle Over!</h2>
      <div style="font-size:3rem;color:#0ff" id="finalScore">0</div>
      <div class="result-msg" id="trashTalk"></div>
      <div class="champion-voice-text" id="championText" style="display:none">“Champions are built in losses, my friend. Come back stronger.”</div>
      <button class="btn-primary" onclick="shareScore()">📢 Share My Score</button>
      <button class="btn-secondary" onclick="goToDashboard()">Back to Arena</button>
    </div>
  </div>

  <!-- Leaderboard Screen -->
  <div id="leaderboardScreen" class="screen">
    <h1>WEEKLY RANKINGS</h1>
    <p class="small" style="text-align:center">Top 10 of the last 7 days</p>
    <div id="leaderboardList"></div>
    <button class="btn-secondary" onclick="goToDashboard()" style="margin-top:16px">← Back to Arena</button>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4"></script>
<script src="https://cdn.jsdelivr.net/npm/@tensorflow-models/pose-detection@2"></script>
<script>
  let currentUser = null, repCount = 0, timeLeft = 60, challengeInterval, countdownInterval, challengeMode = 'ai', aiDetector = null, aiStream = null;
  const trashTalks = ["Even my grandma does more! 💀","Weak sauce!","Push-up? More like push-over.","Bro, my cat reps more.","Too ez. Next!"];
  const BASE = window.location.origin;

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

  function saveProfile(){
    const n = document.getElementById('nameInput').value.trim();
    const nat = document.getElementById('nationalityInput').value.trim();
    const em = document.getElementById('emailInput').value.trim();
    const err = document.getElementById('setupError');
    if(!n || !nat || !em){ err.textContent = 'All fields are required!'; return; }
    if(!em.includes('@') || !em.includes('.')){ err.textContent = 'Please enter a valid email'; return; }
    err.textContent = '';
    currentUser = {name: n, nationality: nat, email: em};
    localStorage.setItem('pushclash_user', JSON.stringify(currentUser));
    speakWelcome();
    showScreen('dashboardScreen');
    loadStats();
  }

  function resetProfile(){ localStorage.removeItem('pushclash_user'); currentUser=null; showScreen('setupScreen'); }
  function showScreen(id){ document.querySelectorAll('.screen').forEach(e=>e.classList.remove('active')); document.getElementById(id).classList.add('active'); if(id!=='dashboardScreen') document.getElementById('saveConfirmation').style.display='none'; }
  function goToDashboard(){ if(aiStream){ aiStream.getTracks().forEach(t=>t.stop()); aiStream=null; } loadStats(); showScreen('dashboardScreen'); }

  async function loadStats(){
    if(!currentUser) return;
    document.getElementById('dashName').textContent = currentUser.name;
    document.getElementById('dashNationality').textContent = currentUser.nationality;
    const res = await fetch('/api/stats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email: currentUser.email})});
    const data = await res.json();
    document.getElementById('personalBest').textContent = data.personalBest;
    document.getElementById('totalBattles').textContent = data.totalBattles;
  }

  async function startChallenge(mode){
    challengeMode = mode;
    showScreen('challengeScreen');
    document.getElementById('countdownDisplay').style.display='block';
    document.getElementById('challengeActiveUI').style.display='none';
    document.getElementById('battleResultUI').style.display='none';
    repCount = 0;
    let count=3;
    document.getElementById('countdownDisplay').textContent = count;
    countdownInterval = setInterval(()=>{
      count--;
      if(count===0){
        document.getElementById('countdownDisplay').textContent='GO!';
        setTimeout(()=>{ clearInterval(countdownInterval); document.getElementById('countdownDisplay').style.display='none'; startActiveChallenge(); }, 400);
      } else { document.getElementById('countdownDisplay').textContent = count; }
    }, 800);
  }

  async function startActiveChallenge(){
    timeLeft = 60;
    document.getElementById('challengeActiveUI').style.display='block';
    document.getElementById('timerDisplay').textContent = timeLeft;
    document.getElementById('repCounter').textContent = '0';
    document.getElementById('aiCameraUI').style.display='block';
    document.getElementById('debugMsg').textContent = '📷 Camera starting...';
    await startAICamera();
    challengeInterval = setInterval(()=>{
      timeLeft--;
      document.getElementById('timerDisplay').textContent = timeLeft;
      if(timeLeft<=0){ clearInterval(challengeInterval); endBattle(); }
    }, 1000);
  }

  let angleBuffer = [], lastRepTime = 0, aiState = 'up';
  async function startAICamera(){
    const video = document.getElementById('webcam'), canvas = document.getElementById('poseCanvas'), ctx = canvas.getContext('2d'), debugMsg = document.getElementById('debugMsg');
    try {
      aiStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
      video.srcObject = aiStream; await video.play();
      debugMsg.textContent = '📹 Camera active, loading AI...';
    } catch(e) { debugMsg.textContent = '❌ Camera access denied!'; return; }
    video.addEventListener('loadedmetadata', ()=>{ canvas.width = video.videoWidth; canvas.height = video.videoHeight; });
    try {
      const cfg = { modelType: 'SinglePose.Lightning' };
      aiDetector = await poseDetection.createDetector(poseDetection.SupportedModels.MoveNet, cfg);
      debugMsg.textContent = '✅ AI ready – show yourself!';
    } catch(e) { debugMsg.textContent = '❌ AI model failed to load. Check internet.'; return; }
    angleBuffer = []; lastRepTime = 0; aiState = 'up';
    requestAnimationFrame(detectPose);
  }

  function movingAverage(arr, N){
    const recent = arr.slice(-N);
    if(recent.length===0) return null;
    return recent.reduce((a,b)=>a+b,0)/recent.length;
  }

  async function detectPose(){
    if(timeLeft<=0 || !aiDetector || !aiStream) return;
    const video = document.getElementById('webcam'), canvas = document.getElementById('poseCanvas'), ctx = canvas.getContext('2d'), overlay = document.getElementById('angleOverlay'), debugMsg = document.getElementById('debugMsg');
    if(video.readyState < 2){ requestAnimationFrame(detectPose); return; }
    const poses = await aiDetector.estimatePoses(video, {flipHorizontal: false});
    ctx.clearRect(0,0,canvas.width,canvas.height);
    if(poses.length > 0){
      const kp = poses[0].keypoints; drawSkeleton(ctx, kp);
      const ls = kp[5], rs = kp[6], le = kp[7], lw = kp[9], re = kp[8], rw = kp[10];
      if(ls && le && lw && rs && re && rw){
        const la = calculateAngle(ls,le,lw), ra = calculateAngle(rs,re,rw), raw = (la+ra)/2;
        angleBuffer.push(raw); if(angleBuffer.length>5) angleBuffer.shift();
        const sa = movingAverage(angleBuffer,5);
        if(sa===null){ requestAnimationFrame(detectPose); return; }
        overlay.textContent = Math.round(sa) + '°'; overlay.style.display='block';
        debugMsg.textContent = '🟢 Active – ' + Math.round(sa) + '°';
        const now = Date.now();
        if(aiState==='up' && sa < 90){ aiState = 'down'; }
        else if(aiState==='down' && sa > 160){
          if(now - lastRepTime > 500){
            repCount++; document.getElementById('repCounter').textContent = repCount; lastRepTime = now;
            const flash = document.getElementById('repFlash'); flash.style.display='block'; setTimeout(()=>{ flash.style.display='none'; }, 800);
          }
          aiState = 'up';
        }
      } else {
        overlay.textContent = '?'; overlay.style.display='block';
        debugMsg.textContent = '⚠️ Not all keypoints visible – adjust camera';
      }
    } else {
      overlay.textContent = '?'; overlay.style.display='block';
      debugMsg.textContent = '🔍 Searching for pose...';
    }
    requestAnimationFrame(detectPose);
  }

  function calculateAngle(a,b,c){
    const radians = Math.atan2(c.y-b.y, c.x-b.x) - Math.atan2(a.y-b.y, a.x-b.x);
    let angle = Math.abs(radians * 180.0 / Math.PI);
    if(angle > 180.0) angle = 360 - angle;
    return angle;
  }

  function drawSkeleton(ctx, kp){
    const adj = poseDetection.util.getAdjacentPairs(poseDetection.SupportedModels.MoveNet);
    ctx.strokeStyle = '#0ff'; ctx.lineWidth = 2;
    for(const [p1,p2] of adj){
      if(kp[p1].score > 0.3 && kp[p2].score > 0.3){
        ctx.beginPath(); ctx.moveTo(kp[p1].x, kp[p1].y); ctx.lineTo(kp[p2].x, kp[p2].y); ctx.stroke();
      }
    }
    for(const p of kp){ if(p.score > 0.3){ ctx.fillStyle='#f0f'; ctx.beginPath(); ctx.arc(p.x,p.y,4,0,2*Math.PI); ctx.fill(); } }
  }

  async function endBattle(){
    if(aiStream){ aiStream.getTracks().forEach(t=>t.stop()); aiStream=null; }
    document.getElementById('challengeActiveUI').style.display='none';
    document.getElementById('battleResultUI').style.display='block';
    document.getElementById('finalScore').textContent = repCount;
    document.getElementById('trashTalk').textContent = trashTalks[Math.floor(Math.random()*trashTalks.length)];
    const champ = document.getElementById('championText'); champ.style.display='block'; speakChampion();
    await fetch('/api/battle', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:currentUser.name, nationality:currentUser.nationality, email:currentUser.email, score:repCount})});
    setTimeout(()=>{ champ.style.display='none'; }, 5000);
  }

  function shareScore(){ navigator.clipboard.writeText(`I just did ${repCount} push-ups in PushClash! Can you beat me? 🔥 ${BASE}`).then(()=>alert('Link copied!')); }

  async function showLeaderboard(){
    showScreen('leaderboardScreen');
    const res = await fetch('/api/leaderboard'), data = await res.json(), container = document.getElementById('leaderboardList');
    if(!data.length){ container.innerHTML = '<p style="text-align:center;color:#aaa">No battles in the last 7 days. Be the first!</p>'; return; }
    container.innerHTML = data.map((b,i)=>{
      const emojis = ['🥇','🥈','🥉'], rankDisp = i<3 ? emojis[i] : `#${i+1}`;
      const dateStr = b.date ? ` <span class="score-date">${b.date}</span>` : '';
      return `<div class="leaderboard-item"><span class="rank">${rankDisp}</span><span>${b.name}</span><span class="small">${b.nationality}</span><span class="score">${b.score}${dateStr}</span></div>`;
    }).join('');
  }

  // Init
  currentUser = JSON.parse(localStorage.getItem('pushclash_user'));
  if(currentUser){ showScreen('dashboardScreen'); loadStats(); } else { showScreen('setupScreen'); }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return FRONTEND_HTML

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
