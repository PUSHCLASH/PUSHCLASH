import os
import time
import json
import psycopg2
import psycopg2.extras

from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, g
from threading import Lock


# ============================================================
# PUSHCLASH
# Flask + PostgreSQL + MoveNet AI Push-up Detection
# Single Python file
# ============================================================

app = Flask(__name__)


# ============================================================
# ACTIVE USER TRACKING
# ============================================================

active_users = {}
active_users_lock = Lock()

INACTIVITY_LIMIT = 10


def update_active_user(email):
    if not email:
        return

    with active_users_lock:
        active_users[email] = time.time()


def cleanup_active_users():
    now = time.time()

    with active_users_lock:
        expired = [
            email
            for email, timestamp in active_users.items()
            if now - timestamp > INACTIVITY_LIMIT
        ]

        for email in expired:
            del active_users[email]


def get_active_count():
    cleanup_active_users()

    with active_users_lock:
        return len(active_users)


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")


def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(
            DATABASE_URL,
            sslmode="require"
        )

        g.db.cursor_factory = psycopg2.extras.DictCursor

    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)

    if db:
        db.close()


def init_db():
    with app.app_context():

        cur = get_db().cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS battles (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                nationality TEXT NOT NULL,
                email TEXT NOT NULL,
                score INTEGER NOT NULL,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                ghost_data JSONB
            )
        """)

        get_db().commit()


# ============================================================
# API
# ============================================================

@app.route("/api/check-email", methods=["POST"])
def check_email():

    data = request.get_json(silent=True) or {}

    email = data.get("email", "").strip()

    if not email:
        return jsonify({"exists": False})

    cur = get_db().cursor()

    cur.execute(
        "SELECT COUNT(*) FROM battles WHERE email=%s",
        (email,)
    )

    return jsonify({
        "exists": cur.fetchone()[0] > 0
    })


@app.route("/api/battle", methods=["POST"])
def record_battle():

    data = request.get_json(silent=True) or {}

    try:
        name = data.get("name", "").strip()
        nationality = data.get("nationality", "").strip()
        email = data.get("email", "").strip()
        score = int(data.get("score", 0))
        ghost = data.get("ghost_timestamps", None)

    except Exception:
        return jsonify({
            "error": "Invalid data"
        }), 400

    if not name or not nationality or not email or score <= 0:
        return jsonify({
            "error": "Invalid data"
        }), 400

    cur = get_db().cursor()

    cur.execute(
        """
        INSERT INTO battles
        (name, nationality, email, score, ghost_data)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            name,
            nationality,
            email,
            score,
            json.dumps(ghost) if ghost else None
        )
    )

    get_db().commit()

    return jsonify({
        "status": "ok"
    })


@app.route("/api/ghost")
def ghost():

    email = request.args.get("email", "").strip()

    if not email:
        return jsonify({
            "ghost": None
        })

    cur = get_db().cursor()

    cur.execute(
        """
        SELECT score, ghost_data
        FROM battles
        WHERE email=%s
        AND ghost_data IS NOT NULL
        ORDER BY score DESC
        LIMIT 1
        """,
        (email,)
    )

    row = cur.fetchone()

    if row and row["ghost_data"]:

        return jsonify({
            "ghost": {
                "score": row["score"],
                "timestamps": row["ghost_data"]
            }
        })

    return jsonify({
        "ghost": None
    })


@app.route("/api/leaderboard")
def leaderboard():

    cur = get_db().cursor()

    seven_days_ago = (
        datetime.now(timezone.utc)
        - timedelta(days=7)
    )

    cur.execute(
        """
        SELECT
            name,
            nationality,
            email,
            score,
            timestamp
        FROM battles
        WHERE timestamp >= %s
        ORDER BY timestamp DESC
        """,
        (seven_days_ago,)
    )

    rows = cur.fetchall()

    best = {}

    for row in rows:

        email = row["email"]

        if (
            email not in best
            or row["score"] > best[email]["score"]
        ):
            best[email] = {
                "name": row["name"],
                "nationality": row["nationality"],
                "score": row["score"],
                "date": row["timestamp"]
            }

    sorted_best = sorted(
        best.values(),
        key=lambda x: x["score"],
        reverse=True
    )[:10]

    return jsonify([
        {
            "name": entry["name"],
            "nationality": entry["nationality"],
            "score": entry["score"],
            "date": (
                entry["date"].strftime("%b %d")
                if entry["date"]
                else ""
            )
        }
        for entry in sorted_best
    ])


@app.route("/api/stats", methods=["POST"])
def user_stats():

    data = request.get_json(silent=True) or {}

    email = data.get("email", "").strip()

    if email:
        update_active_user(email)

    if not email:

        return jsonify({
            "totalBattles": 0,
            "personalBest": 0,
            "rank": "-",
            "totalPushups": 0,
            "recentBattles": []
        })

    cur = get_db().cursor()

    cur.execute(
        """
        SELECT
            COUNT(*),
            COALESCE(MAX(score), 0),
            COALESCE(SUM(score), 0)
        FROM battles
        WHERE email=%s
        """,
        (email,)
    )

    total, personal_best, total_pushups = cur.fetchone()

    seven_days_ago = (
        datetime.now(timezone.utc)
        - timedelta(days=7)
    )

    cur.execute(
        """
        SELECT COUNT(DISTINCT email) + 1
        FROM battles
        WHERE timestamp >= %s
        AND score >
        (
            SELECT COALESCE(MAX(score), 0)
            FROM battles
            WHERE email=%s
            AND timestamp >= %s
        )
        """,
        (
            seven_days_ago,
            email,
            seven_days_ago
        )
    )

    rank = cur.fetchone()[0]

    cur.execute(
        """
        SELECT score, timestamp
        FROM battles
        WHERE email=%s
        ORDER BY timestamp DESC
        LIMIT 10
        """,
        (email,)
    )

    recent = [
        {
            "score": row["score"],
            "date": row["timestamp"].strftime(
                "%b %d %H:%M"
            )
        }
        for row in cur.fetchall()
    ]

    return jsonify({
        "totalBattles": total,
        "personalBest": personal_best,
        "rank": rank,
        "totalPushups": total_pushups,
        "recentBattles": recent
    })


@app.route("/api/streak")
def streak():

    email = request.args.get("email", "").strip()

    if not email:

        return jsonify({
            "streak": 0,
            "lastDate": None
        })

    cur = get_db().cursor()

    cur.execute(
        """
        SELECT DISTINCT DATE(timestamp) AS day
        FROM battles
        WHERE email=%s
        ORDER BY day DESC
        LIMIT 60
        """,
        (email,)
    )

    days = [
        row["day"]
        for row in cur.fetchall()
    ]

    if not days:

        return jsonify({
            "streak": 0,
            "lastDate": None
        })

    today = datetime.now(timezone.utc).date()

    yesterday = today - timedelta(days=1)

    if days[0] not in (today, yesterday):

        return jsonify({
            "streak": 0,
            "lastDate": str(days[0])
        })

    current_streak = 1

    for i in range(1, len(days)):

        if (days[i - 1] - days[i]).days == 1:
            current_streak += 1
        else:
            break

    return jsonify({
        "streak": current_streak,
        "lastDate": str(days[0])
    })


