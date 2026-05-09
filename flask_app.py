import os
import time
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, g
from threading import Lock

app = Flask(__name__)

# ---------- Active user tracking (10-second inactivity) ----------
active_users = {}
active_users_lock = Lock()
INACTIVITY_LIMIT = 10

def update_active_user(email):
    with active_users_lock:
        active_users[email] = time.time()

def cleanup_active_users():
    now = time.time()
    with active_users_lock:
        stale = [email for email, t in active_users.items() if now - t > INACTIVITY_LIMIT]
        for email in stale:
            del active_users[email]

def get_active_count():
    cleanup_active_users()
    with active_users_lock:
        return len(active_users)

# ---------- Database connection ----------
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL, sslmode='require')
        g.db.cursor_factory = psycopg2.extras.DictCursor
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS battles (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                nationality TEXT NOT NULL,
                email TEXT NOT NULL,
                score INTEGER NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            )
        ''')
        db.commit()

# ---------- API Endpoints ----------
@app.route('/api/check-email', methods=['POST'])
def check_email():
    data = request.get_json()
    email = data.get('email', '').strip()
    if not email:
        return jsonify({'exists': False})
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT COUNT(*) FROM battles WHERE email = %s', (email,))
    exists = cur.fetchone()[0] > 0
    return jsonify({'exists': exists})

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
    cur = db.cursor()
    cur.execute(
        'INSERT INTO battles (name, nationality, email, score) VALUES (%s, %s, %s, %s)',
        (name, nationality, email, score)
    )
    db.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/leaderboard')
def leaderboard():
    db = get_db()
    cur = db.cursor()
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    cur.execute('''
        SELECT name, nationality, email, score, timestamp
        FROM battles
        WHERE timestamp >= %s
        ORDER BY timestamp DESC
    ''', (seven_days_ago,))
    rows = cur.fetchall()

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
                dt = entry['date']
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
    if email:
        update_active_user(email)
    if not email:
        return jsonify({'totalBattles': 0, 'personalBest': 0, 'rank': '-'})
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT COUNT(*) FROM battles WHERE email = %s', (email,))
    total = cur.fetchone()[0]
    cur.execute('SELECT MAX(score) FROM battles WHERE email = %s', (email,))
    best = cur.fetchone()[0] or 0
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    cur.execute('''
        SELECT COUNT(DISTINCT email) + 1 FROM battles
        WHERE timestamp >= %s AND score > (
            SELECT COALESCE(MAX(score), 0) FROM battles WHERE email = %s AND timestamp >= %s
        )
    ''', (seven_days_ago, email, seven_days_ago))
    rank_row = cur.fetchone()
    rank = rank_row[0] if rank_row else '-'
    return jsonify({'totalBattles': total, 'personalBest': best, 'rank': rank})

@app.route('/api/active_users')
def active_users_endpoint():
    return jsonify({'count': get_active_count()})

# ---------- PWA Routes (unchanged) ----------
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
        response="""const CACHE_NAME='pushclash-v5';self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE_NAME).then(c=>c.addAll(['/','/manifest.json']))) });self.addEventListener('fetch',e=>{e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request))) });self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE_NAME).map(k=>caches.delete(k)))));});""",
        mimetype='application/javascript'
    )

# ---------- Frontend (unchanged, except saveProfile now checks email duplicate) ----------
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
  video,canvas{width:100%;border-radius:14px;background:#000}
  #aiCameraUI{position:relative;width:100%;height:250px;margin:10px 0;border-radius:14px;overflow:hidden;background:#000;display:block}
  #aiCameraUI video{display:block;position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;z-index:2}
  #aiCameraUI canvas{display:block;position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;z-index:3}
  .angle-overlay{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:5rem;font-weight:800;color:#0ff;text-shadow:0 0 30px cyan;pointer-events:none;z-index:5}
  .rep-flash{position:absolute;top:30%;left:50%;transform:translate(-50%,-50%);font-size:3rem;font-weight:800;color:#0f0;text-shadow:0 0 30px green;z-index:6;animation:fadeInOut .8s ease}
  @keyframes fadeInOut{0%{opacity:0;transform:translate(-50%,-50%) scale(.5)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.2)}100%{opacity:0;transform:translate(-50%,-50%) scale(1)}}
  .debug-msg{position:absolute;bottom:10px;left:10px;background:rgba(0,0,0,.8);color:#fa0;padding:6px 12px;border-radius:8px;font-size:16px;font-weight:bold;z-index:7;pointer-events:none}

  /* CEO Badge */
  .luffy-badge{position:fixed;top:15px;right:15px;z-index:10000;cursor:pointer;display:flex;flex-direction:column;align-items:center}
  .luffy-img{width:70px;height:70px;border-radius:50%;object-fit:cover;border:none;box-shadow:0 0 15px rgba(0,191,255,0.6),0 0 30px rgba(255,69,0,0.4)}
  .ceo-label{font-size:.7rem;color:#ddd;margin-top:6px;background:rgba(0,0,0,0.7);padding:3px 10px;border-radius:12px;text-align:center}
  .ceo-arrow{position:fixed;top:30px;right:90px;font-size:1.8rem;color:#fff;animation:arrowBounce .8s ease-in-out infinite;pointer-events:none;z-index:10000;filter:drop-shadow(0 0 6px rgba(255,255,255,0.8))}
  @keyframes arrowBounce{0%,100%{transform:translateX(0)}50%{transform:translateX(8px)}}

  /* Active Users Pill */
  .active-users-pill{position:fixed;top:15px;left:15px;z-index:10000;display:flex;align-items:center;gap:6px;background:rgba(0,0,0,0.7);backdrop-filter:blur(8px);padding:6px 12px;border-radius:20px;border:1px solid rgba(0,255,255,0.4);box-shadow:0 0 12px rgba(0,255,255,0.3)}
  .active-users-pill .user-icon{font-size:1.2rem;}
  .active-users-pill .count{font-weight:bold;font-size:1rem;color:#0ff}

  /* CEO Modal */
  .ceo-modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);backdrop-filter:blur(10px);z-index:20000;display:none;align-items:center;justify-content:center}
  .ceo-modal-overlay.active{display:flex}
  .ceo-modal{background:#1a1a1a;border-radius:24px;padding:30px 24px;max-width:320px;width:90%;text-align:center;border:1px solid rgba(0,255,255,.3);box-shadow:0 0 40px rgba(0,255,255,.2)}
  .ceo-modal h2{font-size:1.6rem;margin:8px 0;background:linear-gradient(135deg,#ff4500,#00bfff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
  .ceo-modal .title{color:#fa0;font-weight:bold;margin-bottom:10px;font-size:.95rem}
  .ceo-modal .phone{color:#0ff;font-size:1.3rem;margin:8px 0;font-weight:bold}
  .close-btn{background:none;border:1px solid #555;color:#aaa;padding:6px 20px;border-radius:20px;margin-top:18px;cursor:pointer}

  /* Instruction screen */
  .instruction-box{background:rgba(0,0,0,0.8);border-radius:20px;padding:20px;margin:20px 0}
  .instruction-box p{font-size:1rem;line-height:1.8;margin:8px 0;color:#ddd}
  .instruction-box .emoji{font-size:1.3rem}
  .checkbox-row{display:flex;align-items:center;gap:12px;margin:20px 0;justify-content:center}
  .checkbox-row input{width:20px;height:20px;accent-color:#ff4500}
  .checkbox-row label{font-size:0.9rem;color:#ccc}
</style>
</head>
<body>

<!-- ACTIVE USERS PILL (top-left) -->
<div class="active-users-pill" id="activeUsersPill">
  <span class="user-icon">👥</span>
  <span class="count" id="activeUserCount">0</span>
  <span style="font-size:0.8rem;color:#aaa">online</span>
</div>

<!-- LUFFY GEAR 5 BADGE -->
<div class="luffy-badge" onclick="document.getElementById('ceoModal').classList.add('active')">
  <img class="luffy-img" src="https://raw.githubusercontent.com/PUSHCLASH/PUSHCLASH/main/luffy%20image.jpeg" alt="Luffy Gear 5">
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

  <!-- Instruction Screen -->
  <div id="instructionScreen" class="screen">
    <h1 style="font-size:2rem;margin-bottom:20px">🚀 WELCOME, WARRIOR!</h1>
    <div class="instruction-box">
      <p><span class="emoji">🤖</span> PushClash is an <strong>AI fitness battlefield</strong> where you crush push‑ups and your reps are counted live by our AI referee.</p>
      <p><span class="emoji">⏱️</span> You get <strong>60 seconds</strong> to do as many clean push‑ups as possible. Every rep counts, every second matters.</p>
      <p><span class="emoji">🏆</span> Your best score hits the <strong>Weekly Global Leaderboard</strong>. Rise up, own your nation, become the #1 push‑up legend.</p>
      <p><span class="emoji">👑</span> This app was built with pure hustle by <strong>Kaushtubh (CEO)</strong>. Tap the Luffy badge anytime to see who's running the show.</p>
      <p><span class="emoji">🔥</span> No mercy, no shortcuts. Only raw power brings glory. Ready to turn your body into a weapon?</p>
    </div>
    <div class="checkbox-row">
      <input type="checkbox" id="agreeCheck">
      <label for="agreeCheck">I have read all instructions carefully</label>
    </div>
    <button class="btn-primary" id="enterArenaBtn" disabled onclick="showScreen('dashboardScreen'); loadStats(); speakWelcome();">⚡ I'M READY, ENTER ARENA ⚡</button>
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
      <div id="aiCameraUI">
        <video id="webcam" autoplay playsinline></video>
        <canvas id="poseCanvas"></canvas>
        <div class="angle-overlay" id="angleOverlay"></div>
        <div class="rep-flash" id="repFlash" style="display:none">REP!</div>
        <div class="debug-msg" id="debugMsg"></div>
      </div>
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
  // -------------------- GLOBALS --------------------
  let currentUser = null, repCount = 0, timeLeft = 60, challengeInterval, countdownInterval, challengeMode = 'ai', aiDetector = null, aiStream = null;
  const trashTalks = ["Even my grandma does more! 💀","Weak sauce!","Push-up? More like push-over.","Bro, my cat reps more.","Too ez. Next!"];
  const BASE = window.location.origin;

  // ---------- Active user count updater ----------
  async function refreshActiveCount() {
    try {
      const res = await fetch('/api/active_users');
      const data = await res.json();
      document.getElementById('activeUserCount').textContent = data.count;
    } catch(e) {}
  }
  setInterval(refreshActiveCount, 10000);
  window.addEventListener('load', refreshActiveCount);

  // -------------------- VOICE HELPERS --------------------
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

  // -------------------- USER FLOW (with duplicate email check) --------------------
  async function saveProfile(){
    const n = document.getElementById('nameInput').value.trim();
    const nat = document.getElementById('nationalityInput').value.trim();
    const em = document.getElementById('emailInput').value.trim();
    const err = document.getElementById('setupError');
    if(!n || !nat || !em){ err.textContent = 'All fields are required!'; return; }
    if(!em.includes('@') || !em.includes('.')){ err.textContent = 'Please enter a valid email'; return; }

    // Check if email already exists in the database
    const checkRes = await fetch('/api/check-email', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email: em})
    });
    const checkData = await checkRes.json();
    if(checkData.exists){
      err.textContent = 'This email is already registered. Please use a different email or contact the CEO to recover your account.';
      return;
    }

    err.textContent = '';
    currentUser = {name: n, nationality: nat, email: em};
    localStorage.setItem('pushclash_user', JSON.stringify(currentUser));
    fetch('/api/stats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email: em})});
    showScreen('instructionScreen');
  }

  document.getElementById('agreeCheck').addEventListener('change', function() {
    document.getElementById('enterArenaBtn').disabled = !this.checked;
  });

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
    refreshActiveCount();
  }

  // -------------------- CHALLENGE START --------------------
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
    if(currentUser) fetch('/api/stats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email: currentUser.email})});
  }

  // -------------------- AI CAMERA (NO RESOLUTION CONSTRAINTS) --------------------
  let angleBuffer = [], lastRepTime = 0, aiState = 'up';

  async function startAICamera(){
    const video = document.getElementById('webcam');
    const canvas = document.getElementById('poseCanvas');
    const ctx = canvas.getContext('2d');
    const debugMsg = document.getElementById('debugMsg');

    try {
      aiStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
      video.srcObject = aiStream;
      await video.play();
      debugMsg.textContent = '✅ AI ready – show yourself!';
    } catch(e) {
      debugMsg.textContent = '❌ Camera access denied! Please allow camera in settings.';
      return;
    }

    video.addEventListener('loadedmetadata', () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
    });

    try {
      const cfg = { modelType: 'SinglePose.Lightning' };
      aiDetector = await poseDetection.createDetector(poseDetection.SupportedModels.MoveNet, cfg);
    } catch(e) {
      debugMsg.textContent = '❌ AI model failed to load. Check your internet.';
      return;
    }

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

        overlay.textContent = Math.round(sa) + '°';
        overlay.style.display = 'block';
        debugMsg.textContent = '🟢 Active – ' + Math.round(sa) + '°';

        const now = Date.now();
        if(aiState==='up' && sa < 90){
          aiState = 'down';
        } else if(aiState==='down' && sa > 160){
          if(now - lastRepTime > 500){
            repCount++;
            document.getElementById('repCounter').textContent = repCount;
            lastRepTime = now;
            const flash = document.getElementById('repFlash');
            flash.style.display = 'block';
            setTimeout(()=>{ flash.style.display='none'; }, 800);
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

  // -------------------- END BATTLE --------------------
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
