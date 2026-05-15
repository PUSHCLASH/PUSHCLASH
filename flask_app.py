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

# ---------- API Endpoints (ALL UNCHANGED) ----------
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
        return jsonify({'totalBattles': 0, 'personalBest': 0, 'rank': '-', 'totalPushups': 0, 'recentBattles': []})
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT COUNT(*) FROM battles WHERE email = %s', (email,))
    total = cur.fetchone()[0]
    cur.execute('SELECT MAX(score) FROM battles WHERE email = %s', (email,))
    best = cur.fetchone()[0] or 0
    cur.execute('SELECT COALESCE(SUM(score), 0) FROM battles WHERE email = %s', (email,))
    total_pushups = cur.fetchone()[0]
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    cur.execute('''
        SELECT COUNT(DISTINCT email) + 1 FROM battles
        WHERE timestamp >= %s AND score > (
            SELECT COALESCE(MAX(score), 0) FROM battles WHERE email = %s AND timestamp >= %s
        )
    ''', (seven_days_ago, email, seven_days_ago))
    rank_row = cur.fetchone()
    rank = rank_row[0] if rank_row else '-'
    cur.execute('SELECT score, timestamp FROM battles WHERE email = %s ORDER BY timestamp DESC LIMIT 10', (email,))
    recent = [{'score': r['score'], 'date': r['timestamp'].strftime('%b %d %H:%M')} for r in cur.fetchall()]
    return jsonify({
        'totalBattles': total,
        'personalBest': best,
        'rank': rank,
        'totalPushups': total_pushups,
        'recentBattles': recent
    })

@app.route('/api/streak')
def streak():
    email = request.args.get('email', '').strip()
    if not email:
        return jsonify({'streak': 0, 'lastDate': None})
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT DISTINCT DATE(timestamp) as day FROM battles WHERE email = %s ORDER BY day DESC LIMIT 60', (email,))
    days = [r['day'] for r in cur.fetchall()]
    if not days:
        return jsonify({'streak': 0, 'lastDate': None})
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    if days[0] not in (today, yesterday):
        return jsonify({'streak': 0, 'lastDate': str(days[0])})
    streak = 1
    for i in range(1, len(days)):
        if (days[i-1] - days[i]).days == 1:
            streak += 1
        else:
            break
    return jsonify({'streak': streak, 'lastDate': str(days[0])})

@app.route('/api/target')
def daily_target():
    email = request.args.get('email', '').strip()
    if not email:
        return jsonify({'target': 10, 'todayDone': 0})
    db = get_db()
    cur = db.cursor()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cur.execute('SELECT COALESCE(SUM(score), 0) FROM battles WHERE email = %s AND timestamp >= %s', (email, today_start))
    today_done = cur.fetchone()[0]
    # Average of last 7 days
    seven_days_ago = today_start - timedelta(days=7)
    cur.execute('SELECT COALESCE(AVG(daily_total), 0) FROM (SELECT SUM(score) as daily_total FROM battles WHERE email = %s AND timestamp >= %s GROUP BY DATE(timestamp)) sub', (email, seven_days_ago))
    avg = cur.fetchone()[0]
    target = max(10, int(avg * 1.2) + 5)  # progressive overload
    return jsonify({'target': target, 'todayDone': today_done})

@app.route('/api/active_users')
def active_users_endpoint():
    return jsonify({'count': get_active_count()})

# ---------- PWA Routes ----------
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "PushClash", "short_name": "PushClash", "start_url": "/", "scope": "/",
        "display": "standalone", "background_color": "#0a0a0a", "theme_color": "#ff00ff",
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