@app.route("/api/target")
def target():

    email = request.args.get("email", "").strip()

    if not email:

        return jsonify({
            "target": 10,
            "todayDone": 0
        })

    cur = get_db().cursor()

    today_start = datetime.now(
        timezone.utc
    ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    cur.execute(
        """
        SELECT COALESCE(SUM(score), 0)
        FROM battles
        WHERE email=%s
        AND timestamp >= %s
        """,
        (
            email,
            today_start
        )
    )

    today_done = cur.fetchone()[0]

    seven_days_ago = today_start - timedelta(days=7)

    cur.execute(
        """
        SELECT COALESCE(AVG(daily_total), 0)
        FROM (
            SELECT SUM(score) AS daily_total
            FROM battles
            WHERE email=%s
            AND timestamp >= %s
            GROUP BY DATE(timestamp)
        ) sub
        """,
        (
            email,
            seven_days_ago
        )
    )

    avg = cur.fetchone()[0]

    daily_target = max(
        10,
        int(avg * 1.2) + 5
    )

    return jsonify({
        "target": daily_target,
        "todayDone": today_done
    })


@app.route("/api/weekly-plan")
def weekly_plan():

    email = request.args.get("email", "").strip()

    if not email:

        return jsonify({
            "days": [],
            "weekStart": "",
            "weekEnd": ""
        })

    cur = get_db().cursor()

    today = datetime.now(timezone.utc).date()

    monday = today - timedelta(
        days=today.weekday()
    )

    sunday = monday + timedelta(days=6)

    cur.execute(
        """
        SELECT
            timestamp::date AS day,
            SUM(score) AS total
        FROM battles
        WHERE email=%s
        AND timestamp::date >= %s
        AND timestamp::date <= %s
        GROUP BY timestamp::date
        """,
        (
            email,
            monday,
            sunday
        )
    )

    daily_data = {
        row["day"]: int(row["total"])
        for row in cur.fetchall()
    }

    seven_days_ago = today - timedelta(days=7)

    cur.execute(
        """
        SELECT COALESCE(AVG(daily_total), 0)
        FROM (
            SELECT SUM(score) AS daily_total
            FROM battles
            WHERE email=%s
            AND timestamp >= %s
            GROUP BY DATE(timestamp)
        ) sub
        """,
        (
            email,
            seven_days_ago
        )
    )

    avg = float(cur.fetchone()[0])

    base_target = max(
        10,
        int(avg * 1.2) + 5
    )

    day_names = [
        "Mon",
        "Tue",
        "Wed",
        "Thu",
        "Fri",
        "Sat",
        "Sun"
    ]

    days = []

    for i in range(7):

        day_date = monday + timedelta(days=i)

        day_name = day_names[i]

        is_rest = day_name in ("Wed", "Sun")

        target_value = (
            0
            if is_rest
            else base_target
        )

        done = daily_data.get(
            day_date,
            0
        )

        days.append({
            "day": day_name,
            "date": day_date.isoformat(),
            "target": target_value,
            "done": done,
            "is_rest": is_rest,
            "is_today": day_date == today
        })

    return jsonify({
        "days": days,
        "weekStart": monday.isoformat(),
        "weekEnd": sunday.isoformat()
    })


@app.route("/api/active_users")
def active_users_endpoint():

    return jsonify({
        "count": get_active_count()
    })


# ============================================================
# PWA
# ============================================================

@app.route("/manifest.json")
def manifest():

    return jsonify({
        "name": "PushClash",
        "short_name": "PushClash",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0a0a0a",
        "theme_color": "#ff00ff",
        "icons": [
            {
                "src": "https://cdn-icons-png.flaticon.com/128/2548/2548538.png",
                "sizes": "128x128",
                "type": "image/png"
            },
            {
                "src": "https://cdn-icons-png.flaticon.com/192/2548/2548538.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "https://cdn-icons-png.flaticon.com/512/2548/2548538.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    })


@app.route("/sw.js")
def service_worker():

    return app.response_class(
        response="""
        const CACHE_NAME='pushclash-v6';

        self.addEventListener('install', event => {
            event.waitUntil(
                caches.open(CACHE_NAME).then(cache =>
                    cache.addAll([
                        '/',
                        '/manifest.json'
                    ])
                )
            );
        });

        self.addEventListener('fetch', event => {
            event.respondWith(
                caches.match(event.request).then(response =>
                    response || fetch(event.request)
                )
            );
        });

        self.addEventListener('activate', event => {
            event.waitUntil(
                caches.keys().then(keys =>
                    Promise.all(
                        keys
                        .filter(key => key !== CACHE_NAME)
                        .map(key => caches.delete(key))
                    )
                )
            );
        });
        """,
        mimetype="application/javascript"
    )


# ============================================================
# FRONTEND
# ============================================================

FRONTEND_HTML = r"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0, user-scalable=yes"
>

<link rel="manifest" href="/manifest.json">

<meta
    name="apple-mobile-web-app-capable"
    content="yes"
>

<meta
    name="apple-mobile-web-app-status-bar-style"
    content="black-translucent"
>

<script>
navigator.serviceWorker?.register('/sw.js');
</script>

<title>PUSHCLASH 🔥</title>


<style>

*{
    margin:0;
    padding:0;
    box-sizing:border-box;
    font-family:'Poppins',sans-serif
}

body{
    background:#0a0a0a;
    color:#fff;
    min-height:100vh;
    display:flex;
    justify-content:center;
    align-items:center;
    padding:20px;
    background-image:
        radial-gradient(
            circle at 50% 50%,
            #1a1a1a 0%,
            #000 100%
        );
    overflow-x:hidden
}

.app-container{
    max-width:450px;
    width:100%;
    background:#111;
    border-radius:28px;
    padding:24px 20px;
    box-shadow:
        0 0 40px rgba(255,0,255,.3),
        0 0 80px rgba(0,255,255,.2);
    border:1px solid rgba(0,255,255,.2);
    position:relative;
    display:none
}

.app-container.visible{
    display:block
}

h1{
    text-align:center;
    font-size:2.8rem;
    background:
        linear-gradient(
            135deg,
            #ff5500,
            #ff00ff
        );
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    margin-bottom:8px
}

.arena-subtitle{
    text-align:center;
    color:#aaa;
    font-size:.9rem;
    margin-bottom:24px
}

.screen{
    display:none
}

.screen.active{
    display:block
}

.battle-input{
    width:100%;
    padding:15px 18px;
    margin:10px 0;
    border:1px solid rgba(0,255,255,.4);
    border-radius:14px;
    background:rgba(20,20,20,.9);
    color:#fff;
    font-size:1rem;
    outline:none
}

.battle-input:focus{
    background:#1e1e1e;
    box-shadow:0 0 15px #0ff;
    border-color:#0ff
}

.btn-primary{
    width:100%;
    padding:16px;
    margin:12px 0;
    border:none;
    border-radius:14px;
    background:
        linear-gradient(
            135deg,
            #ff5500,
            #ff00ff
        );
    color:#fff;
    font-weight:bold;
    font-size:1.2rem;
    cursor:pointer;
    box-shadow:0 0 25px rgba(255,0,255,.4);
    transition:transform .1s
}

.btn-primary:active{
    transform:scale(.97)
}

.btn-secondary{
    width:100%;
    padding:14px;
    margin:8px 0;
    border:1px solid #0ff;
    border-radius:14px;
    background:transparent;
    color:#0ff;
    font-weight:bold;
    cursor:pointer
}

.timer-big{
    font-size:5rem;
    text-align:center;
    font-weight:800;
    color:#0ff;
    text-shadow:0 0 30px cyan
}

.counter-big{
    font-size:4rem;
    text-align:center;
    font-weight:800;
    color:#f0f
}

.leaderboard-item{
    display:flex;
    align-items:center;
    gap:12px;
    padding:10px;
    background:#1a1a1a;
    border-radius:12px;
    margin:6px 0
}

.rank{
    font-size:1.5rem;
    font-weight:bold;
    width:40px
}

.score{
    margin-left:auto;
    font-weight:bold;
    color:#0ff
}

.score-date{
    font-size:.75rem;
    color:#888;
    margin-left:6px
}

.result-msg{
    text-align:center;
    font-size:1.3rem;
    margin:12px 0;
    font-style:italic;
    color:#f0f
}

.small{
    font-size:.85rem;
    color:#aaa
}

.share-btn{
    background:#0ff;
    color:black
}

video,
canvas{
    width:100%;
    border-radius:14px;
    background:#000
}

#aiCameraUI{
    position:relative;
    width:100%;
    height:250px;
    margin:10px 0;
    border-radius:14px;
    overflow:hidden;
    background:#000;
    display:block
}

#aiCameraUI video{
    display:block;
    position:absolute;
    top:0;
    left:0;
    width:100%;
    height:100%;
    object-fit:cover;
    z-index:3
}

#aiCameraUI canvas{
    display:block;
    position:absolute;
    top:0;
    left:0;
    width:100%;
    height:100%;
    object-fit:cover;
    z-index:4;
    background:transparent!important;
    pointer-events:none
}

.angle-overlay{
    position:absolute;
    top:50%;
    left:50%;
    transform:translate(-50%,-50%);
    font-size:5rem;
    font-weight:800;
    color:#0ff;
    text-shadow:0 0 30px cyan;
    pointer-events:none;
    z-index:5
}

.rep-flash{
    position:absolute;
    top:30%;
    left:50%;
    transform:translate(-50%,-50%);
    font-size:3rem;
    font-weight:800;
    color:#0f0;
    text-shadow:0 0 30px green;
    z-index:6;
    animation:fadeInOut .8s ease
}

.form-feedback{
    position:absolute;
    bottom:60px;
    left:50%;
    transform:translateX(-50%);
    background:rgba(0,0,0,.85);
    color:#ffcc00;
    padding:8px 16px;
    border-radius:10px;
    font-size:.9rem;
    font-weight:bold;
    z-index:10;
    border:1px solid #ffcc00;
    text-align:center;
    max-width:90%;
    transition:all .3s ease
}

.form-feedback.good{
    color:#00ff88;
    border-color:#00ff88
}

.form-feedback.bad{
    color:#ff4444;
    border-color:#ff4444
}

@keyframes fadeInOut{
    0%{
        opacity:0;
        transform:translate(-50%,-50%) scale(.5)
    }

    50%{
        opacity:1;
        transform:translate(-50%,-50%) scale(1.2)
    }

    100%{
        opacity:0;
        transform:translate(-50%,-50%) scale(1)
    }
}

.debug-msg{
    position:absolute;
    bottom:10px;
    left:10px;
    background:rgba(0,0,0,.8);
    color:#fa0;
    padding:6px 12px;
    border-radius:8px;
    font-size:14px;
    font-weight:bold;
    z-index:7;
    pointer-events:none
}

.motivation-banner{
    position:absolute;
    bottom:10px;
    left:50%;
    transform:translateX(-50%);
    width:95%;
    background:rgba(0,0,0,.85);
    border:1px solid #ff4500;
    border-radius:10px;
    padding:10px 13px;
    text-align:center;
    font-size:.8rem;
    color:#ccc;
    line-height:1.4;
    z-index:9999!important;
    display:none
}

.motivation-banner strong{
    color:#ff4500
}

.fade-out{
    animation:fadeOutBanner 1s ease forwards
}

@keyframes fadeOutBanner{
    0%{opacity:1}
    100%{opacity:0}
}

.ghost-overlay{
    position:absolute;
    top:10px;
    right:10px;
    background:rgba(0,0,0,.7);
    padding:8px 14px;
    border-radius:12px;
    font-size:1.2rem;
    z-index:8;
    display:none
}

.ghost-overlay .ghost-icon{
    font-size:1.5rem
}

.ghost-overlay .ghost-count{
    font-weight:bold;
    color:#aaa;
    margin-left:5px
}

.ghost-beaten{
    color:#0f0!important
}

.intro-overlay{
    position:fixed;
    top:0;
    left:0;
    width:100vw;
    height:100vh;
    background:
        radial-gradient(
            circle at 50% 40%,
            #0d071a 0%,
            #000 100%
        );
    z-index:99999;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    overflow:hidden
}

.intro-scene{
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:space-between;
    height:100%;
    width:100%;
    padding:60px 20px 40px
}

.intro-title-top{
    text-align:center;
    z-index:10
}

.intro-title-main{
    font-size:3.2rem;
    font-weight:900;
    color:transparent;
    background:
        linear-gradient(
            135deg,
            #ff4500,
            #ff00ff,
            #ff4500
        );
    background-size:200% 200%;
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    filter:drop-shadow(0 0 25px #ff00ff);
    animation:
        titleGlow 2s ease-in-out infinite,
        titleEntrance .8s ease forwards
}

.luffy-image-container{
    position:relative;
    width:220px;
    height:220px;
    display:flex;
    align-items:center;
    justify-content:center;
    z-index:2
}

.luffy-image{
    width:190px;
    height:190px;
    border-radius:50%;
    object-fit:cover;
    border:2px solid rgba(255,255,255,.15);
    box-shadow:
        0 0 40px rgba(255,69,0,.4),
        0 0 80px rgba(255,0,255,.3),
        0 0 120px rgba(255,100,0,.2);
    animation:
        cinematicEntrance 1.4s ease forwards,
        cinematicPulse 2.5s 1.4s ease-in-out infinite
}

@keyframes cinematicEntrance{
    0%{
        transform:scale(.3) translateY(30px);
        opacity:0;
        filter:brightness(.3)
    }

    60%{
        transform:scale(1.05) translateY(-5px);
        opacity:1;
        filter:brightness(1.2)
    }

    100%{
        transform:scale(1) translateY(0);
        opacity:1;
        filter:brightness(1)
    }
}

@keyframes cinematicPulse{
    0%,100%{
        box-shadow:
            0 0 40px rgba(255,69,0,.4),
            0 0 80px rgba(255,0,255,.3),
            0 0 120px rgba(255,100,0,.2)
    }

    50%{
        box-shadow:
            0 0 60px rgba(255,69,0,.7),
            0 0 100px rgba(255,0,255,.5),
            0 0 140px rgba(255,100,0,.4)
    }
}

@keyframes titleGlow{
    0%,100%{
        filter:drop-shadow(0 0 25px #ff00ff)
    }

    50%{
        filter:
            drop-shadow(0 0 45px #ff4500)
            drop-shadow(0 0 60px #ff00ff)
    }
}

@keyframes titleEntrance{
    0%{
        opacity:0;
        transform:translateY(-20px) scale(.7)
    }

    100%{
        opacity:1;
        transform:translateY(0) scale(1)
    }
}

.particle{
    position:absolute;
    width:4px;
    height:4px;
    border-radius:50%;
    background:#ff4500;
    animation:
        floatParticle 3s ease-in-out infinite;
    opacity:0;
    z-index:0
}

.particle:nth-child(1){
    top:15%;
    left:12%;
    animation-delay:0s;
    background:#ff00ff;
    width:5px;
    height:5px
}

.particle:nth-child(2){
    top:22%;
    right:10%;
    animation-delay:.6s
}

.particle:nth-child(3){
    top:50%;
    left:6%;
    animation-delay:1.1s;
    background:#0ff;
    width:6px;
    height:6px
}

.particle:nth-child(4){
    top:58%;
    right:8%;
    animation-delay:1.6s;
    background:#ff4500
}

.particle:nth-child(5){
    top:38%;
    left:22%;
    animation-delay:.9s;
    background:#ff00ff;
    width:5px;
    height:5px
}

.particle:nth-child(6){
    top:42%;
    right:18%;
    animation-delay:1.3s
}

.particle:nth-child(7){
    top:68%;
    left:16%;
    animation-delay:.4s;
    background:#0ff;
    width:4px;
    height:4px
}

.particle:nth-child(8){
    top:72%;
    right:12%;
    animation-delay:1.9s;
    background:#ff4500
}

@keyframes floatParticle{
    0%{
        opacity:0;
        transform:translateY(0) scale(0)
    }

    30%{
        opacity:.8;
        transform:translateY(-25px) scale(1)
    }

    100%{
        opacity:0;
        transform:translateY(50px) scale(.3)
    }
}

.intro-tagline{
    font-size:1rem;
    color:#ccc;
    letter-spacing:3px;
    animation:
        tagAppear 1s .5s ease forwards;
    opacity:0;
    text-align:center;
    margin-top:10px
}

@keyframes tagAppear{
    0%{
        opacity:0;
        transform:translateY(10px)
    }

    100%{
        opacity:1;
        transform:translateY(0)
    }
}

.skip-btn{
    position:absolute;
    top:20px;
    right:20px;
    background:rgba(255,255,255,.1);
    color:#aaa;
    padding:6px 16px;
    border-radius:20px;
    font-size:.8rem;
    cursor:pointer;
    z-index:999
}

.intro-fadeout{
    animation:fadeOutIntro .8s ease forwards
}

@keyframes fadeOutIntro{
    0%{
        opacity:1
    }

    100%{
        opacity:0;
        visibility:hidden
    }
}

.luffy-badge{
    position:fixed;
    top:15px;
    right:15px;
    z-index:10000;
    cursor:pointer;
    display:flex;
    flex-direction:column;
    align-items:center
}

.luffy-img{
    width:70px;
    height:70px;
    border-radius:50%;
    object-fit:cover;
    border:none;
    box-shadow:
        0 0 15px rgba(0,191,255,.6),
        0 0 30px rgba(255,69,0,.4)
}

.ceo-label{
    font-size:.7rem;
    color:#ddd;
    margin-top:6px;
    background:rgba(0,0,0,.7);
    padding:3px 10px;
    border-radius:12px;
    text-align:center
}

.ceo-arrow{
    position:fixed;
    top:30px;
    right:90px;
    font-size:1.8rem;
    color:#fff;
    animation:
        arrowBounce .8s ease-in-out infinite;
    pointer-events:none;
    z-index:10000;
    filter:
        drop-shadow(
            0 0 6px rgba(255,255,255,.8)
        )
}

@keyframes arrowBounce{
    0%,100%{
        transform:translateX(0)
    }

    50%{
        transform:translateX(8px)
    }
}

.active-users-pill{
    position:fixed;
    top:15px;
    left:15px;
    z-index:10000;
    display:flex;
    align-items:center;
    gap:6px;
    background:rgba(0,0,0,.7);
    backdrop-filter:blur(8px);
    padding:6px 12px;
    border-radius:20px;
    border:1px solid rgba(0,255,255,.4);
    box-shadow:
        0 0 12px rgba(0,255,255,.3)
}

.active-users-pill .user-icon{
    font-size:1.2rem
}

.active-users-pill .count{
    font-weight:bold;
    font-size:1rem;
    color:#0ff
}

.ceo-modal-overlay{
    position:fixed;
    top:0;
    left:0;
    width:100%;
    height:100%;
    background:rgba(0,0,0,.85);
    backdrop-filter:blur(10px);
    z-index:20000;
    display:none;
    align-items:center;
    justify-content:center
}

.ceo-modal-overlay.active{
    display:flex
}

.ceo-modal{
    background:#1a1a1a;
    border-radius:24px;
    padding:30px 24px;
    max-width:320px;
    width:90%;
    text-align:center;
    border:1px solid rgba(0,255,255,.3);
    box-shadow:
        0 0 40px rgba(0,255,255,.2)
}

.ceo-modal h2{
    font-size:1.6rem;
    margin:8px 0;
    background:
        linear-gradient(
            135deg,
            #ff4500,
            #00bfff
        );
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent
}

.ceo-modal .title{
    color:#fa0;
    font-weight:bold;
    margin-bottom:10px;
    font-size:.95rem
}

.ceo-modal .phone{
    color:#0ff;
    font-size:1.3rem;
    margin:8px 0;
    font-weight:bold
}

.close-btn{
    background:none;
    border:1px solid #555;
    color:#aaa;
    padding:6px 20px;
    border-radius:20px;
    margin-top:18px;
    cursor:pointer
}

.wa-btn{
    display:inline-block;
    margin-top:12px;
    background:#25D366;
    color:#fff;
    padding:10px 18px;
    border-radius:25px;
    text-decoration:none;
    font-weight:bold;
    font-size:1rem;
    box-shadow:
        0 0 12px rgba(37,211,102,.5)
}

.instruction-box{
    background:rgba(0,0,0,.8);
    border-radius:20px;
    padding:20px;
    margin:20px 0
}

.instruction-box p{
    font-size:1rem;
    line-height:1.8;
    margin:8px 0;
    color:#ddd
}

.checkbox-row{
    display:flex;
    align-items:center;
    gap:12px;
    margin:20px 0;
    justify-content:center
}

.checkbox-row input{
    width:20px;
    height:20px;
    accent-color:#ff4500
}

.checkbox-row label{
    font-size:.9rem;
    color:#ccc
}

.stats-box{
    background:rgba(0,0,0,.7);
    border-radius:16px;
    padding:16px;
    margin:10px 0
}

.stats-row{
    display:flex;
    gap:12px;
    margin:10px 0
}

.stats-card{
    flex:1;
    background:#1a1a1a;
    border-radius:12px;
    padding:12px;
    text-align:center
}

.stats-card .big-num{
    font-size:2rem;
    font-weight:bold;
    color:#0ff
}

.recent-item{
    display:flex;
    justify-content:space-between;
    padding:8px 0;
    border-bottom:1px solid #333
}

.weekly-plan-container{
    background:rgba(0,0,0,.7);
    border-radius:16px;
    padding:16px;
    margin:15px 0
}

.day-row{
    display:flex;
    align-items:center;
    gap:10px;
    padding:8px 0;
    border-bottom:1px solid #222;
    position:relative
}

.day-row:last-child{
    border-bottom:none
}

.day-label{
    width:35px;
    font-weight:bold;
    color:#ccc
}

.day-date{
    font-size:.7rem;
    color:#888;
    width:45px
}

.progress-container{
    flex:1;
    height:8px;
    background:#333;
    border-radius:4px;
    overflow:hidden
}

.progress-bar{
    height:100%;
    background:
        linear-gradient(
            90deg,
            #00bfff,
            #00ff88
        );
    width:0%;
    transition:width .5s ease;
    border-radius:4px
}

.progress-bar.rest{
    background:#444
}

.progress-bar.over{
    background:
        linear-gradient(
            90deg,
            #ff4500,
            #ff00ff
        )
}

.day-status{
    font-size:.7rem;
    width:60px;
    text-align:right;
    color:#aaa
}

.day-row.rest-day .day-label{
    color:#ff4500
}

.day-row.rest-day .day-status{
    color:#ff4500
}

.day-row.today{
    background:rgba(0,255,255,.05);
    border-radius:8px;
    padding:8px;
    animation:pulseToday 2s infinite
}

@keyframes pulseToday{
    0%,100%{
        box-shadow:0 0 0 rgba(0,255,255,0)
    }

    50%{
        box-shadow:0 0 12px rgba(0,255,255,.3)
    }
}

.ai-assistant{
    position:fixed;
    bottom:20px;
    right:20px;
    z-index:15000;
    background:
        linear-gradient(
            135deg,
            #ff4500,
            #ff00ff
        );
    color:#fff;
    padding:10px 16px;
    border-radius:20px;
    font-size:.85rem;
    max-width:250px;
    box-shadow:
        0 0 20px rgba(255,0,255,.4);
    cursor:pointer
}

.ai-msg{
    display:block;
    line-height:1.4
}

.ai-mute{
    position:absolute;
    top:-8px;
    right:-8px;
    background:#fff;
    color:#000;
    width:24px;
    height:24px;
    border-radius:50%;
    font-size:.8rem;
    border:none;
    cursor:pointer
}

</style>

</head>


<body>


<!-- ========================================================
     INTRO
========================================================= -->

<div
    id="introOverlay"
    class="intro-overlay"
>

    <div
        class="skip-btn"
        onclick="skipIntro()"
    >
        Tap to skip →
    </div>

    <div class="intro-scene">

        <div class="intro-title-top">
            <div class="intro-title-main">
                PUSHCLASH
            </div>
        </div>

        <div class="luffy-image-container">

            <img
                class="luffy-image"
                src="https://raw.githubusercontent.com/PUSHCLASH/PUSHCLASH/main/luffy%20image.jpeg"
                alt="Luffy Gear 5"
            >

            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>

        </div>

        <div class="intro-tagline">
            ⚡ GEAR 5 — AWAKENED ⚡
        </div>

    </div>

</div>


<!-- ========================================================
     ACTIVE USERS
========================================================= -->

<div
    class="active-users-pill"
    id="activeUsersPill"
>

    <span class="user-icon">
        👥
    </span>

    <span
        class="count"
        id="activeUserCount"
    >
        0
    </span>

    <span
        style="font-size:.8rem;color:#aaa"
    >
        online
    </span>

</div>


<!-- ========================================================
     CEO
========================================================= -->

<div
    class="luffy-badge"
    onclick="document.getElementById('ceoModal').classList.add('active')"
>

    <img
        class="luffy-img"
        src="https://raw.githubusercontent.com/PUSHCLASH/PUSHCLASH/main/luffy%20image.jpeg"
    >

    <span class="ceo-label">
        CEO of App
    </span>

</div>

<div class="ceo-arrow">
    👉
</div>


<div
    id="ceoModal"
    class="ceo-modal-overlay"
    onclick="this.classList.remove('active')"
>

    <div
        class="ceo-modal"
        onclick="event.stopPropagation()"
    >

        <div
            style="font-size:2rem;margin-bottom:8px"
        >
            👑
        </div>

        <h2>
            KAUSHTUBH
        </h2>

        <div class="title">
            CEO OF PUSH CLASH
        </div>

        <div
            style="color:#ccc;font-size:.9rem;margin:6px 0"
        >
            Have a query? Get in touch
        </div>

        <div class="phone">
            📞 8950592855
        </div>

        <a
            href="https://wa.me/918950592855?text=Hey%20Kaushtubh%2C%20I%20have%20a%20query%20about%20PushClash"
            target="_blank"
            class="wa-btn"
        >
            📱 Message on WhatsApp
        </a>

        <button
            class="close-btn"
            onclick="document.getElementById('ceoModal').classList.remove('active')"
        >
            Close
        </button>

    </div>

</div>


<!-- ========================================================
     AI ASSISTANT
========================================================= -->

<div
    class="ai-assistant"
    id="aiAssistant"
    onclick="speakAIMessage()"
>

    <button
        class="ai-mute"
        id="aiMuteBtn"
        onclick="event.stopPropagation();toggleMute()"
    >
        🔊
    </button>

    <span
        class="ai-msg"
        id="aiMessage"
    >
        💬 Loading your coach...
    </span>

</div>


<!-- ========================================================
     MAIN APP
========================================================= -->

<div
    class="app-container"
    id="appContainer"
>


<!-- ========================================================
     SETUP
========================================================= -->

<div
    id="setupScreen"
    class="screen"
>

    <h1>
        PUSHCLASH
    </h1>

    <div class="arena-subtitle">
        ⚔️ ENTER THE ARENA ⚔️
    </div>

    <div
        style="font-size:3rem;text-align:center;margin-bottom:10px"
    >
        🛡️🔥🛡️
    </div>

    <input
        class="battle-input"
        id="nameInput"
        placeholder="Your Warrior Name"
        maxlength="30"
    >

    <input
        class="battle-input"
        id="nationalityInput"
        placeholder="Nationality"
        maxlength="30"
    >

    <input
        class="battle-input"
        id="emailInput"
        placeholder="Email (your battle ID)"
        maxlength="50"
    >

    <div
        class="error-msg"
        id="setupError"
    ></div>

    <button
        class="btn-primary"
        onclick="saveProfile()"
    >
        ⚡ ENTER ARENA ⚡
    </button>

    <p
        class="small"
        style="text-align:center;margin-top:16px"
    >
        Only real warriors dare to compete
    </p>

</div>


<!-- ========================================================
     INSTRUCTIONS
========================================================= -->

<div
    id="instructionScreen"
    class="screen"
>

    <h1
        style="font-size:2rem;margin-bottom:20px"
    >
        🚀 WELCOME, WARRIOR!
    </h1>

    <div class="instruction-box">

        <p>
            🤖 PushClash is an
            <strong>AI fitness battlefield</strong>
            where you crush push-ups and your reps
            are counted live by our AI referee.
        </p>

        <p>
            ⏱️ You get
            <strong>60 seconds</strong>
            to do as many clean push-ups as possible.
            Every rep counts, every second matters.
        </p>

        <p>
            🏆 Your best score hits the
            <strong>Weekly Global Leaderboard</strong>.
            Rise up, own your nation, become the #1
            push-up legend.
        </p>

        <p>
            👑 This app was built with pure hustle by
            <strong>Kaushtubh (CEO)</strong>.
        </p>

        <p>
            🔥 No mercy, no shortcuts.
            Only raw power brings glory.
        </p>

    </div>

    <div class="checkbox-row">

        <input
            type="checkbox"
            id="agreeCheck"
        >

        <label for="agreeCheck">
            I have read all instructions carefully
        </label>

    </div>

    <button
        class="btn-primary"
        id="enterArenaBtn"
        disabled
        onclick="showScreen('dashboardScreen');loadStats();speakWelcome();"
    >
        ⚡ I'M READY, ENTER ARENA ⚡
    </button>

</div>


<!-- ========================================================
     DASHBOARD
========================================================= -->

<div
    id="dashboardScreen"
    class="screen"
>

    <h1>
        PUSHCLASH
    </h1>

    <p style="font-size:1.4rem">
        Welcome,
        <span id="dashName"></span>!
    </p>

    <p class="small">
        🌍
        <span id="dashNationality"></span>
    </p>

    <div
        style="display:flex;gap:12px;margin:20px 0"
    >

        <div
            style="flex:1;background:#1a1a1a;border-radius:14px;padding:12px;text-align:center"
        >

            <div
                style="font-size:2rem;font-weight:bold;color:#0ff"
                id="personalBest"
            >
                0
            </div>

            <div class="small">
                Personal Best
            </div>

        </div>

        <div
            style="flex:1;background:#1a1a1a;border-radius:14px;padding:12px;text-align:center"
        >

            <div
                style="font-size:2rem;font-weight:bold;color:#f0f"
                id="totalBattles"
            >
                0
            </div>

            <div class="small">
                Total Battles
            </div>

        </div>

    </div>

    <div
        style="display:flex;gap:12px;margin:10px 0;color:#ff0"
    >

        <span
            id="streakDisplay"
            style="font-size:.9rem"
        >
            🔥 Streak: 0 days
        </span>

        <span
            id="targetDisplay"
            style="font-size:.9rem"
        >
            🎯 Daily target: 10
        </span>

    </div>

    <button
        class="btn-primary"
        onclick="startChallenge('normal')"
    >
        🤖 START AI BATTLE
    </button>

    <button
        class="btn-primary"
        onclick="startChallenge('ghost')"
        style="background:linear-gradient(135deg,#6a0dad,#00bfff)"
        id="ghostBtn"
    >
        👻 RACE MY GHOST
    </button>

    <button
        class="btn-secondary"
        onclick="showLeaderboard()"
    >
        🏆 Weekly Leaderboard
    </button>

    <button
        class="btn-secondary"
        onclick="showStats()"
    >
        📊 MY STATS
    </button>

    <button
        class="btn-secondary"
        onclick="resetProfile()"
    >
        🔄 Leave Arena
    </button>

    <div
        class="success-msg"
        id="saveConfirmation"
        style="display:none"
    >
        ✅ Score saved to global arena!
    </div>

</div>


<!-- ========================================================
     STATS
========================================================= -->

<div
    id="statsScreen"
    class="screen"
>

    <h1>
        📊 MY STATS & PLAN
    </h1>

    <div class="stats-box">

        <div class="stats-row">

            <div class="stats-card">

                <div
                    class="big-num"
                    id="statTotalPushups"
                >
                    0
                </div>

                <div class="label">
                    Total Push-ups
                </div>

            </div>

            <div class="stats-card">

                <div
                    class="big-num"
                    id="statBest"
                >
                    0
                </div>

                <div class="label">
                    Personal Best
                </div>

            </div>

        </div>

        <div class="stats-row">

            <div class="stats-card">

                <div
                    class="big-num"
                    id="statBattles"
                >
                    0
                </div>

                <div class="label">
                    Battles Fought
                </div>

            </div>

            <div class="stats-card">

                <div
                    class="big-num"
                    id="statRank"
                >
                    -
                </div>

                <div class="label">
                    Weekly Rank
                </div>

            </div>

        </div>

    </div>

    <h3>
        📅 SMART WEEKLY PLAN
    </h3>

    <div
        id="weeklyPlanContainer"
        class="weekly-plan-container"
    >
        Loading your personalized plan...
    </div>

    <h3>
        📜 Recent Battles
    </h3>

    <div
        id="recentBattlesList"
        style="max-height:200px;overflow-y:auto"
    ></div>

    <button
        class="btn-secondary"
        onclick="showScreen('dashboardScreen')"
    >
        ← Back to Arena
    </button>

</div>


<!-- ========================================================
     CHALLENGE
========================================================= -->

<div
    id="challengeScreen"
    class="screen"
>

    <div
        id="countdownDisplay"
        class="timer-big"
        style="font-size:4rem"
    >
        3
    </div>

    <div
        id="challengeActiveUI"
        style="display:none"
    >

        <div
            class="timer-big"
            id="timerDisplay"
        >
            60
        </div>

        <div
            class="counter-big"
            id="repCounter"
        >
            0
        </div>


        <div
            id="aiCameraUI"
        >

            <canvas
                id="poseCanvas"
            ></canvas>

            <video
                id="webcam"
                autoplay
                playsinline
                muted
            ></video>

            <div
                class="angle-overlay"
                id="angleOverlay"
            ></div>

            <div
                class="rep-flash"
                id="repFlash"
                style="display:none"
            >
                REP!
            </div>

            <div
                class="form-feedback"
                id="formFeedback"
            ></div>

            <div
                class="debug-msg"
                id="debugMsg"
            ></div>

            <div
                class="motivation-banner"
                id="motivationBanner"
            >

                <strong>
                    👁️ THE AI IS WATCHING EVERY REP 👁️
                </strong>

                <br>

                Start your push-ups NOW!
                No distractions, no excuses —
                pure power only.

            </div>

            <div
                class="ghost-overlay"
                id="ghostOverlay"
            >

                <span class="ghost-icon">
                    👻
                </span>

                <span
                    class="ghost-count"
                    id="ghostCount"
                >
                    0
                </span>

            </div>

        </div>

    </div>


    <div
        id="battleResultUI"
        style="display:none;text-align:center"
    >

        <h2>
            ⚔️ Battle Over!
        </h2>

        <div
            style="font-size:3rem;color:#0ff"
            id="finalScore"
        >
            0
        </div>

        <div
            class="result-msg"
            id="trashTalk"
        ></div>

        <div
            class="champion-voice-text"
            id="championText"
            style="display:none"
        >
            "Champions are built in losses,
            my friend. Come back stronger."
        </div>

        <button
            class="btn-primary"
            onclick="shareScore()"
        >
            📢 Share My Score
        </button>

        <button
            class="btn-secondary"
            onclick="goToDashboard()"
        >
            Back to Arena
        </button>

    </div>

</div>


<!-- ========================================================
     LEADERBOARD
========================================================= -->

<div
    id="leaderboardScreen"
    class="screen"
>

    <h1>
        WEEKLY RANKINGS
    </h1>

    <p
        class="small"
        style="text-align:center"
    >
        Top 10 of the last 7 days
    </p>

    <div id="leaderboardList"></div>

    <button
        class="btn-secondary"
        onclick="showScreen('dashboardScreen')"
        style="margin-top:16px"
    >
        ← Back to Arena
    </button>

</div>


</div>


<!-- ========================================================
     TENSORFLOW + MOVENET
========================================================= -->

<script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4"></script>

<script src="https://cdn.jsdelivr.net/npm/@tensorflow-models/pose-detection@2"></script>


<script>


// ============================================================
// GLOBAL VARIABLES
// ============================================================

let currentUser = null;

let repCount = 0;

let timeLeft = 60;

let challengeInterval = null;

let countdownInterval = null;

let challengeMode = "normal";

let aiDetector = null;

let aiStream = null;

let aiReady = false;

let muteAI = false;

let idleTimer = null;

let bannerTimer = null;

let ghostTimestamps = [];

let battleStartTime = 0;

let ghostData = null;

let lastFeedbackTime = 0;

const BASE = window.location.origin;


// ============================================================
// AI REP DETECTION SETTINGS
// ============================================================
//
// These values are intentionally separated so the AI
// detection can be tuned without changing the UI.
//

const AI_CONFIG = {

    // Keypoint confidence
    minKeypointScore: 0.45,

    // Down position
    downAngle: 105,

    // Strong bottom position
    bottomAngle: 92,

    // Up position
    upAngle: 155,

    // Minimum movement between states
    minimumMovement: 45,

    // Minimum time between two reps
    repCooldown: 450,

    // Number of angle samples used for smoothing
    smoothingWindow: 5,

    // How long the user must remain around bottom
    bottomHoldFrames: 2,

    // Require several valid frames
    stableFrames: 2
};


// ============================================================
// AI STATE MACHINE
// ============================================================

let aiState = "UP";

let angleBuffer = [];

let lastRepTime = 0;

let bottomFrames = 0;

let upStableFrames = 0;

let downStableFrames = 0;

let lastStableAngle = null;

let validArm = null;


// ============================================================
// INTRO
// ============================================================

function skipIntro() {

    clearTimeout(window._introTimer);

    const overlay =
        document.getElementById("introOverlay");

    overlay.classList.add("intro-fadeout");

    setTimeout(() => {

        overlay.style.display = "none";

        proceedToApp();

    }, 800);
}


function proceedToApp() {

    document
        .getElementById("appContainer")
        .classList.add("visible");

    currentUser =
        JSON.parse(
            localStorage.getItem("pushclash_user")
        );

    if (currentUser) {

        showScreen("dashboardScreen");

        loadStats();

    } else {

        showScreen("setupScreen");

    }
}


window.addEventListener("load", () => {

    const overlay =
        document.getElementById("introOverlay");

    overlay.style.display = "flex";

    window._introTimer =
        setTimeout(() => {

            overlay.classList.add(
                "intro-fadeout"
            );

            setTimeout(() => {

                overlay.style.display = "none";

                proceedToApp();

            }, 800);

        }, 5000);

});


// ============================================================
// ACTIVE USERS
// ============================================================

async function refreshActiveCount() {

    try {

        const response =
            await fetch("/api/active_users");

        const data =
            await response.json();

        document
            .getElementById("activeUserCount")
            .textContent = data.count;

    } catch (error) {

    }
}


setInterval(
    refreshActiveCount,
    10000
);


// ============================================================
// AI VOICE
// ============================================================

function speak(message) {

    if (muteAI) return;

    if (!("speechSynthesis" in window))
        return;

    speechSynthesis.cancel();

    const utterance =
        new SpeechSynthesisUtterance(message);

    utterance.lang = "en-US";

    utterance.rate = 0.95;

    speechSynthesis.speak(utterance);
}


function toggleMute() {

    muteAI = !muteAI;

    document
        .getElementById("aiMuteBtn")
        .textContent = muteAI
            ? "🔇"
            : "🔊";
}


function setAIMessage(message) {

    document
        .getElementById("aiMessage")
        .textContent = message;
}


function speakAIMessage() {

    speak(
        document
            .getElementById("aiMessage")
            .textContent
    );
}


// ============================================================
// IDLE
// ============================================================

function resetIdleTimer() {

    if (idleTimer)
        clearTimeout(idleTimer);

    idleTimer = setTimeout(() => {

        if (
            document
                .getElementById("dashboardScreen")
                .classList
                .contains("active")
            &&
            currentUser
        ) {

            speak(
                "Hey " +
                currentUser.name +
                ", you haven't started a battle yet. Let's crush those push-ups!"
            );

            setAIMessage(
                "💤 Still resting, " +
                currentUser.name +
                "? Your push-up target is waiting!"
            );
        }

    }, 120000);
}


// ============================================================
// DASHBOARD
// ============================================================

async function updateDashboardInfo() {

    if (!currentUser)
        return;

    try {

        const [
            streakResponse,
            targetResponse
        ] = await Promise.all([

            fetch(
                "/api/streak?email=" +
                encodeURIComponent(
                    currentUser.email
                )
            ),

            fetch(
                "/api/target?email=" +
                encodeURIComponent(
                    currentUser.email
                )
            )

        ]);

        const streakData =
            await streakResponse.json();

        const targetData =
            await targetResponse.json();

        document
            .getElementById("streakDisplay")
            .textContent =
            "🔥 Streak: " +
            streakData.streak +
            " days";

        document
            .getElementById("targetDisplay")
            .textContent =
            "🎯 Target: " +
            targetData.todayDone +
            "/" +
            targetData.target;

        return {
            streak: streakData.streak,
            target: targetData.target,
            done: targetData.todayDone
        };

    } catch (error) {

        return {
            streak: 0,
            target: 10,
            done: 0
        };
    }
}


async function speakDashboardWelcome() {

    if (!currentUser)
        return;

    const data =
        await updateDashboardInfo();

    const remaining =
        Math.max(
            0,
            data.target - data.done
        );

    const message =
        `Welcome back, ${currentUser.name}! ` +
        `Your streak is ${data.streak} days. ` +
        `Today's push-up target is ${data.target}. ` +
        `You've done ${data.done}, ${remaining} to go!`;

    speak(message);

    setAIMessage(
        "💬 " + message
    );

    resetIdleTimer();
}


function speakWelcome() {

    const utterance =
        new SpeechSynthesisUtterance(
            "Welcome to PushClash. This is the world where people battle for fitness."
        );

    utterance.lang = "en-US";

    utterance.rate = 0.9;

    utterance.pitch = 1.1;

    speechSynthesis.speak(
        utterance
    );

    speakDashboardWelcome();
}


function speakChampion() {

    const utterance =
        new SpeechSynthesisUtterance(
            "Champions are built in losses, my friend. Come back stronger."
        );

    utterance.lang = "en-US";

    utterance.rate = 0.85;

    utterance.pitch = 0.8;

    speechSynthesis.speak(
        utterance
    );
}


// ============================================================
// PROFILE
// ============================================================

async function saveProfile() {

    const name =
        document
            .getElementById("nameInput")
            .value
            .trim();

    const nationality =
        document
            .getElementById("nationalityInput")
            .value
            .trim();

    const email =
        document
            .getElementById("emailInput")
            .value
            .trim();

    const errorElement =
        document
            .getElementById("setupError");

    if (!name || !nationality || !email) {

        errorElement.textContent =
            "All fields are required!";

        return;
    }

    if (
        !email.includes("@") ||
        !email.includes(".")
    ) {

        errorElement.textContent =
            "Please enter a valid email";

        return;
    }

    try {

        const response =
            await fetch(
                "/api/check-email",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        email: email
                    })
                }
            );

        const data =
            await response.json();

        if (data.exists) {

            errorElement.textContent =
                "This email is already registered.";

            return;
        }

    } catch (error) {

        errorElement.textContent =
            "Unable to connect to server.";

        return;
    }

    errorElement.textContent = "";

    currentUser = {
        name: name,
        nationality: nationality,
        email: email
    };

    localStorage.setItem(
        "pushclash_user",
        JSON.stringify(currentUser)
    );

    showScreen(
        "instructionScreen"
    );
}


document
    .getElementById("agreeCheck")
    .addEventListener(
        "change",
        function () {

            document
                .getElementById(
                    "enterArenaBtn"
                )
                .disabled =
                !this.checked;

        }
    );


function resetProfile() {

    localStorage.removeItem(
        "pushclash_user"
    );

    currentUser = null;

    showScreen(
        "setupScreen"
    );
}


function showScreen(id) {

    document
        .querySelectorAll(".screen")
        .forEach(
            element =>
                element.classList.remove(
                    "active"
                )
        );

    document
        .getElementById(id)
        .classList.add("active");

    const confirmation =
        document.getElementById(
            "saveConfirmation"
        );

    if (
        confirmation &&
        id !== "dashboardScreen"
    ) {

        confirmation.style.display =
            "none";
    }

    if (id === "dashboardScreen") {

        resetIdleTimer();

        updateDashboardInfo();

        loadGhostButton();
    }
}


function goToDashboard() {

    stopCamera();

    loadStats();

    showScreen(
        "dashboardScreen"
    );

    resetIdleTimer();
}


// ============================================================
// STATS
// ============================================================

async function loadStats() {

    if (!currentUser)
        return;

    document
        .getElementById("dashName")
        .textContent =
        currentUser.name;

    document
        .getElementById("dashNationality")
        .textContent =
        currentUser.nationality;

    try {

        const response =
            await fetch(
                "/api/stats",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        email:
                            currentUser.email
                    })
                }
            );

        const data =
            await response.json();

        document
            .getElementById("personalBest")
            .textContent =
            data.personalBest;

        document
            .getElementById("totalBattles")
            .textContent =
            data.totalBattles;

        localStorage.setItem(
            "pushclash_stats",
            JSON.stringify(data)
        );

        refreshActiveCount();

    } catch (error) {

    }
}


