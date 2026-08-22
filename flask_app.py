# flask_app.py
import os
import time
import json
import subprocess
import psycopg2
import psycopg2.extras
import psycopg2.errors
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, g, Markup
from threading import Lock

app = Flask(__name__)

# ---------- Active user tracking ----------
active_users = {}
active_users_lock = Lock()
INACTIVITY_LIMIT = 10

def update_active_user(email):
    with active_users_lock:
        active_users[email] = time.time()

def cleanup_active_users():
    now = time.time()
    with active_users_lock:
        for e in [e for e, t in active_users.items() if now - t > INACTIVITY_LIMIT]:
            del active_users[e]

def get_active_count():
    cleanup_active_users()
    with active_users_lock:
        return len(active_users)

# ---------- Database ----------
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL, sslmode='require')
        g.db.cursor_factory = psycopg2.extras.DictCursor
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    """
    Ensure the battles table exists and has the expected columns.
    CREATE TABLE IF NOT EXISTS followed by ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
    """
    try:
        cur = get_db().cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS battles (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            nationality TEXT NOT NULL,
            email TEXT NOT NULL,
            score INTEGER NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT NOW()
        )''')
        # ensure ghost_data column exists (JSONB). If it already exists, this is a no-op.
        cur.execute("ALTER TABLE battles ADD COLUMN IF NOT EXISTS ghost_data JSONB")
        get_db().commit()
        app.logger.info("init_db: OK (table ensured, ghost_data column ensured)")
    except Exception as e:
        # log error but continue; endpoints will defensively handle missing columns
        app.logger.exception("init_db: failed: %s", e)

# Ensure init_db runs even when app is run under a WSGI server (not only __main__)
@app.before_first_request
def ensure_db_on_first_request():
    init_db()

# ---------- Progress endpoint (hackathon 24h view) ----------
@app.route('/progress')
def progress():
    """
    Show git commits from the last 24 hours. If git isn't available (e.g. on some deployed platforms),
    return a friendly message explaining how to generate a PROGRESS-24H.md locally.
    """
    try:
        cmd = ["git", "log", "--since=24 hours ago", "--pretty=format:%h - %s (%an, %ar)"]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        if not output.strip():
            html = "<p>No commits in the last 24 hours.</p>"
        else:
            html = "<pre style='white-space:pre-wrap;font-size:14px;background:#0f0f0f;color:#eee;padding:12px;border-radius:8px;'>%s</pre>" % Markup.escape(output)
    except Exception as e:
        msg = (
            "Could not read git history on this server. This usually means the deployed instance "
            "does not have the git repository or git is not installed.\n\n"
            "To produce the same 24-hour progress locally, run:\n\n"
            "  git log --since='24 hours ago' --pretty=format:\"%h - %s (%an, %ar)\" > PROGRESS-24H.md\n\n"
            "Then add PROGRESS-24H.md to your repo and push to trigger a redeploy."
        )
        html = "<pre style='white-space:pre-wrap;font-size:14px;background:#0f0f0f;color:#f88;padding:12px;border-radius:8px;'>%s\n\nError: %s</pre>" % (Markup.escape(msg), Markup.escape(str(e)))

    page = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>PushClash — 24h Progress</title>
        <style>
          body{{background:#0a0a0a;color:#fff;font-family:system-ui,Segoe UI,Roboto,'Poppins',sans-serif;padding:24px}}
          .container{{max-width:900px;margin:0 auto}}
          h1{{color:#ffcc00}}
          .note{{color:#aaa;margin-bottom:12px}}
          a.button{{display:inline-block;padding:10px 14px;background:#ff4500;color:#fff;border-radius:10px;text-decoration:none;margin-bottom:16px}}
          pre{{overflow:auto}}
        </style>
      </head>
      <body>
        <div class="container">
          <h1>PushClash — 24h Progress</h1>
          <p class="note">This page shows commits made in the last 24 hours (git log). Useful for hackathon progress demos.</p>
          <a class="button" href="/">← Back to app</a>
          {html}
        </div>
      </body>
    </html>
    """
    return page

# ---------- API ----------
@app.route('/api/check-email', methods=['POST'])
def check_email():
    email = request.get_json().get('email','').strip()
    if not email:
        return jsonify({'exists':False})
    cur = get_db().cursor()
    cur.execute('SELECT COUNT(*) FROM battles WHERE email=%s',(email,))
    return jsonify({'exists':cur.fetchone()[0]>0})

@app.route('/api/battle', methods=['POST'])
def record_battle():
    d = request.get_json()
    try:
        n = d.get('name','').strip()
        nat = d.get('nationality','').strip()
        em = d.get('email','').strip()
        sc = int(d.get('score',0))
    except Exception:
        return jsonify({'error':'Invalid data'}),400
    ghost = d.get('ghost_timestamps', None)
    if not n or not nat or not em or sc<=0:
        return jsonify({'error':'Invalid data'}),400
    cur = get_db().cursor()
    cur.execute(
        'INSERT INTO battles (name,nationality,email,score,ghost_data) VALUES (%s,%s,%s,%s,%s)',
        (n, nat, em, sc, json.dumps(ghost) if ghost else None)
    )
    get_db().commit()
    return jsonify({'status':'ok'})

@app.route('/api/ghost')
def ghost():
    email = request.args.get('email','').strip()
    if not email:
        return jsonify({'ghost':None})
    cur = get_db().cursor()
    try:
        # If ghost_data column exists this will work.
        cur.execute("SELECT score, ghost_data FROM battles WHERE email=%s AND ghost_data IS NOT NULL ORDER BY score DESC LIMIT 1", (email,))
        row = cur.fetchone()
        if row and row.get('ghost_data'):
            return jsonify({'ghost': {'score': row['score'], 'timestamps': row['ghost_data']}})
        return jsonify({'ghost': None})
    except psycopg2.errors.UndefinedColumn:
        # Defensive: if column doesn't exist, return ghost None (no 500)
        app.logger.warning("ghost_data column missing when querying ghost; returning ghost: None")
        return jsonify({'ghost': None})
    except Exception as e:
        app.logger.exception("Error in /api/ghost: %s", e)
        return jsonify({'ghost': None})

@app.route('/api/leaderboard')
def leaderboard():
    cur = get_db().cursor()
    seven = datetime.now(timezone.utc)-timedelta(days=7)
    cur.execute('SELECT name,nationality,email,score,timestamp FROM battles WHERE timestamp>=%s ORDER BY timestamp DESC',(seven,))
    rows = cur.fetchall()
    best = {}
    for r in rows:
        em = r['email']
        if em not in best or r['score']>best[em]['score']:
            best[em] = {'name':r['name'],'nationality':r['nationality'],'score':r['score'],'date':r['timestamp']}
    sorted_best = sorted(best.values(), key=lambda x:x['score'], reverse=True)[:10]
    return jsonify([{'name':e['name'],'nationality':e['nationality'],'score':e['score'],'date':e['date'].strftime('%b %d') if e['date'] else ''} for e in sorted_best])

@app.route('/api/stats', methods=['POST'])
def user_stats():
    email = request.get_json().get('email')
    if email:
        update_active_user(email)
    if not email:
        return jsonify({'totalBattles':0,'personalBest':0,'rank':'-','totalPushups':0,'recentBattles':[]})
    cur = get_db().cursor()
    cur.execute('SELECT COUNT(*), COALESCE(MAX(score),0), COALESCE(SUM(score),0) FROM battles WHERE email=%s',(email,))
    total,best,total_pushups = cur.fetchone()
    seven = datetime.now(timezone.utc)-timedelta(days=7)
    cur.execute("""SELECT COUNT(DISTINCT email)+1 FROM battles WHERE timestamp>=%s
                   AND score>(SELECT COALESCE(MAX(score),0) FROM battles WHERE email=%s AND timestamp>=%s)""",(seven,email,seven))
    rank = cur.fetchone()[0]
    cur.execute('SELECT score,timestamp FROM battles WHERE email=%s ORDER BY timestamp DESC LIMIT 10',(email,))
    recent = [{'score':r['score'],'date':r['timestamp'].strftime('%b %d %H:%M')} for r in cur.fetchall()]
    return jsonify({'totalBattles':total,'personalBest':best,'rank':rank,'totalPushups':total_pushups,'recentBattles':recent})

@app.route('/api/streak')
def streak():
    email = request.args.get('email','').strip()
    if not email:
        return jsonify({'streak':0,'lastDate':None})
    cur = get_db().cursor()
    cur.execute('SELECT DISTINCT DATE(timestamp) as day FROM battles WHERE email=%s ORDER BY day DESC LIMIT 60',(email,))
    days = [r['day'] for r in cur.fetchall()]
    if not days:
        return jsonify({'streak':0,'lastDate':None})
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    if days[0] not in (today,yesterday):
        return jsonify({'streak':0,'lastDate':str(days[0])})
    s = 1
    for i in range(1,len(days)):
        if (days[i-1]-days[i]).days==1:
            s+=1
        else:
            break
    return jsonify({'streak':s,'lastDate':str(days[0])})

@app.route('/api/target')
def target():
    email = request.args.get('email','').strip()
    if not email:
        return jsonify({'target':10,'todayDone':0})
    cur = get_db().cursor()
    today_start = datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    cur.execute('SELECT COALESCE(SUM(score),0) FROM battles WHERE email=%s AND timestamp>=%s',(email,today_start))
    today_done = cur.fetchone()[0]
    seven = today_start - timedelta(days=7)
    cur.execute("SELECT COALESCE(AVG(daily_total),0) FROM (SELECT SUM(score) as daily_total FROM battles WHERE email=%s AND timestamp>=%s GROUP BY DATE(timestamp)) sub",(email,seven))
    avg_db = cur.fetchone()[0]
    try:
        avg = float(avg_db) if avg_db is not None else 0.0
    except Exception:
        avg = 0.0
    return jsonify({'target':max(10,int(avg*1.2)+5),'todayDone':today_done})

@app.route('/api/weekly-plan')
def weekly_plan():
    email = request.args.get('email','').strip()
    if not email:
        return jsonify({'days':[], 'weekStart':'', 'weekEnd':''})
    db = get_db()
    cur = db.cursor()
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    cur.execute("""
        SELECT timestamp::date as day, SUM(score) as total
        FROM battles
        WHERE email=%s AND timestamp::date >= %s AND timestamp::date <= %s
        GROUP BY timestamp::date
    """, (email, monday, sunday))
    daily_data = {row['day']: int(row['total']) for row in cur.fetchall()}
    seven_days_ago = today - timedelta(days=7)
    cur.execute("""
        SELECT COALESCE(AVG(daily_total), 0) FROM (
            SELECT SUM(score) as daily_total
            FROM battles
            WHERE email=%s AND timestamp >= %s
            GROUP BY DATE(timestamp)
        ) sub
    """, (email, seven_days_ago))
    avg_db = cur.fetchone()[0]
    try:
        avg = float(avg_db) if avg_db is not None else 0.0
    except Exception:
        avg = 0.0
    base_target = max(10, int(avg * 1.2) + 5)
    days_names = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    days = []
    for i in range(7):
        day_date = monday + timedelta(days=i)
        day_name = days_names[i]
        is_rest = (day_name in ('Wed','Sun'))
        target = 0 if is_rest else base_target
        done = daily_data.get(day_date, 0)
        days.append({
            'day': day_name,
            'date': day_date.isoformat(),
            'target': target,
            'done': done,
            'is_rest': is_rest,
            'is_today': day_date == today
        })
    return jsonify({
        'days': days,
        'weekStart': monday.isoformat(),
        'weekEnd': sunday.isoformat()
    })

@app.route('/api/active_users')
def active_users_endpoint():
    return jsonify({'count':get_active_count()})

# ---------- PWA ----------
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name":"PushClash","short_name":"PushClash","start_url":"/","scope":"/",
        "display":"standalone","background_color":"#0a0a0a","theme_color":"#ff00ff",
        "icons":[
            {"src":"https://cdn-icons-png.flaticon.com/128/2548/2548538.png","sizes":"128x128","type":"image/png"},
            {"src":"https://cdn-icons-png.flaticon.com/192/2548/2548538.png","sizes":"192x192","type":"image/png"},
            {"src":"https://cdn-icons-png.flaticon.com/512/2548/2548538.png","sizes":"512x512","type":"image/png","purpose":"any maskable"}
        ]
    })

@app.route('/sw.js')
def service_worker():
    return app.response_class(
        response="""const CACHE_NAME='pushclash-v5';self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE_NAME).then(c=>c.addAll(['/','/manifest.json'])))});self.addEventListener('fetch',e=>{e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)))});self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE_NAME).map(k=>caches.delete(k)))));});""",
        mimetype='application/javascript'
    )

# ---------- Frontend ----------
# Keep your existing FRONTEND_HTML (the full HTML/JS you already had).
# For brevity, reuse the same FRONTEND_HTML content that includes your updated rep-counting JS.
FRONTEND_HTML = r"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body>
<!-- Paste your full original FRONTEND_HTML (the full page) here exactly as in your working copy.
     I omitted the long HTML in this message to keep it readable. Use the same full HTML/JS you used before. -->
</body>
</html>
"""

@app.route('/')
def index():
    return FRONTEND_HTML

if __name__ == '__main__':
    # If you run the file directly, make sure the DB is initialized (redundant with before_first_request)
    try:
        init_db()
    except Exception:
        pass
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