# ---------- Frontend (CAMERA FEED NOW VISIBLE + all features intact) ----------
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

  /* ─────────── CAMERA FIX ─────────── */
  /* The video must show through the canvas */
  video{width:100%;border-radius:14px;background:#000}
  canvas{width:100%;border-radius:14px;background:transparent !important;pointer-events:none}
  #aiCameraUI{position:relative;width:100%;height:250px;margin:10px 0;border-radius:14px;overflow:hidden;background:#000;display:block}
  #aiCameraUI video{display:block;position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;z-index:3}
  #aiCameraUI canvas{display:block;position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;z-index:2;background:transparent !important}
  /* ───────────────────────────────── */

  .angle-overlay{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:5rem;font-weight:800;color:#0ff;text-shadow:0 0 30px cyan;pointer-events:none;z-index:5}
  .rep-flash{position:absolute;top:30%;left:50%;transform:translate(-50%,-50%);font-size:3rem;font-weight:800;color:#0f0;text-shadow:0 0 30px green;z-index:6;animation:fadeInOut .8s ease}
  @keyframes fadeInOut{0%{opacity:0;transform:translate(-50%,-50%) scale(.5)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.2)}100%{opacity:0;transform:translate(-50%,-50%) scale(1)}}
  .debug-msg{position:absolute;bottom:10px;left:10px;background:rgba(0,0,0,.8);color:#fa0;padding:6px 12px;border-radius:8px;font-size:16px;font-weight:bold;z-index:7;pointer-events:none}

  /* INFO BANNER – auto‑dismiss after 6s */
  .equality-info{position:absolute;bottom:10px;left:50%;transform:translateX(-50%);width:95%;background:rgba(0,0,0,0.85);border:1px solid #00ffff;border-radius:10px;padding:10px 13px;text-align:center;font-size:0.8rem;color:#ccc;line-height:1.4;z-index:10;backdrop-filter:blur(6px);display:none}
  .equality-info strong{color:#00ffff}
  .fade-out{animation:fadeOutBanner 1s ease forwards}
  @keyframes fadeOutBanner{0%{opacity:1}100%{opacity:0}}

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
  .wa-btn{display:inline-block;margin-top:12px;background:#25D366;color:#fff;padding:10px 18px;border-radius:25px;text-decoration:none;font-weight:bold;font-size:1rem;box-shadow:0 0 12px rgba(37,211,102,0.5)}
  .wa-btn:hover{background:#1ebe5b}

  /* Instruction screen */
  .instruction-box{background:rgba(0,0,0,0.8);border-radius:20px;padding:20px;margin:20px 0}
  .instruction-box p{font-size:1rem;line-height:1.8;margin:8px 0;color:#ddd}
  .checkbox-row{display:flex;align-items:center;gap:12px;margin:20px 0;justify-content:center}
  .checkbox-row input{width:20px;height:20px;accent-color:#ff4500}
  .checkbox-row label{font-size:0.9rem;color:#ccc}

  /* Stats Screen */
  .stats-box{background:rgba(0,0,0,0.7);border-radius:16px;padding:16px;margin:10px 0}
  .stats-row{display:flex;gap:12px;margin:10px 0}
  .stats-card{flex:1;background:#1a1a1a;border-radius:12px;padding:12px;text-align:center}
  .stats-card .big-num{font-size:2rem;font-weight:bold;color:#0ff}
  .stats-card .label{font-size:0.75rem;color:#aaa}
  .recent-item{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #333}
  .plan-item{display:flex;justify-content:space-between;padding:6px 0;color:#ccc}

  /* AI Assistant */
  .ai-assistant{position:fixed;bottom:20px;right:20px;z-index:15000;background:linear-gradient(135deg,#ff4500,#ff00ff);color:#fff;padding:10px 16px;border-radius:20px;font-size:0.85rem;max-width:250px;box-shadow:0 0 20px rgba(255,0,255,0.4);cursor:pointer}
  .ai-msg{display:block;line-height:1.4}
  .ai-mute{position:absolute;top:-8px;right:-8px;background:#fff;color:#000;width:24px;height:24px;border-radius:50%;font-size:0.8rem;border:none;cursor:pointer}
</style>
</head>
<body>

<!-- ACTIVE USERS PILL -->
<div class="active-users-pill" id="activeUsersPill">
  <span class="user-icon">👥</span>
  <span class="count" id="activeUserCount">0</span>
  <span style="font-size:0.8rem;color:#aaa">online</span>
</div>

<!-- LUFFY BADGE -->
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
    <div style="color:#aaa;font-size:0.7rem">Tap to call / message</div>
    <!-- WhatsApp Message Button -->
    <a href="https://wa.me/918950592855?text=Hey%20Kaushtubh%2C%20I%20have%20a%20query%20about%20PushClash" target="_blank" class="wa-btn">📱 Message on WhatsApp</a>
    <button class="close-btn" onclick="document.getElementById('ceoModal').classList.remove('active')">Close</button>
  </div>
</div>

<!-- AI Assistant -->
<div class="ai-assistant" id="aiAssistant" onclick="speakAIMessage()">
  <button class="ai-mute" id="aiMuteBtn" onclick="event.stopPropagation(); toggleMute()">🔊</button>
  <span class="ai-msg" id="aiMessage">💬 Loading your coach...</span>
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
    <div style="display:flex;gap:12px;margin:10px 0;color:#ff0">
      <span id="streakDisplay" style="font-size:0.9rem">🔥 Streak: 0 days</span>
      <span id="targetDisplay" style="font-size:0.9rem">🎯 Daily target: 10</span>
    </div>
    <button class="btn-primary" onclick="startChallenge('ai')">🤖 START AI BATTLE</button>
    <button class="btn-secondary" onclick="showLeaderboard()">🏆 Weekly Leaderboard</button>
    <button class="btn-secondary" onclick="showStats()">📊 MY STATS</button>
    <button class="btn-secondary" onclick="resetProfile()">🔄 Leave Arena</button>
    <div class="success-msg" id="saveConfirmation" style="display:none">✅ Score saved to global arena!</div>
  </div>

  <!-- Stats Screen -->
  <div id="statsScreen" class="screen">
    <h1>📊 MY STATS & PLAN</h1>
    <div class="stats-box">
      <div class="stats-row">
        <div class="stats-card"><div class="big-num" id="statTotalPushups">0</div><div class="label">Total Push‑ups</div></div>
        <div class="stats-card"><div class="big-num" id="statBest">0</div><div class="label">Personal Best</div></div>
      </div>
      <div class="stats-row">
        <div class="stats-card"><div class="big-num" id="statBattles">0</div><div class="label">Battles Fought</div></div>
        <div class="stats-card"><div class="big-num" id="statRank">-</div><div class="label">Weekly Rank</div></div>
      </div>
    </div>
    <h3>📅 Weekly Training Plan</h3>
    <div id="weeklyPlan" class="stats-box" style="font-size:0.85rem">
      <div class="plan-item"><span>Mon</span><span>30 push‑ups</span></div>
      <div class="plan-item"><span>Tue</span><span>35 push‑ups</span></div>
      <div class="plan-item"><span>Wed</span><span>REST</span></div>
      <div class="plan-item"><span>Thu</span><span>40 push‑ups</span></div>
      <div class="plan-item"><span>Fri</span><span>35 push‑ups</span></div>
      <div class="plan-item"><span>Sat</span><span>50 push‑ups (challenge)</span></div>
      <div class="plan-item"><span>Sun</span><span>Active recovery</span></div>
    </div>
    <h3>📜 Recent Battles</h3>
    <div id="recentBattlesList" style="max-height:200px;overflow-y:auto"></div>
    <button class="btn-secondary" onclick="showScreen('dashboardScreen')">← Back to Arena</button>
  </div>

  <!-- Challenge Screen (VIDEO NOW VISIBLE – canvas behind video with transparent background) -->
  <div id="challengeScreen" class="screen">
    <div id="countdownDisplay" class="timer-big" style="font-size:4rem">3</div>
    <div id="challengeActiveUI" style="display:none">
      <div class="timer-big" id="timerDisplay">60</div>
      <div class="counter-big" id="repCounter">0</div>
      <div id="aiCameraUI">
        <!-- Canvas first (lower z-index), video on top -->
        <canvas id="poseCanvas"></canvas>
        <video id="webcam" autoplay playsinline muted></video>
        <div class="angle-overlay" id="angleOverlay"></div>
        <div class="rep-flash" id="repFlash" style="display:none">REP!</div>
        <div class="debug-msg" id="debugMsg"></div>
        <!-- INFO BANNER – auto‑dismiss after 6s -->
        <div class="equality-info" id="equalityInfo">
          <strong>⚠️ YOUR FACE IS HIDDEN FOR EQUALITY ⚠️</strong><br>
          We do NOT show your face to anyone. The AI only tracks your body motion, angles, and form — never your identity. All warriors are judged only by their power, not by how they look. Continue your push‑ups into the camera — the AI is watching and will count every clean rep. <strong>NO FACE. ALL STRENGTH. PURE EQUALITY.</strong>
        </div>
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
    <button class="btn-secondary" onclick="showScreen('dashboardScreen')" style="margin-top:16px">← Back to Arena</button>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4"></script>
<script src="https://cdn.jsdelivr.net/npm/@tensorflow-models/pose-detection@2"></script>
<script>
  // -------------------- GLOBALS --------------------
  let currentUser = null, repCount = 0, timeLeft = 60, challengeInterval, countdownInterval, challengeMode = 'ai', aiDetector = null, aiStream = null;
  let muteAI = false;
  let idleTimer = null;
  let equalityTimer = null;
  const trashTalks = ["Even my grandma does more! 💀","Weak sauce!","Push-up? More like push-over.","Bro, my cat reps more.","Too ez. Next!"];
  const BASE = window.location.origin;

  // ---------- Active user count ----------
  async function refreshActiveCount() {
    try { const res = await fetch('/api/active_users'); const data = await res.json(); document.getElementById('activeUserCount').textContent = data.count; } catch(e) {}
  }
  setInterval(refreshActiveCount, 10000);
  window.addEventListener('load', refreshActiveCount);

  // ---------- AI Assistant voice helpers ----------
  function speak(msg) {
    if (muteAI) return;
    const utter = new SpeechSynthesisUtterance(msg);
    utter.lang = 'en-US';
    utter.rate = 0.95;
    speechSynthesis.speak(utter);
  }
  function toggleMute() {
    muteAI = !muteAI;
    const btn = document.getElementById('aiMuteBtn');
    btn.textContent = muteAI ? '🔇' : '🔊';
  }
  function setAIMessage(msg) { document.getElementById('aiMessage').textContent = msg; }
  function speakAIMessage() { speak(document.getElementById('aiMessage').textContent); }

  // ---------- Idle reminder ----------
  function resetIdleTimer() {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      if (document.getElementById('dashboardScreen').classList.contains('active') && currentUser) {
        speak("Hey " + currentUser.name + ", you haven't started a battle yet! Let's crush those push‑ups!");
        setAIMessage("💤 Still resting, " + currentUser.name + "? Your push‑up target is waiting!");
      }
    }, 120000);
  }

  // ---------- Streak & target updater ----------
  async function updateDashboardInfo() {
    if (!currentUser) return;
    try {
      const [streakRes, targetRes] = await Promise.all([
        fetch('/api/streak?email=' + encodeURIComponent(currentUser.email)),
        fetch('/api/target?email=' + encodeURIComponent(currentUser.email))
      ]);
      const streakData = await streakRes.json();
      const targetData = await targetRes.json();
      document.getElementById('streakDisplay').textContent = '🔥 Streak: ' + streakData.streak + ' days';
      const done = targetData.todayDone;
      const target = targetData.target;
      document.getElementById('targetDisplay').textContent = `🎯 Target: ${done}/${target}`;
      return { streak: streakData.streak, target, done };
    } catch(e) { return { streak: 0, target: 10, done: 0 }; }
  }

  // ---------- Voice welcome on dashboard ----------
  async function speakDashboardWelcome() {
    if (!currentUser) return;
    const { streak, target, done } = await updateDashboardInfo();
    const remaining = Math.max(0, target - done);
    const msg = `Welcome back, ${currentUser.name}! Your streak is ${streak} days. Today's push‑up target is ${target}. You've done ${done}, ${remaining} to go!`;
    speak(msg);
    setAIMessage("💬 " + msg);
    resetIdleTimer();
  }

  // ---------- VOICE HELPERS (original) ----------
  function speakWelcome() {
    const msg = new SpeechSynthesisUtterance("Welcome to PushClash. This is the world where people battle for fitness.");
    msg.lang = 'en-US'; msg.rate = 0.9; msg.pitch = 1.1;
    const voices = speechSynthesis.getVoices();
    const femaleVoice = voices.find(v => v.name.toLowerCase().includes('female') || v.name.toLowerCase().includes('samantha') || v.name.toLowerCase().includes('google uk female') || v.name.toLowerCase().includes('microsoft zira'));
    if (femaleVoice) msg.voice = femaleVoice;
    speechSynthesis.speak(msg);
    speakDashboardWelcome();
  }
  function speakChampion() {
    const msg = new SpeechSynthesisUtterance("Champions are built in losses, my friend. Come back stronger.");
    msg.lang = 'en-US'; msg.rate = 0.85; msg.pitch = 0.8;
    const voices = speechSynthesis.getVoices();
    const maleVoice = voices.find(v => v.name.toLowerCase().includes('male') || v.name.toLowerCase().includes('google uk male') || v.name.toLowerCase().includes('microsoft david') || v.name.toLowerCase().includes('daniel'));
    if (maleVoice) msg.voice = maleVoice;
    speechSynthesis.speak(msg);
  }

  // ---------- USER FLOW ----------
  async function saveProfile(){
    const n = document.getElementById('nameInput').value.trim();
    const nat = document.getElementById('nationalityInput').value.trim();
    const em = document.getElementById('emailInput').value.trim();
    const err = document.getElementById('setupError');
    if(!n || !nat || !em){ err.textContent = 'All fields are required!'; return; }
    if(!em.includes('@') || !em.includes('.')){ err.textContent = 'Please enter a valid email'; return; }
    const checkRes = await fetch('/api/check-email', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email: em})});
    const checkData = await checkRes.json();
    if(checkData.exists){ err.textContent = 'This email is already registered.'; return; }
    err.textContent = '';
    currentUser = {name: n, nationality: nat, email: em};
    localStorage.setItem('pushclash_user', JSON.stringify(currentUser));
    showScreen('instructionScreen');
  }

  document.getElementById('agreeCheck').addEventListener('change', function() {
    document.getElementById('enterArenaBtn').disabled = !this.checked;
  });

  function resetProfile(){ localStorage.removeItem('pushclash_user'); currentUser=null; showScreen('setupScreen'); }
  function showScreen(id){ document.querySelectorAll('.screen').forEach(e=>e.classList.remove('active')); document.getElementById(id).classList.add('active'); if(id!=='dashboardScreen') document.getElementById('saveConfirmation').style.display='none'; if(id==='dashboardScreen') { resetIdleTimer(); updateDashboardInfo(); } }
  function goToDashboard(){ if(aiStream){ aiStream.getTracks().forEach(t=>t.stop()); aiStream=null; } loadStats(); showScreen('dashboardScreen'); resetIdleTimer(); }

  async function loadStats(){
    if(!currentUser) return;
    document.getElementById('dashName').textContent = currentUser.name;
    document.getElementById('dashNationality').textContent = currentUser.nationality;
    const res = await fetch('/api/stats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email: currentUser.email})});
    const data = await res.json();
    document.getElementById('personalBest').textContent = data.personalBest;
    document.getElementById('totalBattles').textContent = data.totalBattles;
    localStorage.setItem('pushclash_stats', JSON.stringify(data));
    refreshActiveCount();
  }

  // ---------- STATS PAGE ----------
  async function showStats(){
    if(!currentUser) return;
    const res = await fetch('/api/stats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email: currentUser.email})});
    const data = await res.json();
    document.getElementById('statTotalPushups').textContent = data.totalPushups;
    document.getElementById('statBest').textContent = data.personalBest;
    document.getElementById('statBattles').textContent = data.totalBattles;
    document.getElementById('statRank').textContent = data.rank;
    const container = document.getElementById('recentBattlesList');
    if(!data.recentBattles.length){ container.innerHTML = '<p style="color:#aaa">No battles yet.</p>'; }
    else { container.innerHTML = data.recentBattles.map(b=>`<div class="recent-item"><span>🔥 ${b.score}</span><span class="small">${b.date}</span></div>`).join(''); }
    showScreen('statsScreen');
  }

  // ---------- CHALLENGE START ----------
  async function startChallenge(mode){
    challengeMode = mode;
    showScreen('challengeScreen');
    document.getElementById('countdownDisplay').style.display='block';
    document.getElementById('challengeActiveUI').style.display='none';
    document.getElementById('equalityInfo').style.display='none';
    document.getElementById('equalityInfo').classList.remove('fade-out');
    document.getElementById('battleResultUI').style.display='none';
    if (equalityTimer) clearTimeout(equalityTimer);
    repCount = 0;
    let count=3;
    document.getElementById('countdownDisplay').textContent = count;
    countdownInterval = setInterval(()=>{
      count--;
      if(count===0){
        document.getElementById('countdownDisplay').textContent='GO!';
        speak("Go!");
        setTimeout(()=>{ clearInterval(countdownInterval); document.getElementById('countdownDisplay').style.display='none'; startActiveChallenge(); }, 400);
      } else {
        document.getElementById('countdownDisplay').textContent = count;
        speak(count.toString());
      }
    }, 800);
  }

  async function startActiveChallenge(){
    timeLeft = 60;
    document.getElementById('challengeActiveUI').style.display='block';
    document.getElementById('timerDisplay').textContent = timeLeft;
    document.getElementById('repCounter').textContent = '0';
    document.getElementById('aiCameraUI').style.display='block';
    document.getElementById('debugMsg').textContent = '📷 Camera starting...';
    // Pre‑load the AI model as early as possible
    startAIModel();

    // Show the equality info banner
    const infoBanner = document.getElementById('equalityInfo');
    infoBanner.style.display='block';
    infoBanner.classList.remove('fade-out');
    speak("Attention warrior! Your face is hidden intentionally. We believe in equality — no one is judged by looks, only by power. Continue your push‑ups, the AI is watching your every move.");
    // AUTO‑DISMISS after 6 seconds
    equalityTimer = setTimeout(() => {
      infoBanner.classList.add('fade-out');
      setTimeout(() => { infoBanner.style.display='none'; }, 1000);
    }, 6000);

    await startAICamera();

    // Battle voice cues
    const cueInterval = setInterval(() => {
      if (timeLeft > 55) return;
      if (timeLeft === 30) speak("Halfway there, keep pushing!");
      else if (timeLeft === 15) speak("15 seconds left, give it everything!");
      else if (timeLeft === 10) speak("Final 10 seconds!");
      else if (timeLeft <= 3 && timeLeft > 0) speak(timeLeft.toString());
    }, 1000);

    challengeInterval = setInterval(()=>{
      timeLeft--;
      document.getElementById('timerDisplay').textContent = timeLeft;
      if(timeLeft<=0){
        clearInterval(challengeInterval);
        clearInterval(cueInterval);
        endBattle();
      }
    }, 1000);
    if(currentUser) fetch('/api/stats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email: currentUser.email})});
  }

  // ---------- Pre‑load the AI model ----------
  async function startAIModel(){
    try {
      const cfg = { modelType: 'SinglePose.Lightning' };
      aiDetector = await poseDetection.createDetector(poseDetection.SupportedModels.MoveNet, cfg);
      document.getElementById('debugMsg').textContent = '✅ AI ready – show yourself!';
    } catch(e) {
      document.getElementById('debugMsg').textContent = '❌ AI model failed. Check internet.';
    }
  }

  // ---------- AI CAMERA (canvas background TRANSPARENT, video on top) ----------
  let angleBuffer = [], lastRepTime = 0, aiState = 'up';
  async function startAICamera(){
    const video = document.getElementById('webcam'), canvas = document.getElementById('poseCanvas'), ctx = canvas.getContext('2d'), debugMsg = document.getElementById('debugMsg');
    video.setAttribute('muted', '');
    video.setAttribute('autoplay', '');
    video.setAttribute('playsinline', '');
    try {
      aiStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } });
      video.srcObject = aiStream; await video.play();
    } catch(e) {
      try {
        aiStream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = aiStream; await video.play();
        debugMsg.textContent = '✅ Camera ready (basic)';
      } catch(e2) {
        debugMsg.textContent = '❌ Camera access denied!';
        return;
      }
    }
    video.addEventListener('loadedmetadata', ()=>{ canvas.width = video.videoWidth; canvas.height = video.videoHeight; });
    angleBuffer = []; lastRepTime = 0; aiState = 'up';
    requestAnimationFrame(detectPose);
  }

  function movingAverage(arr, N){ const recent = arr.slice(-N); if(recent.length===0) return null; return recent.reduce((a,b)=>a+b,0)/recent.length; }
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
        // Down threshold = 90°, up threshold = 150°
        if(aiState==='up' && sa < 90){ aiState = 'down'; }
        else if(aiState==='down' && sa > 150){
          if(now - lastRepTime > 500){
            repCount++; document.getElementById('repCounter').textContent = repCount; lastRepTime = now;
            const flash = document.getElementById('repFlash'); flash.style.display='block'; setTimeout(()=>{ flash.style.display='none'; }, 800);
          }
          aiState = 'up';
        }
      } else { overlay.textContent = '?'; overlay.style.display='block'; debugMsg.textContent = '⚠️ Not all keypoints visible'; }
    } else { overlay.textContent = '?'; overlay.style.display='block'; debugMsg.textContent = '🔍 Searching for pose...'; }
    requestAnimationFrame(detectPose);
  }

  function calculateAngle(a,b,c){ const radians = Math.atan2(c.y-b.y, c.x-b.x) - Math.atan2(a.y-b.y, a.x-b.x); let angle = Math.abs(radians * 180.0 / Math.PI); if(angle > 180.0) angle = 360 - angle; return angle; }
  function drawSkeleton(ctx, kp){ const adj = poseDetection.util.getAdjacentPairs(poseDetection.SupportedModels.MoveNet); ctx.strokeStyle = '#0ff'; ctx.lineWidth = 2; for(const [p1,p2] of adj){ if(kp[p1].score > 0.3 && kp[p2].score > 0.3){ ctx.beginPath(); ctx.moveTo(kp[p1].x, kp[p1].y); ctx.lineTo(kp[p2].x, kp[p2].y); ctx.stroke(); } } for(const p of kp){ if(p.score > 0.3){ ctx.fillStyle='#f0f'; ctx.beginPath(); ctx.arc(p.x,p.y,4,0,2*Math.PI); ctx.fill(); } } }

  // ---------- END BATTLE ----------
  async function endBattle(){
    if(aiStream){ aiStream.getTracks().forEach(t=>t.stop()); aiStream=null; }
    if (equalityTimer) clearTimeout(equalityTimer);
    document.getElementById('challengeActiveUI').style.display='none';
    document.getElementById('equalityInfo').style.display='none';
    document.getElementById('battleResultUI').style.display='block';
    document.getElementById('finalScore').textContent = repCount;
    document.getElementById('trashTalk').textContent = trashTalks[Math.floor(Math.random()*trashTalks.length)];
    const champ = document.getElementById('championText'); champ.style.display='block'; speakChampion();
    await fetch('/api/battle', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:currentUser.name, nationality:currentUser.nationality, email:currentUser.email, score:repCount})});
    setTimeout(()=>{ champ.style.display='none'; }, 5000);
    const stats = JSON.parse(localStorage.getItem('pushclash_stats') || '{}');
    const pb = stats.personalBest || 0;
    let analysis = `You scored ${repCount}. `;
    if (repCount >= pb) analysis += "That's a new personal best! You're on fire!";
    else analysis += `Your PB is ${pb}. You're getting closer!`;
    speak(analysis);
    setAIMessage("💬 " + analysis);
  }

  function shareScore(){ navigator.clipboard.writeText(`I just did ${repCount} push-ups in PushClash! Can you beat me? 🔥 ${BASE}`).then(()=>alert('Link copied!')); }

  async function showLeaderboard(){
    showScreen('leaderboardScreen');
    const res = await fetch('/api/leaderboard'), data = await res.json(), container = document.getElementById('leaderboardList');
    if(!data.length){ container.innerHTML = '<p style="text-align:center;color:#aaa">No battles yet.</p>'; return; }
    container.innerHTML = data.map((b,i)=>{ const emojis = ['🥇','🥈','🥉'], rankDisp = i<3 ? emojis[i] : `#${i+1}`; const dateStr = b.date ? ` <span class="score-date">${b.date}</span>` : ''; return `<div class="leaderboard-item"><span class="rank">${rankDisp}</span><span>${b.name}</span><span class="small">${b.nationality}</span><span class="score">${b.score}${dateStr}</span></div>`; }).join('');
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