async function loadGhostButton() {

    if (!currentUser)
        return;

    try {

        const response =
            await fetch(
                "/api/ghost?email=" +
                encodeURIComponent(
                    currentUser.email
                )
            );

        const data =
            await response.json();

        const button =
            document.getElementById(
                "ghostBtn"
            );

        if (
            data.ghost &&
            data.ghost.score > 0
        ) {

            button.style.display =
                "block";

            button.textContent =
                `👻 RACE MY GHOST (PB: ${data.ghost.score})`;

        } else {

            button.style.display =
                "none";
        }

    } catch (error) {

        document
            .getElementById("ghostBtn")
            .style.display = "none";
    }
}


async function showStats() {

    if (!currentUser)
        return;

    const response =
        await fetch(
            "/api/stats",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body: JSON.stringify({
                    email:
                        currentUser.email
                })
            }
        );

    const data =
        await response.json();

    document
        .getElementById(
            "statTotalPushups"
        )
        .textContent =
        data.totalPushups;

    document
        .getElementById("statBest")
        .textContent =
        data.personalBest;

    document
        .getElementById("statBattles")
        .textContent =
        data.totalBattles;

    document
        .getElementById("statRank")
        .textContent =
        data.rank;

    const container =
        document.getElementById(
            "recentBattlesList"
        );

    if (!data.recentBattles.length) {

        container.innerHTML =
            '<p style="color:#aaa">No battles yet.</p>';

    } else {

        container.innerHTML =
            data.recentBattles
                .map(
                    battle =>
                        `<div class="recent-item">
                            <span>🔥 ${battle.score}</span>
                            <span class="small">${battle.date}</span>
                        </div>`
                )
                .join("");
    }

    loadWeeklyPlan();

    showScreen(
        "statsScreen"
    );
}


