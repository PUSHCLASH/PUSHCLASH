import os, time, psycopg2, psycopg2.extras
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, g
from threading import Lock

app = Flask(__name__)

# ---------- Active user tracking ----------
active_users, active_users_lock = {}, Lock()
INACTIVITY_LIMIT = 10

def update_active_user(email):
    with active_users_lock: active_users[email] = time.time()

def cleanup_active_users():
    now = time.time()
    with active_users_lock:
        for email in [e for e, t in active_users.items() if now - t > INACTIVITY_LIMIT]:
            del active_users[email]

def get_active_count():
    cleanup_active_users()
    with active_users_lock: return len(active_users)

# ---------- Database ----------
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL: raise RuntimeError("DATABASE_URL not set")

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL, sslmode='require')
        g.db.cursor_factory = psycopg2.extras.DictCursor
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    with app.app_context():
        cur = get_db().cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS battles (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL, nationality TEXT NOT NULL,
            email TEXT NOT NULL, score INTEGER NOT NULL, timestamp TIMESTAMPTZ DEFAULT NOW())''')
        get_db().commit()

# ---------- API Endpoints (unchanged) ----------
@app.route('/api/check-email', methods=['POST'])
def check_email():
    email = request.get_json().get('email', '').strip()
    if not email: return jsonify({'exists': False})
    cur = get_db().cursor()
    cur.execute('SELECT COUNT(*) FROM battles WHERE email = %s', (email,))
    return jsonify({'exists': cur.fetchone()[0] > 0})

@app.route('/api/battle', methods=['POST'])
def record_battle():
    d = request.get_json()
    n, nat, em, sc = d.get('name','').strip(), d.get('nationality','').strip(), d.get('email','').strip(), int(d.get('score',0))
    if not n or not nat or not em or sc <= 0: return jsonify({'error': 'Invalid data'}), 400
    cur = get_db().cursor()
    cur.execute('INSERT INTO battles (name,nationality,email,score) VALUES (%s,%s,%s,%s)', (n, nat, em, sc))
    get_db().commit()
    return jsonify({'status': 'ok'})

@app.route('/api/leaderboard')
def leaderboard():
    cur = get_db().cursor()
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    cur.execute('SELECT name,nationality,email,score,timestamp FROM battles WHERE timestamp>=%s ORDER BY timestamp DESC', (seven_days_ago,))
    rows = cur.fetchall()
    best_map = {}
    for r in rows:
        em = r['email']
        if em not in best_map or r['score'] > best_map[em]['score']:
            best_map[em] = {'name': r['name'], 'nationality': r['nationality'], 'score': r['score'], 'date': r['timestamp']}
    sorted_best = sorted(best_map.values(), key=lambda x: x['score'], reverse=True)[:10]
    return jsonify([{'name': e['name'], 'nationality': e['nationality'], 'score': e['score'],
                     'date': e['date'].strftime('%b %d') if e['date'] else ''} for e in sorted_best])

@app.route('/api/stats', methods=['POST'])
def user_stats():
    email = request.get_json().get('email')
    if email: update_active_user(email)
    if not email: return jsonify({'totalBattles':0,'personalBest':0,'rank':'-','totalPushups':0,'recentBattles':[]})
    cur = get_db().cursor()
    cur.execute('SELECT COUNT(*), COALESCE(MAX(score),0), COALESCE(SUM(score),0) FROM battles WHERE email=%s', (email,))
    total, best, total_pushups = cur.fetchone()
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    cur.execute("""SELECT COUNT(DISTINCT email)+1 FROM battles WHERE timestamp>=%s
                   AND score>(SELECT COALESCE(MAX(score),0) FROM battles WHERE email=%s AND timestamp>=%s)""",
                (seven_days_ago, email, seven_days_ago))
    rank = cur.fetchone()[0]
    cur.execute('SELECT score, timestamp FROM battles WHERE email=%s ORDER BY timestamp DESC LIMIT 10', (email,))
    recent = [{'score': r['score'], 'date': r['timestamp'].strftime('%b %d %H:%M')} for r in cur.fetchall()]
    return jsonify({'totalBattles': total, 'personalBest': best, 'rank': rank, 'totalPushups': total_pushups, 'recentBattles': recent})

@app.route('/api/streak')
def streak():
    email = request.args.get('email','').strip()
    if not email: return jsonify({'streak':0,'lastDate':None})
    cur = get_db().cursor()
    cur.execute('SELECT DISTINCT DATE(timestamp) as day FROM battles WHERE email=%s ORDER BY day DESC LIMIT 60', (email,))
    days = [r['day'] for r in cur.fetchall()]
    if not days: return jsonify({'streak':0,'lastDate':None})
    today, yesterday = datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date() - timedelta(days=1)
    if days[0] not in (today, yesterday): return jsonify({'streak':0,'lastDate':str(days[0])})
    s = 1
    for i in range(1, len(days)):
        if (days[i-1] - days[i]).days == 1: s += 1
        else: break
    return jsonify({'streak': s, 'lastDate': str(days[0])})

@app.route('/api/target')
def daily_target():
    email = request.args.get('email','').strip()
    if not email: return jsonify({'target':10,'todayDone':0})
    cur = get_db().cursor()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cur.execute('SELECT COALESCE(SUM(score),0) FROM battles WHERE email=%s AND timestamp>=%s', (email, today_start))
    today_done = cur.fetchone()[0]
    seven_days_ago = today_start - timedelta(days=7)
    cur.execute("""SELECT COALESCE(AVG(daily_total),0) FROM (SELECT SUM(score) as daily_total FROM battles
                    WHERE email=%s AND timestamp>=%s GROUP BY DATE(timestamp)) sub""", (email, seven_days_ago))
    avg = cur.fetchone()[0]
    return jsonify({'target': max(10, int(avg * 1.2) + 5), 'todayDone': today_done})

@app.route('/api/active_users')
def active_endpoint():
    return jsonify({'count': get_active_count()})

# ---------- PWA Routes ----------
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "PushClash", "short_name": "PushClash", "start_url": "/", "scope": "/",
        "display": "standalone", "background_color": "#0a0a0a", "theme_color": "#ff00ff",
        "icons": [
            {"src":"https://cdn-icons-png.flaticon.com/128/2548/2548538.png","sizes":"128x128","type":"image/png"},
            {"src":"https://cdn-icons-png.flaticon.com/192/2548/2548538.png","sizes":"192x192","type":"image/png"},
            {"src":"https://cdn-icons-png.flaticon.com/512/2548/2548538.png","sizes":"512x512","type":"image/png","purpose":"any maskable"}
        ]
    })

@app.route('/sw.js')
def service_worker():
    return app.response_class(
        response="""const CACHE_NAME='pushclash-v5';self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE_NAME).then(c=>c.addAll(['/','/manifest.json']))) });self.addEventListener('fetch',e=>{e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request))) });""",
        mimetype='application/javascript'
    )

# ---------- Frontend (VIDEO MUTED + VISIBILITY HARDENED) ----------
FRONTEND_HTML = r"""
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
  .debug-msg{position:absolute;bottom:10px;left:10px;background:rgba(0,0,0,.8);color:#fa0;padding:6px 12px;border-radius:8px;font-size:16px;font-weight:bold;z-index:7}
  .luffy-badge{position:fixed;top:15px;right:15px;z-index:10000;cursor:pointer;display:flex;flex-direction:column;align-items:center}
  .luffy-img{width:70px;height:70px;border-radius:50%;object-fit:cover;border:none;box-shadow:0 0 15px rgba(0,191,255,0.6),0 0 30px rgba(255,69,0,0.4)}
  .ceo-label{font-size:.7rem;color:#ddd;margin-top:6px;background:rgba(0,0,0,0.7);padding:3px 10px;border-radius:12px;text-align:center}
  .ceo-arrow{position:fixed;top:30px;right:90px;font-size:1.8rem;color:#fff;animation:arrowBounce .8s ease-in-out infinite;pointer-events:none;z-index:10000}
  @keyframes arrowBounce{0%,100%{transform:translateX(0)}50%{transform:translateX(8px)}}
  .active-users-pill{position:fixed;top:15px;left:15px;z-index:10000;display:flex;align-items:center;gap:6px;background:rgba(0,0,0,0.7);padding:6px 12px;border-radius:20px;border:1px solid rgba(0,255,255,0.4)}
  .active-users-pill .user-icon{font-size:1.2rem}.active-users-pill .count{font-weight:bold;font-size:1rem;color:#0ff}
  .ceo-modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.85);backdrop-filter:blur(10px);z-index:20000;display:none;align-items:center;justify-content:center}
  .ceo-modal-overlay.active{display:flex}
  .ceo-modal{background:#1a1a1a;border-radius:24px;padding:30px 24px;max-width:320px;width:90%;text-align:center;border:1px solid rgba(0,255,255,.3)}
  .instruction-box{background:rgba(0,0,0,0.8);border-radius:20px;padding:20px;margin:20px 0}
  .instruction-box p{font-size:1rem;line-height:1.8;margin:8px 0;color:#ddd}
  .checkbox-row{display:flex;align-items:center;gap:12px;margin:20px 0;justify-content:center}
  .checkbox-row input{width:20px;height:20px;accent-color:#ff4500}
  .stats-box{background:rgba(0,0,0,0.7);border-radius:16px;padding:16px;margin:10px 0}
  .stats-row{display:flex;gap:12px;margin:10px 0}
  .stats-card{flex:1;background:#1a1a1a;border-radius:12px;padding:12px;text-align:center}
  .stats-card .big-num{font-size:2rem;font-weight:bold;color:#0ff}
  .ai-assistant{position:fixed;bottom:20px;right:20px;z-index:15000;background:linear-gradient(135deg,#ff4500,#ff00ff);color:#fff;padding:10px 16px;border-radius:20px;font-size:0.85rem;max-width:250px;cursor:pointer}
  .ai-mute{position:absolute;top:-8px;right:-8px;background:#fff;color:#000;width:24px;height:24px;border-radius:50%;font-size:0.8rem;border:none;cursor:pointer}
</style>
</head>
<body>

<div class="active-users-pill"><span class="user-icon">👥</span><span class="count" id="activeUserCount">0</span><span style="font-size:0.8rem;color:#aaa">online</span></div>
<div class="luffy-badge" onclick="document.getElementById('ceoModal').classList.add('active')"><img class="luffy-img" src="https://raw.githubusercontent.com/PUSHCLASH/PUSHCLASH/main/luffy%20image.jpeg"><span class="ceo-label">CEO of App</span></div>
<div class="ceo-arrow">👉</div>
<div id="ceoModal" class="ceo-modal-overlay" onclick="this.classList.remove('active')"><div class="ceo-modal" onclick="event.stopPropagation()"><h2>KAUSHTUBH</h2><div class="title">CEO OF PUSH CLASH</div><div class="phone">📞 8950592855</div></div></div>
<div class="ai-assistant" onclick="speakAIMessage()"><button class="ai-mute" onclick="event.stopPropagation();toggleMute()">🔊</button><span id="aiMessage">💬 Loading…</span></div>

<div class="app-container" id="app">
  <div id="setupScreen" class="screen active"><h1>PUSHCLASH</h1><div class="arena-subtitle">⚔️ ENTER THE ARENA ⚔️</div>
    <input class="battle-input" id="nameInput" placeholder="Your Warrior Name"><input class="battle-input" id="nationalityInput" placeholder="Nationality"><input class="battle-input" id="emailInput" placeholder="Email">
    <div class="error-msg" id="setupError"></div><button class="btn-primary" onclick="saveProfile()">⚡ ENTER ARENA ⚡</button></div>
  <div id="instructionScreen" class="screen"><h1>🚀 WELCOME!</h1><div class="instruction-box"><p>...</p></div><div class="checkbox-row"><input type="checkbox" id="agreeCheck"><label>I have read all instructions</label></div><button class="btn-primary" id="enterArenaBtn" disabled onclick="showScreen('dashboardScreen');loadStats()">⚡ ENTER ARENA ⚡</button></div>
  <div id="dashboardScreen" class="screen"><h1>PUSHCLASH</h1><p>Welcome, <span id="dashName"></span>!</p>
    <div style="display:flex;gap:12px;margin:20px 0"><div class="stats-card"><div class="big-num" id="personalBest">0</div><div class="small">Personal Best</div></div><div class="stats-card"><div class="big-num" id="totalBattles">0</div><div class="small">Total Battles</div></div></div>
    <div style="color:#ff0"><span id="streakDisplay">🔥 Streak: 0</span> | <span id="targetDisplay">🎯 Target: 0</span></div>
    <button class="btn-primary" onclick="startChallenge('ai')">🤖 START AI BATTLE</button>
    <button class="btn-secondary" onclick="showLeaderboard()">🏆 Weekly Leaderboard</button>
    <button class="btn-secondary" onclick="showStats()">📊 MY STATS</button>
    <button class="btn-secondary" onclick="resetProfile()">🔄 Leave Arena</button></div>
  <div id="statsScreen" class="screen"><h1>📊 MY STATS</h1><div id="recentBattlesList"></div><button class="btn-secondary" onclick="showScreen('dashboardScreen')">← Back</button></div>
  <div id="challengeScreen" class="screen"><div id="countdownDisplay" class="timer-big">3</div><div id="challengeActiveUI" style="display:none"><div class="timer-big" id="timerDisplay">60</div><div class="counter-big" id="repCounter">0</div><div id="aiCameraUI"><video id="webcam" autoplay playsinline muted></video><canvas id="poseCanvas"></canvas><div class="angle-overlay" id="angleOverlay"></div><div class="rep-flash" id="repFlash" style="display:none">REP!</div><div class="debug-msg" id="debugMsg"></div></div></div><div id="battleResultUI" style="display:none;text-align:center"><h2>⚔️ Battle Over!</h2><div style="font-size:3rem;color:#0ff" id="finalScore">0</div><div class="result-msg" id="trashTalk"></div><button class="btn-primary" onclick="shareScore()">📢 Share</button><button class="btn-secondary" onclick="goToDashboard()">Back</button></div>
  <div id="leaderboardScreen" class="screen"><h1>WEEKLY RANKINGS</h1><div id="leaderboardList"></div><button class="btn-secondary" onclick="showScreen('dashboardScreen')">← Back</button></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4"></script>
<script src="https://cdn.jsdelivr.net/npm/@tensorflow-models/pose-detection@2"></script>
<script>
let currentUser=null,repCount=0,timeLeft=60,challengeInterval,countdownInterval,aiDetector=null,aiStream=null,muteAI=false,idleTimer=null;
const trashTalks=["Even my grandma does more! 💀","Weak sauce!","Push-up? More like push-over.","Bro, my cat reps more.","Too ez. Next!"];
const BASE=window.location.origin;

async function refreshActiveCount(){try{let r=await fetch('/api/active_users');let d=await r.json();document.getElementById('activeUserCount').textContent=d.count}catch(e){}}
setInterval(refreshActiveCount,10000);window.addEventListener('load',refreshActiveCount);

function speak(msg){if(muteAI)return;let u=new SpeechSynthesisUtterance(msg);u.lang='en-US';u.rate=0.95;speechSynthesis.speak(u)}
function toggleMute(){muteAI=!muteAI;document.getElementById('aiMuteBtn').textContent=muteAI?'🔇':'🔊'}
function setAIMessage(m){document.getElementById('aiMessage').textContent=m}
function speakAIMessage(){speak(document.getElementById('aiMessage').textContent)}

async function saveProfile(){
  let n=document.getElementById('nameInput').value.trim(),nat=document.getElementById('nationalityInput').value.trim(),em=document.getElementById('emailInput').value.trim(),err=document.getElementById('setupError');
  if(!n||!nat||!em){err.textContent='All fields required!';return}
  if(!em.includes('@')||!em.includes('.')){err.textContent='Valid email needed';return}
  let chk=await fetch('/api/check-email',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em})});
  if((await chk.json()).exists){err.textContent='Email already registered!';return}
  err.textContent='';currentUser={name:n,nationality:nat,email:em};localStorage.setItem('pushclash_user',JSON.stringify(currentUser));
  showScreen('instructionScreen')}

function resetProfile(){localStorage.removeItem('pushclash_user');currentUser=null;showScreen('setupScreen')}
function showScreen(id){document.querySelectorAll('.screen').forEach(e=>e.classList.remove('active'));document.getElementById(id).classList.add('active')}
function goToDashboard(){if(aiStream){aiStream.getTracks().forEach(t=>t.stop());aiStream=null}loadStats();showScreen('dashboardScreen')}

async function loadStats(){
  if(!currentUser)return;
  let r=await fetch('/api/stats',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:currentUser.email})});
  let d=await r.json();document.getElementById('personalBest').textContent=d.personalBest;document.getElementById('totalBattles').textContent=d.totalBattles}

async function startChallenge(mode){
  showScreen('challengeScreen');document.getElementById('countdownDisplay').style.display='block';
  document.getElementById('challengeActiveUI').style.display='none';repCount=0;let c=3;
  document.getElementById('countdownDisplay').textContent=c;
  countdownInterval=setInterval(()=>{c--;if(c===0){document.getElementById('countdownDisplay').textContent='GO!';setTimeout(()=>{clearInterval(countdownInterval);document.getElementById('countdownDisplay').style.display='none';startActiveChallenge()},400)}else{document.getElementById('countdownDisplay').textContent=c}},800)}

async function startActiveChallenge(){
  timeLeft=60;document.getElementById('challengeActiveUI').style.display='block';
  document.getElementById('timerDisplay').textContent=timeLeft;document.getElementById('repCounter').textContent='0';
  document.getElementById('aiCameraUI').style.display='block';document.getElementById('debugMsg').textContent='📷 Camera starting...';
  await startAICamera();
  challengeInterval=setInterval(()=>{timeLeft--;document.getElementById('timerDisplay').textContent=timeLeft;if(timeLeft<=0){clearInterval(challengeInterval);endBattle()}},1000)}

let angleBuffer=[],lastRepTime=0,aiState='up';

async function startAICamera(){
  const video=document.getElementById('webcam'),canvas=document.getElementById('poseCanvas'),ctx=canvas.getContext('2d'),debug=document.getElementById('debugMsg');
  //--------- HARDENED CAMERA START ---------
  video.setAttribute('autoplay','');video.setAttribute('playsinline','');video.setAttribute('muted','');
  video.style.display='block';video.style.width='100%';video.style.height='100%';video.style.objectFit='cover';
  try{
    aiStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user'}});
    video.srcObject=aiStream;await video.play();
    debug.textContent='✅ Camera ready!';debug.style.color='#0f0';
  }catch(e){
    try{
      aiStream=await navigator.mediaDevices.getUserMedia({video:true});
      video.srcObject=aiStream;await video.play();
      debug.textContent='✅ Camera ready (basic)';debug.style.color='#0f0';
    }catch(e2){
      debug.textContent='❌ Camera denied. Check permissions.';debug.style.color='#f44';return}
  }
  video.addEventListener('loadedmetadata',()=>{canvas.width=video.videoWidth||640;canvas.height=video.videoHeight||480;canvas.style.display='block'});
  try{aiDetector=await poseDetection.createDetector(poseDetection.SupportedModels.MoveNet,{modelType:'SinglePose.Lightning'})}catch(e){debug.textContent='❌ AI model failed';return}
  angleBuffer=[];lastRepTime=0;aiState='up';requestAnimationFrame(detectPose)}

function movingAverage(arr,N){let r=arr.slice(-N);if(r.length===0)return null;return r.reduce((a,b)=>a+b,0)/r.length}

async function detectPose(){
  if(timeLeft<=0||!aiDetector||!aiStream)return;
  const video=document.getElementById('webcam'),canvas=document.getElementById('poseCanvas'),ctx=canvas.getContext('2d'),overlay=document.getElementById('angleOverlay'),debug=document.getElementById('debugMsg');
  if(video.readyState<2){requestAnimationFrame(detectPose);return}
  const poses=await aiDetector.estimatePoses(video,{flipHorizontal:false});ctx.clearRect(0,0,canvas.width,canvas.height);
  if(poses.length>0){
    const kp=poses[0].keypoints;drawSkeleton(ctx,kp);
    const ls=kp[5],rs=kp[6],le=kp[7],lw=kp[9],re=kp[8],rw=kp[10];
    if(ls&&le&&lw&&rs&&re&&rw){
      const la=calculateAngle(ls,le,lw),ra=calculateAngle(rs,re,rw),raw=(la+ra)/2;
      angleBuffer.push(raw);if(angleBuffer.length>5)angleBuffer.shift();
      const sa=movingAverage(angleBuffer,5);if(sa===null){requestAnimationFrame(detectPose);return}
      overlay.textContent=Math.round(sa)+'°';overlay.style.display='block';debug.textContent='🟢 Active – '+Math.round(sa)+'°';
      const now=Date.now();
      if(aiState==='up'&&sa<90){aiState='down'}else if(aiState==='down'&&sa>160){if(now-lastRepTime>500){repCount++;document.getElementById('repCounter').textContent=repCount;lastRepTime=now;const flash=document.getElementById('repFlash');flash.style.display='block';setTimeout(()=>{flash.style.display='none'},800)}aiState='up'}}
    else{overlay.textContent='?';overlay.style.display='block';debug.textContent='⚠️ Not all keypoints visible'}}
  else{overlay.textContent='?';overlay.style.display='block';debug.textContent='🔍 Searching for pose...'}
  requestAnimationFrame(detectPose)}

function calculateAngle(a,b,c){const radians=Math.atan2(c.y-b.y,c.x-b.x)-Math.atan2(a.y-b.y,a.x-b.x);let angle=Math.abs(radians*180.0/Math.PI);if(angle>180.0)angle=360-angle;return angle}
function drawSkeleton(ctx,kp){const adj=poseDetection.util.getAdjacentPairs(poseDetection.SupportedModels.MoveNet);ctx.strokeStyle='#0ff';ctx.lineWidth=2;for(const[p1,p2]of adj){if(kp[p1].score>0.3&&kp[p2].score>0.3){ctx.beginPath();ctx.moveTo(kp[p1].x,kp[p1].y);ctx.lineTo(kp[p2].x,kp[p2].y);ctx.stroke()}}for(const p of kp){if(p.score>0.3){ctx.fillStyle='#f0f';ctx.beginPath();ctx.arc(p.x,p.y,4,0,2*Math.PI);ctx.fill()}}}

async function endBattle(){
  if(aiStream){aiStream.getTracks().forEach(t=>t.stop());aiStream=null}
  document.getElementById('challengeActiveUI').style.display='none';document.getElementById('battleResultUI').style.display='block';
  document.getElementById('finalScore').textContent=repCount;document.getElementById('trashTalk').textContent=trashTalks[Math.floor(Math.random()*trashTalks.length)];
  await fetch('/api/battle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:currentUser.name,nationality:currentUser.nationality,email:currentUser.email,score:repCount})})}

function shareScore(){navigator.clipboard.writeText(`I just did ${repCount} push-ups in PushClash! Can you beat me? 🔥 ${BASE}`).then(()=>alert('Link copied!'))}

async function showLeaderboard(){
  showScreen('leaderboardScreen');let r=await fetch('/api/leaderboard'),d=await r.json(),c=document.getElementById('leaderboardList');
  if(!d.length){c.innerHTML='<p style="color:#aaa">No battles yet.</p>';return}
  c.innerHTML=d.map((b,i)=>{let emojis=['🥇','🥈','🥉'],rd=i<3?emojis[i]:`#${i+1}`,ds=b.date?` <span class="score-date">${b.date}</span>`:'';return `<div class="leaderboard-item"><span class="rank">${rd}</span><span>${b.name}</span><span class="small">${b.nationality}</span><span class="score">${b.score}${ds}</span></div>`}).join('')}

async function showStats(){
  if(!currentUser)return;
  let r=await fetch('/api/stats',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:currentUser.email})});
  let d=await r.json();document.getElementById('statTotalPushups').textContent=d.totalPushups;
  document.getElementById('statBest').textContent=d.personalBest;document.getElementById('statBattles').textContent=d.totalBattles;
  document.getElementById('statRank').textContent=d.rank;
  let c=document.getElementById('recentBattlesList');
  if(!d.recentBattles.length){c.innerHTML='<p style="color:#aaa">No battles yet.</p>';return}
  c.innerHTML=d.recentBattles.map(b=>`<div class="recent-item"><span>🔥 ${b.score}</span><span class="small">${b.date}</span></div>`).join('');
  showScreen('statsScreen')}

currentUser=JSON.parse(localStorage.getItem('pushclash_user'));if(currentUser){showScreen('dashboardScreen');loadStats()}else{showScreen('setupScreen')}
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return FRONTEND_HTML

if __name__ == '__main__':
    with app.app_context(): init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False)