async function loadWeeklyPlan() {

    if (!currentUser)
        return;

    try {

        const response =
            await fetch(
                "/api/weekly-plan?email=" +
                encodeURIComponent(
                    currentUser.email
                )
            );

        if (!response.ok)
            throw new Error(
                "Server error"
            );

        const plan =
            await response.json();

        const container =
            document.getElementById(
                "weeklyPlanContainer"
            );

        if (
            !plan.days ||
            !plan.days.length
        ) {

            container.innerHTML =
                '<p style="color:#aaa">No plan data yet. Start battling!</p>';

            return;
        }

        let html = "";

        plan.days.forEach(day => {

            const percent =
                day.target > 0
                    ? Math.min(
                        100,
                        Math.round(
                            (
                                day.done /
                                day.target
                            ) * 100
                        )
                    )
                    : 0;

            const overTarget =
                day.target > 0 &&
                day.done >= day.target;

            const barClass =
                day.is_rest
                    ? "rest"
                    : (
                        overTarget
                            ? "over"
                            : ""
                    );

            const statusText =
                day.is_rest
                    ? "REST"
                    : (
                        overTarget
                            ? "Crushed!"
                            : (
                                day.done > 0
                                    ? `${day.done}/${day.target}`
                                    : `0/${day.target}`
                            )
                    );

            const todayClass =
                day.is_today
                    ? " today"
                    : "";

            const restClass =
                day.is_rest
                    ? " rest-day"
                    : "";

            html += `
                <div class="day-row${todayClass}${restClass}">

                    <span class="day-label">
                        ${day.is_rest ? "😴" : "💪"}
                        ${day.day}
                    </span>

                    <span class="day-date">
                        ${day.date.slice(5)}
                    </span>

                    <div class="progress-container">

                        <div
                            class="progress-bar ${barClass}"
                            style="width:${day.is_rest ? 0 : percent}%"
                        ></div>

                    </div>

                    <span class="day-status">
                        ${statusText}
                    </span>

                </div>
            `;
        });

        container.innerHTML =
            html;

    } catch (error) {

        document
            .getElementById(
                "weeklyPlanContainer"
            )
            .innerHTML =
            '<p style="color:#aaa">Could not load plan.</p>';
    }
}


// ============================================================
// ANGLE CALCULATION
// ============================================================

function calculateAngle(a, b, c) {

    if (!a || !b || !c)
        return null;

    const radians =
        Math.atan2(
            c.y - b.y,
            c.x - b.x
        )
        -
        Math.atan2(
            a.y - b.y,
            a.x - b.x
        );

    let angle =
        Math.abs(
            radians * 180 / Math.PI
        );

    if (angle > 180)
        angle = 360 - angle;

    return angle;
}


// ============================================================
// KEYPOINT VALIDATION
// ============================================================

function isGoodPoint(point) {

    return (
        point &&
        typeof point.x === "number" &&
        typeof point.y === "number" &&
        (
            typeof point.score !== "number" ||
            point.score >=
                AI_CONFIG.minKeypointScore
        )
    );
}


// ============================================================
// GET ARM ANGLE
// ============================================================
//
// We don't blindly average two arms.
// The AI chooses reliable arms based on
// keypoint confidence.
//
// This is important because one arm can disappear
// from the camera for a few frames.
//

function getArmAngles(keypoints) {

    const leftShoulder = keypoints[5];
    const rightShoulder = keypoints[6];

    const leftElbow = keypoints[7];
    const rightElbow = keypoints[8];

    const leftWrist = keypoints[9];
    const rightWrist = keypoints[10];

    const result = [];

    if (
        isGoodPoint(leftShoulder) &&
        isGoodPoint(leftElbow) &&
        isGoodPoint(leftWrist)
    ) {

        const angle =
            calculateAngle(
                leftShoulder,
                leftElbow,
                leftWrist
            );

        if (
            angle !== null &&
            angle >= 20 &&
            angle <= 180
        ) {

            result.push({
                side: "left",
                angle: angle
            });
        }
    }


    if (
        isGoodPoint(rightShoulder) &&
        isGoodPoint(rightElbow) &&
        isGoodPoint(rightWrist)
    ) {

        const angle =
            calculateAngle(
                rightShoulder,
                rightElbow,
                rightWrist
            );

        if (
            angle !== null &&
            angle >= 20 &&
            angle <= 180
        ) {

            result.push({
                side: "right",
                angle: angle
            });
        }
    }

    return result;
}


// ============================================================
// GET STABLE ARM ANGLE
// ============================================================

function getStableAngle(keypoints) {

    const arms =
        getArmAngles(keypoints);

    if (!arms.length)
        return null;

    if (arms.length === 1) {

        validArm =
            arms[0].side;

        return arms[0].angle;
    }


    // If both arms exist, average them.
    const average =
        (
            arms[0].angle +
            arms[1].angle
        ) / 2;

    validArm = "both";

    return average;
}


// ============================================================
// ANGLE SMOOTHING
// ============================================================

function addAngleSample(angle) {

    if (
        typeof angle !== "number" ||
        !Number.isFinite(angle)
    ) {
        return null;
    }

    angleBuffer.push(angle);

    if (
        angleBuffer.length >
        AI_CONFIG.smoothingWindow
    ) {

        angleBuffer.shift();
    }

    const total =
        angleBuffer.reduce(
            (sum, value) =>
                sum + value,
            0
        );

    return (
        total /
        angleBuffer.length
    );
}


// ============================================================
// FORM ANALYSIS
// ============================================================

function analyzeForm(keypoints) {

    const leftShoulder = keypoints[5];
    const rightShoulder = keypoints[6];

    const leftElbow = keypoints[7];
    const rightElbow = keypoints[8];

    const leftWrist = keypoints[9];
    const rightWrist = keypoints[10];

    const leftHip = keypoints[11];
    const rightHip = keypoints[12];

    if (
        !isGoodPoint(leftShoulder) ||
        !isGoodPoint(rightShoulder) ||
        !isGoodPoint(leftElbow) ||
        !isGoodPoint(rightElbow) ||
        !isGoodPoint(leftWrist) ||
        !isGoodPoint(rightWrist) ||
        !isGoodPoint(leftHip) ||
        !isGoodPoint(rightHip)
    ) {

        return null;
    }


    const leftAngle =
        calculateAngle(
            leftShoulder,
            leftElbow,
            leftWrist
        );

    const rightAngle =
        calculateAngle(
            rightShoulder,
            rightElbow,
            rightWrist
        );


    if (
        leftAngle === null ||
        rightAngle === null
    ) {

        return null;
    }


    const averageAngle =
        (
            leftAngle +
            rightAngle
        ) / 2;


    const shoulderWidth =
        Math.abs(
            leftShoulder.x -
            rightShoulder.x
        );


    const elbowWidth =
        Math.abs(
            leftElbow.x -
            rightElbow.x
        );


    let feedbacks = [];

    let priority = "good";


    if (shoulderWidth > 5) {

        const flaringRatio =
            elbowWidth /
            shoulderWidth;

        if (
            flaringRatio > 1.55 &&
            averageAngle < 140
        ) {

            feedbacks.push(
                "Keep your elbows closer to your body!"
            );

            priority = "bad";
        }
    }


    // Body-line check
    const shoulderY =
        (
            leftShoulder.y +
            rightShoulder.y
        ) / 2;

    const hipY =
        (
            leftHip.y +
            rightHip.y
        ) / 2;

    const bodyDifference =
        Math.abs(
            hipY -
            shoulderY
        );


    if (
        bodyDifference > 90 &&
        averageAngle < 145
    ) {

        feedbacks.push(
            "Keep your core tight and body straight!"
        );

        priority = "bad";
    }


    if (
        averageAngle < 95 &&
        averageAngle > 55
    ) {

        feedbacks.push(
            "Good depth!"
        );

        if (priority !== "bad")
            priority = "good";
    }


    if (
        feedbacks.length === 0 &&
        averageAngle > 150
    ) {

        feedbacks.push(
            "Great! Keep going!"
        );

        priority = "good";
    }


    return {

        messages: feedbacks,

        priority: priority,

        elbowAngle: averageAngle,

        depth:
            averageAngle <=
            AI_CONFIG.downAngle

    };
}


// ============================================================
// FORM FEEDBACK
// ============================================================

function showFormFeedback(feedback) {

    const element =
        document.getElementById(
            "formFeedback"
        );

    if (
        !feedback ||
        !feedback.messages ||
        feedback.messages.length === 0
    ) {

        element.style.display =
            "none";

        return;
    }

    element.textContent =
        feedback.messages[0];

    element.className =
        "form-feedback " +
        feedback.priority;

    element.style.display =
        "block";
}


// ============================================================
// RESET AI COUNTER
// ============================================================

function resetAICounter() {

    repCount = 0;

    angleBuffer = [];

    lastRepTime = 0;

    bottomFrames = 0;

    upStableFrames = 0;

    downStableFrames = 0;

    lastStableAngle = null;

    validArm = null;

    /*
        Starting state is UP.
        User must first go DOWN.
    */

    aiState = "UP";
}


// ============================================================
// REGISTER REP
// ============================================================

function registerRep(now) {

    if (
        now - lastRepTime <
        AI_CONFIG.repCooldown
    ) {
        return false;
    }

    repCount++;

    lastRepTime = now;

    document
        .getElementById("repCounter")
        .textContent =
        repCount;


    // Ghost timestamp
    if (battleStartTime > 0) {

        ghostTimestamps.push(
            (now - battleStartTime) /
            1000
        );
    }


    // Ghost race
    if (
        ghostData &&
        ghostData.timestamps
    ) {

        const elapsed =
            (
                now -
                battleStartTime
            ) / 1000;

        let ghostReps = 0;

        for (
            const timestamp
            of ghostData.timestamps
        ) {

            if (
                timestamp <=
                elapsed
            ) {

                ghostReps++;
            }
        }

        document
            .getElementById(
                "ghostCount"
            )
            .textContent =
            ghostReps;


        if (
            repCount >
            ghostReps
        ) {

            document
                .getElementById(
                    "ghostCount"
                )
                .classList
                .add("ghost-beaten");

        } else {

            document
                .getElementById(
                    "ghostCount"
                )
                .classList
                .remove("ghost-beaten");
        }
    }


    // Visual feedback
    const flash =
        document.getElementById(
            "repFlash"
        );

    flash.style.display =
        "block";

    setTimeout(() => {

        flash.style.display =
            "none";

    }, 700);


    return true;
}


// ============================================================
// PUSH-UP STATE MACHINE
// ============================================================
//
// UP
//   |
//   | angle <= 105
//   v
// DOWN
//   |
//   | angle <= 92 for stable frames
//   v
// BOTTOM
//   |
//   | angle >= 155
//   v
// UP + 1 REP
//
// This prevents random arm movements from becoming reps.
//

function updateRepState(angle, now) {

    if (
        angle === null ||
        !Number.isFinite(angle)
    ) {
        return;
    }


    // ========================================================
    // UP STATE
    // ========================================================

    if (aiState === "UP") {

        bottomFrames = 0;

        upStableFrames++;

        if (
            angle <=
            AI_CONFIG.downAngle
        ) {

            downStableFrames++;

        } else {

            downStableFrames = 0;
        }


        if (
            downStableFrames >=
            AI_CONFIG.stableFrames
        ) {

            aiState = "DOWN";

            downStableFrames = 0;

            upStableFrames = 0;

            lastStableAngle =
                angle;

        }

        return;
    }


    // ========================================================
    // DOWN STATE
    // ========================================================

    if (aiState === "DOWN") {

        if (
            angle <=
            AI_CONFIG.bottomAngle
        ) {

            bottomFrames++;

        } else {

            /*
                If the user starts moving upward
                before reaching the bottom, we don't
                count it.
            */

            if (
                angle >
                AI_CONFIG.downAngle
            ) {

                bottomFrames = 0;

                aiState = "UP";

                downStableFrames = 0;

                return;
            }
        }


        if (
            bottomFrames >=
            AI_CONFIG.bottomHoldFrames
        ) {

            aiState = "BOTTOM";

            upStableFrames = 0;

            lastStableAngle =
                angle;
        }

        return;
    }


    // ========================================================
    // BOTTOM STATE
    // ========================================================

    if (aiState === "BOTTOM") {

        if (
            angle >=
            AI_CONFIG.upAngle
        ) {

            upStableFrames++;

        } else {

            upStableFrames = 0;
        }


        if (
            upStableFrames >=
            AI_CONFIG.stableFrames
        ) {

            const movedEnough =
                lastStableAngle === null
                    ? true
                    :
                    (
                        angle -
                        lastStableAngle
                    ) >=
                    AI_CONFIG.minimumMovement;


            if (movedEnough) {

                registerRep(now);
            }


            aiState = "UP";

            bottomFrames = 0;

            upStableFrames = 0;

            downStableFrames = 0;

            lastStableAngle =
                angle;
        }

        return;
    }
}


// ============================================================
// START CHALLENGE
// ============================================================

async function startChallenge(mode) {

    challengeMode =
        mode || "normal";

    ghostTimestamps = [];

    battleStartTime = 0;

    resetAICounter();

    showScreen(
        "challengeScreen"
    );

    document
        .getElementById(
            "countdownDisplay"
        )
        .style.display =
        "block";

    document
        .getElementById(
            "challengeActiveUI"
        )
        .style.display =
        "none";

    document
        .getElementById(
            "motivationBanner"
        )
        .style.display =
        "none";

    document
        .getElementById(
            "motivationBanner"
        )
        .classList
        .remove("fade-out");

    document
        .getElementById(
            "battleResultUI"
        )
        .style.display =
        "none";

    document
        .getElementById(
            "formFeedback"
        )
        .style.display =
        "none";

    if (bannerTimer)
        clearTimeout(
            bannerTimer
        );


    ghostData = null;


    if (
        challengeMode === "ghost" &&
        currentUser
    ) {

        try {

            const response =
                await fetch(
                    "/api/ghost?email=" +
                    encodeURIComponent(
                        currentUser.email
                    )
                );

            const data =
                await response.json();

            ghostData =
                data.ghost;

            document
                .getElementById(
                    "ghostOverlay"
                )
                .style.display =
                "block";

            document
                .getElementById(
                    "ghostCount"
                )
                .textContent =
                "0";

        } catch (error) {

            ghostData = null;
        }

    } else {

        document
            .getElementById(
                "ghostOverlay"
            )
            .style.display =
            "none";
    }


    let count = 3;

    document
        .getElementById(
            "countdownDisplay"
        )
        .textContent =
        count;


    countdownInterval =
        setInterval(() => {

            count--;

            if (count === 0) {

                document
                    .getElementById(
                        "countdownDisplay"
                    )
                    .textContent =
                    "GO!";

                speak("Go!");

                setTimeout(() => {

                    clearInterval(
                        countdownInterval
                    );

                    document
                        .getElementById(
                            "countdownDisplay"
                        )
                        .style.display =
                        "none";

                    startActiveChallenge();

                }, 400);

            } else {

                document
                    .getElementById(
                        "countdownDisplay"
                    )
                    .textContent =
                    count;

                speak(
                    count.toString()
                );
            }

        }, 800);
}


// ============================================================
// START ACTIVE CHALLENGE
// ============================================================

async function startActiveChallenge() {

    timeLeft = 60;

    battleStartTime =
        Date.now();

    resetAICounter();

    document
        .getElementById(
            "challengeActiveUI"
        )
        .style.display =
        "block";

    document
        .getElementById(
            "timerDisplay"
        )
        .textContent =
        timeLeft;

    document
        .getElementById(
            "repCounter"
        )
        .textContent =
        "0";

    document
        .getElementById(
            "aiCameraUI"
        )
        .style.display =
        "block";

    document
        .getElementById(
            "debugMsg"
        )
        .textContent =
        "🤖 Loading AI model...";


    const banner =
        document.getElementById(
            "motivationBanner"
        );

    banner.style.display =
        "block";

    banner.classList.remove(
        "fade-out"
    );


    speak(
        "AI is locking onto your body. Start pushing now. Every clean rep counts!"
    );


    bannerTimer =
        setTimeout(() => {

            banner.classList.add(
                "fade-out"
            );

            setTimeout(() => {

                banner.style.display =
                    "none";

            }, 1000);

        }, 6000);


    // IMPORTANT:
    // Wait for AI model.
    await startAIModel();


    if (!aiReady) {

        document
            .getElementById(
                "debugMsg"
            )
            .textContent =
            "❌ AI could not load.";

        return;
    }


    const cameraStarted =
        await startAICamera();

    if (!cameraStarted) {

        return;
    }


    const cueInterval =
        setInterval(() => {

            if (timeLeft > 55)
                return;

            if (timeLeft === 30) {

                speak(
                    "Halfway there! Keep pushing!"
                );

            } else if (timeLeft === 15) {

                speak(
                    "15 seconds left! Give it everything!"
                );

            } else if (timeLeft === 10) {

                speak(
                    "Final 10 seconds!"
                );

            } else if (
                timeLeft <= 3 &&
                timeLeft > 0
            ) {

                speak(
                    timeLeft.toString()
                );
            }

        }, 1000);


    challengeInterval =
        setInterval(() => {

            timeLeft--;

            document
                .getElementById(
                    "timerDisplay"
                )
                .textContent =
                timeLeft;


            if (timeLeft <= 0) {

                clearInterval(
                    challengeInterval
                );

                clearInterval(
                    cueInterval
                );

                endBattle();
            }

        }, 1000);


    if (currentUser) {

        fetch(
            "/api/stats",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body: JSON.stringify({
                    email:
                        currentUser.email
                })
            }
        );
    }
}


// ============================================================
// LOAD AI MODEL
// ============================================================

async function startAIModel() {

    aiReady = false;

    try {

        if (!window.poseDetection) {

            throw new Error(
                "Pose detection library unavailable"
            );
        }


        /*
            MoveNet SinglePose Lightning is fast enough
            for real-time browser webcam detection.
        */

        const configuration = {

            modelType:
                "SinglePose.Lightning",

            enableSmoothing:
                true
        };


        aiDetector =
            await poseDetection.createDetector(
                poseDetection.SupportedModels.MoveNet,
                configuration
            );


        aiReady = true;


        document
            .getElementById(
                "debugMsg"
            )
            .textContent =
            "✅ AI ready — position your body";

    } catch (error) {

        console.error(
            "AI model error:",
            error
        );

        aiDetector = null;

        aiReady = false;

        document
            .getElementById(
                "debugMsg"
            )
            .textContent =
            "❌ AI model failed. Check internet.";
    }
}


// ============================================================
// CAMERA
// ============================================================

async function startAICamera() {

    const video =
        document.getElementById(
            "webcam"
        );

    const canvas =
        document.getElementById(
            "poseCanvas"
        );

    try {

        aiStream =
            await navigator.mediaDevices.getUserMedia({

                video: {

                    facingMode: "user",

                    width: {
                        ideal: 640
                    },

                    height: {
                        ideal: 480
                    },

                    frameRate: {
                        ideal: 30
                    }
                },

                audio: false
            });


        video.srcObject =
            aiStream;

        await video.play();


        await new Promise(
            resolve => {

                if (
                    video.readyState >= 2
                ) {

                    resolve();

                } else {

                    video.onloadedmetadata =
                        () => resolve();
                }
            }
        );


        canvas.width =
            video.videoWidth ||
            640;

        canvas.height =
            video.videoHeight ||
            480;


        resetAICounter();


        document
            .getElementById(
                "debugMsg"
            )
            .textContent =
            "🟢 AI tracking — get into push-up position";


        requestAnimationFrame(
            detectPose
        );


        return true;


    } catch (error) {

        console.error(
            "Camera error:",
            error
        );

        document
            .getElementById(
                "debugMsg"
            )
            .textContent =
            "❌ Camera access denied!";

        return false;
    }
}


// ============================================================
// STOP CAMERA
// ============================================================

function stopCamera() {

    if (aiStream) {

        aiStream
            .getTracks()
            .forEach(
                track =>
                    track.stop()
            );

        aiStream = null;
    }

    if (aiDetector) {

        try {

            aiDetector.dispose();

        } catch (error) {

        }

        aiDetector = null;
    }

    aiReady = false;
}


// ============================================================
// MAIN AI LOOP
// ============================================================

let detectionBusy = false;


async function detectPose() {

    if (
        timeLeft <= 0 ||
        !aiStream ||
        !aiReady ||
        !aiDetector
    ) {

        return;
    }


    /*
        Prevent multiple MoveNet inference calls
        from stacking up.
    */

    if (detectionBusy) {

        requestAnimationFrame(
            detectPose
        );

        return;
    }


    detectionBusy = true;


    const video =
        document.getElementById(
            "webcam"
        );

    const canvas =
        document.getElementById(
            "poseCanvas"
        );

    const ctx =
        canvas.getContext("2d");

    const angleOverlay =
        document.getElementById(
            "angleOverlay"
        );

    const debugMsg =
        document.getElementById(
            "debugMsg"
        );


    try {

        if (
            video.readyState < 2
        ) {

            detectionBusy = false;

            requestAnimationFrame(
                detectPose
            );

            return;
        }


        const poses =
            await aiDetector.estimatePoses(
                video,
                {
                    flipHorizontal: true
                }
            );


        ctx.clearRect(
            0,
            0,
            canvas.width,
            canvas.height
        );


        if (
            poses &&
            poses.length > 0
        ) {

            const pose =
                poses[0];

            const keypoints =
                pose.keypoints;


            drawSkeleton(
                ctx,
                keypoints
            );


            // =================================================
            // FORM COACH
            // =================================================

            const formFeedback =
                analyzeForm(
                    keypoints
                );

            if (formFeedback) {

                showFormFeedback(
                    formFeedback
                );


                const now =
                    Date.now();


                if (
                    formFeedback.priority ===
                        "bad" &&
                    formFeedback.messages.length > 0 &&
                    now - lastFeedbackTime > 4000
                ) {

                    speak(
                        formFeedback.messages[0]
                    );

                    lastFeedbackTime =
                        now;
                }
            }


            // =================================================
            // GET RELIABLE ELBOW ANGLE
            // =================================================

            const rawAngle =
                getStableAngle(
                    keypoints
                );


            if (
                rawAngle !== null
            ) {

                const smoothAngle =
                    addAngleSample(
                        rawAngle
                    );


                if (
                    smoothAngle !== null
                ) {

                    angleOverlay.textContent =
                        Math.round(
                            smoothAngle
                        ) + "°";

                    angleOverlay.style.display =
                        "block";


                    debugMsg.textContent =
                        "🟢 " +
                        aiState +
                        " • " +
                        Math.round(
                            smoothAngle
                        ) +
                        "°";


                    updateRepState(
                        smoothAngle,
                        Date.now()
                    );
                }


            } else {

                angleOverlay.textContent =
                    "?";

                angleOverlay.style.display =
                    "block";

                debugMsg.textContent =
                    "⚠️ Move into side-view position";
            }


        } else {

            angleOverlay.textContent =
                "?";

            angleOverlay.style.display =
                "block";

            debugMsg.textContent =
                "🔍 Searching for body...";
        }


    } catch (error) {

        console.error(
            "Pose detection error:",
            error
        );

    }


    detectionBusy = false;


    requestAnimationFrame(
        detectPose
    );
}


// ============================================================
// SKELETON
// ============================================================

function drawSkeleton(
    ctx,
    keypoints
) {

    if (
        !window.poseDetection ||
        !keypoints
    ) {
        return;
    }


    const adjacentPairs =
        poseDetection.util.getAdjacentPairs(
            poseDetection.SupportedModels.MoveNet
        );


    ctx.strokeStyle =
        "#0ff";

    ctx.lineWidth = 3;


    for (
        const [p1, p2]
        of adjacentPairs
    ) {

        if (
            isGoodPoint(
                keypoints[p1]
            ) &&
            isGoodPoint(
                keypoints[p2]
            )
        ) {

            ctx.beginPath();

            ctx.moveTo(
                keypoints[p1].x,
                keypoints[p1].y
            );

            ctx.lineTo(
                keypoints[p2].x,
                keypoints[p2].y
            );

            ctx.stroke();
        }
    }


    ctx.fillStyle =
        "#f0f";


    for (
        const point
        of keypoints
    ) {

        if (
            isGoodPoint(point)
        ) {

            ctx.beginPath();

            ctx.arc(
                point.x,
                point.y,
                5,
                0,
                Math.PI * 2
            );

            ctx.fill();
        }
    }
}


// ============================================================
// END BATTLE
// ============================================================

async function endBattle() {

    if (
        challengeInterval
    ) {

        clearInterval(
            challengeInterval
        );

        challengeInterval =
            null;
    }


    if (
        countdownInterval
    ) {

        clearInterval(
            countdownInterval
        );

        countdownInterval =
            null;
    }


    stopCamera();


    if (bannerTimer)
        clearTimeout(
            bannerTimer
        );


    document
        .getElementById(
            "challengeActiveUI"
        )
        .style.display =
        "none";


    document
        .getElementById(
            "motivationBanner"
        )
        .style.display =
        "none";


    document
        .getElementById(
            "ghostOverlay"
        )
        .style.display =
        "none";


    document
        .getElementById(
            "formFeedback"
        )
        .style.display =
        "none";


    document
        .getElementById(
            "battleResultUI"
        )
        .style.display =
        "block";


    document
        .getElementById(
            "finalScore"
        )
        .textContent =
        repCount;


    const trashTalks = [

        "Even my grandma does more! 💀",

        "Weak sauce!",

        "Push-up? More like push-over.",

        "Bro, my cat reps more.",

        "Too ez. Next!"

    ];


    document
        .getElementById(
            "trashTalk"
        )
        .textContent =
        trashTalks[
            Math.floor(
                Math.random() *
                trashTalks.length
            )
        ];


    const champion =
        document.getElementById(
            "championText"
        );

    champion.style.display =
        "block";


    speakChampion();


    if (!currentUser) {

        return;
    }


    const payload = {

        name:
            currentUser.name,

        nationality:
            currentUser.nationality,

        email:
            currentUser.email,

        score:
            repCount,

        ghost_timestamps:
            ghostTimestamps.length > 0
                ? ghostTimestamps
                : null
    };


    try {

        await fetch(
            "/api/battle",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body:
                    JSON.stringify(
                        payload
                    )
            }
        );

    } catch (error) {

        console.error(
            "Battle save error:",
            error
        );
    }


    if (
        ghostData &&
        repCount >
        ghostData.score
    ) {

        document
            .getElementById(
                "trashTalk"
            )
            .textContent =
            "👻 GHOST DEFEATED! You're stronger than your past self!";

        speak(
            "You defeated your ghost! New personal best recorded."
        );
    }


    setTimeout(() => {

        champion.style.display =
            "none";

    }, 5000);


    const stats =
        JSON.parse(
            localStorage.getItem(
                "pushclash_stats"
            ) || "{}"
        );


    const personalBest =
        stats.personalBest || 0;


    let analysis =
        `You scored ${repCount}. `;


    if (
        repCount >=
        personalBest
    ) {

        analysis +=
            "That's a new personal best! You're on fire!";

    } else {

        analysis +=
            `Your PB is ${personalBest}. You're getting closer!`;
    }


    speak(
        analysis
    );

    setAIMessage(
        "💬 " + analysis
    );
}


// ============================================================
// SHARE
// ============================================================

function shareScore() {

    const text =
        `I just did ${repCount} push-ups in PushClash! Can you beat me? 🔥 ${BASE}`;


    if (
        navigator.clipboard
    ) {

        navigator.clipboard
            .writeText(text)
            .then(() => {

                alert(
                    "Link copied!"
                );

            })
            .catch(() => {

                alert(text);

            });

    } else {

        alert(text);
    }
}


// ============================================================
// LEADERBOARD
// ============================================================

async function showLeaderboard() {

    showScreen(
        "leaderboardScreen"
    );


    try {

        const response =
            await fetch(
                "/api/leaderboard"
            );

        const data =
            await response.json();

        const container =
            document.getElementById(
                "leaderboardList"
            );


        if (!data.length) {

            container.innerHTML =
                '<p style="text-align:center;color:#aaa">No battles yet.</p>';

            return;
        }


        container.innerHTML =
            data
                .map(
                    (battle, index) => {

                        const emojis = [
                            "🥇",
                            "🥈",
                            "🥉"
                        ];

                        const rank =
                            index < 3
                                ? emojis[index]
                                : `#${index + 1}`;

                        const date =
                            battle.date
                                ? `
                                    <span class="score-date">
                                        ${battle.date}
                                    </span>
                                  `
                                : "";


                        return `
                            <div class="leaderboard-item">

                                <span class="rank">
                                    ${rank}
                                </span>

                                <span>
                                    ${battle.name}
                                </span>

                                <span class="small">
                                    ${battle.nationality}
                                </span>

                                <span class="score">
                                    ${battle.score}
                                    ${date}
                                </span>

                            </div>
                        `;
                    }
                )
                .join("");


    } catch (error) {

        document
            .getElementById(
                "leaderboardList"
            )
            .innerHTML =
            '<p style="text-align:center;color:#aaa">Unable to load leaderboard.</p>';
    }
}


</script>

</body>
</html>
"""


# ============================================================
# MAIN PAGE
# ============================================================

@app.route("/")
def index():
    return FRONTEND_HTML


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    with app.app_context():
        init_db()

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=False
    )
