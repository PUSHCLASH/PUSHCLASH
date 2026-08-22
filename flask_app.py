from flask import Flask, request, jsonify, render_template_string
from pathlib import Path
import json
import random
import os
from datetime import datetime

app = Flask(__name__)

APP_NAME = "PUSHCLASH"
DATA_FILE = Path("pushclash_user.json")

WORLD_RECORD = {
    "exercise": "Standard Push-Ups",
    "reps": 119,
    "holder": "Jarrad Young",
    "country": "Australia",
    "date": "June 28, 2021"
}

QUOTES = [
    "Small progress is still progress.",
    "Train with control. Progress with patience.",
    "Your only competition is yesterday's version of you.",
    "Consistency creates results.",
    "Build the habit before chasing the numbers.",
    "Strong body. Strong discipline.",
    "One workout at a time."
]

EXERCISES = [
    {
        "name": "Standard Push-Up",
        "icon": "💪",
        "category": "Upper Body",
        "description": "Classic upper-body pushing movement.",
        "steps": "Keep your body controlled and move through a comfortable range.",
        "recommendation": "Prioritize technique over speed.",
        "precautions": "Stop if you experience sharp pain."
    },
    {
        "name": "Bodyweight Squat",
        "icon": "🦵",
        "category": "Strength",
        "description": "Lower-body movement.",
        "steps": "Keep your feet stable and lower your body with control.",
        "recommendation": "Start with controlled repetitions.",
        "precautions": "Do not force uncomfortable depth."
    },
    {
        "name": "Plank",
        "icon": "🔥",
        "category": "Core",
        "description": "Core stability exercise.",
        "steps": "Maintain a comfortable stable position and breathe normally.",
        "recommendation": "Start with short holds.",
        "precautions": "Stop if you experience pain."
    },
    {
        "name": "Jumping Jack",
        "icon": "⚡",
        "category": "Cardio",
        "description": "Simple full-body cardio movement.",
        "steps": "Move your arms and legs rhythmically.",
        "recommendation": "Start slowly.",
        "precautions": "Use a suitable surface."
    },
    {
        "name": "Glute Bridge",
        "icon": "🍑",
        "category": "Lower Body",
        "description": "Hip and posterior-chain exercise.",
        "steps": "Lift your hips gradually and lower them with control.",
        "recommendation": "Focus on controlled movement.",
        "precautions": "Avoid uncomfortable back movement."
    },
    {
        "name": "Bird Dog",
        "icon": "🐦",
        "category": "Core",
        "description": "Balance and core-control exercise.",
        "steps": "Extend opposite arm and leg while keeping your torso stable.",
        "recommendation": "Move slowly.",
        "precautions": "Avoid twisting."
    }
]

SAFETY = [
    "Warm up gradually.",
    "Use a safe training area.",
    "Use controlled technique.",
    "Take rest when needed.",
    "Stop if you feel sharp pain, dizziness or unusual symptoms.",
    "Do not compare your body or performance unfairly with others."
]


def default_user():
    return {
        "username": "",
        "email": "",
        "age": 0,
        "xp": 0,
        "level": 1,
        "streak": 0,
        "workouts": 0,
        "total_reps": 0,
        "best_reps": 0,
        "sessions": [],
        "created_at": datetime.now().isoformat()
    }


def load_user():
    try:
        if DATA_FILE.exists():
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            user = default_user()
            user.update(data)
            return user
    except Exception:
        pass

    return default_user()


def save_user(user):
    try:
        DATA_FILE.write_text(
            json.dumps(user, indent=2),
            encoding="utf-8"
        )
    except OSError:
        pass


def calculate_level(user):
    level = 1
    xp = int(user.get("xp", 0))

    while xp >= level * 100:
        xp -= level * 100
        level += 1

    return level, xp


def add_workout(user, reps):
    reps = max(0, int(reps))

    user["workouts"] += 1
    user["total_reps"] += reps

    if reps > user["best_reps"]:
        user["best_reps"] = reps

    user["xp"] += 50 + min(reps, 100)

    user["streak"] += 1

    session = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "reps": reps
    }

    user["sessions"].append(session)

    user["sessions"] = user["sessions"][-30:]

    user["level"], user["xp"] = calculate_level(user)

    save_user(user)

    return user


HTML = r"""
<!DOCTYPE html>
<html lang="en">

<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>PUSHCLASH</title>

<style>

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    background:
        radial-gradient(circle at top right, #17203d, transparent 35%),
        radial-gradient(circle at bottom left, #11182e, transparent 35%),
        #070812;

    color: white;
    font-family: Arial, sans-serif;
    min-height: 100vh;
}

button {
    border: none;
    cursor: pointer;
}

.app {
    display: flex;
    min-height: 100vh;
}

.sidebar {
    width: 220px;
    background: #090b17;
    border-right: 1px solid #1d2340;
    padding: 22px 12px;
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
}

.logo {
    color: #00eaff;
    font-size: 25px;
    font-weight: 900;
    padding: 10px 14px 25px;
}

.nav button {
    width: 100%;
    text-align: left;
    background: transparent;
    color: #aeb5d2;
    padding: 14px;
    border-radius: 10px;
    margin-bottom: 6px;
    font-weight: bold;
}

.nav button:hover,
.nav button.active {
    background: #101a2c;
    color: #00eaff;
}

.main {
    margin-left: 220px;
    width: calc(100% - 220px);
}

.header {
    height: 70px;
    border-bottom: 1px solid #1d2340;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding: 0 30px;
    gap: 15px;
}

.avatar {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    background: #8b5cf6;
    display: flex;
    justify-content: center;
    align-items: center;
    font-weight: bold;
}

.content {
    padding: 30px;
    max-width: 1400px;
}

.hero,
.card {
    background: #101323;
    border: 1px solid #252a44;
    border-radius: 14px;
}

.hero {
    padding: 30px;
    margin-bottom: 22px;
}

.hero h1 {
    font-size: 32px;
    margin-bottom: 8px;
}

.hero p {
    color: #9da5c5;
}

.stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 22px;
}

.card {
    padding: 20px;
}

.stat-title {
    color: #9da5c5;
    font-size: 12px;
}

.stat-value {
    color: #00eaff;
    font-size: 27px;
    font-weight: bold;
    margin-top: 6px;
}

.grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
}

.exercise-icon {
    font-size: 38px;
    margin-bottom: 12px;
}

.exercise-name {
    font-size: 18px;
    font-weight: bold;
}

.muted {
    color: #9da5c5;
}

.primary {
    background: #00eaff;
    color: #03040a;
}

.secondary {
    background: #171b2c;
    color: white;
}

.action {
    padding: 12px 18px;
    border-radius: 9px;
    font-weight: bold;
    margin-top: 14px;
}

.record {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
}

.record-number {
    font-size: 60px;
    color: #00eaff;
    font-weight: 900;
}

.progress-container {
    height: 12px;
    background: #070812;
    border-radius: 10px;
    overflow: hidden;
    margin: 12px 0;
}

.progress-bar {
    height: 100%;
    width: 0%;
    background: #00eaff;
    transition: width .4s;
}

input,
select {
    width: 100%;
    background: #090c18;
    border: 1px solid #292e49;
    color: white;
    padding: 13px;
    border-radius: 8px;
    margin-top: 7px;
}

.login {
    width: 450px;
    max-width: 90%;
    margin: 100px auto;
}

.login .card {
    padding: 35px;
}

.login h1 {
    color: #00eaff;
    font-size: 40px;
    text-align: center;
}

label {
    display: block;
    margin-top: 15px;
    color: #cbd1ef;
}

.big-timer {
    font-size: 70px;
    color: #00eaff;
    font-weight: 900;
    text-align: center;
    padding: 25px;
}

.hidden {
    display: none;
}

.close {
    color: #9da5c5;
}

@media(max-width: 900px) {

    .sidebar {
        width: 70px;
    }

    .logo {
        font-size: 0;
    }

    .logo:first-letter {
        font-size: 24px;
    }

    .nav button {
        font-size: 0;
        text-align: center;
    }

    .nav button:first-letter {
        font-size: 20px;
    }

    .main {
        margin-left: 70px;
        width: calc(100% - 70px);
    }

    .stats,
    .grid,
    .record {
        grid-template-columns: 1fr;
    }

}

</style>
</head>

<body>

<div id="loginScreen" class="login">

    <div class="card">

        <h1>PUSHCLASH</h1>

        <p class="muted" style="text-align:center;margin:10px 0 25px;">
            Train. Compete. Level Up.
        </p>

        <label>Username</label>
        <input id="username" placeholder="Enter username">

        <label>Email</label>
        <input id="email" placeholder="Enter email">

        <label>Age</label>
        <input id="age" type="number" min="14" max="100">

        <button class="action primary"
                style="width:100%;"
                onclick="login()">
            ENTER PUSHCLASH →
        </button>

    </div>

</div>


<div id="appScreen" class="app hidden">

    <aside class="sidebar">

        <div class="logo">
            PUSHCLASH
        </div>

        <div class="nav">

            <button onclick="showPage('dashboard')" id="nav-dashboard">
                🏠 Dashboard
            </button>

            <button onclick="showPage('workout')" id="nav-workout">
                ⚔️ Training Arena
            </button>

            <button onclick="showPage('record')" id="nav-record">
                🏆 World Record
            </button>

            <button onclick="showPage('exercises')" id="nav-exercises">
                💪 Exercises
            </button>

            <button onclick="showPage('progress')" id="nav-progress">
                📈 Progress
            </button>

            <button onclick="showPage('safety')" id="nav-safety">
                🛡️ Safety
            </button>

        </div>

    </aside>


    <main class="main">

        <header class="header">

            <span id="headerName"></span>

            <div class="avatar" id="avatar">
                P
            </div>

            <button class="action secondary"
                    onclick="logout()">
                Logout
            </button>

        </header>


        <section class="content">

            <div id="page"></div>

        </section>

    </main>

</div>


<script>

let user = null;

let timer = 30;
let timerRunning = false;
let timerInterval = null;

function api(url, options = {}) {

    return fetch(url, {
        headers: {
            "Content-Type": "application/json"
        },
        ...options
    }).then(response => response.json());

}


function login() {

    const username =
        document.getElementById("username").value.trim();

    const email =
        document.getElementById("email").value.trim();

    const age =
        document.getElementById("age").value;

    if (!username || !email || !age) {
        alert("Please complete all fields.");
        return;
    }

    if (!email.includes("@")) {
        alert("Enter a valid email.");
        return;
    }

    api("/api/login", {
        method: "POST",
        body: JSON.stringify({
            username,
            email,
            age
        })
    }).then(data => {

        if (!data.success) {
            alert(data.message);
            return;
        }

        user = data.user;

        localStorage.setItem(
            "pushclash_logged_in",
            "true"
        );

        document
            .getElementById("loginScreen")
            .classList.add("hidden");

        document
            .getElementById("appScreen")
            .classList.remove("hidden");

        updateHeader();

        showPage("dashboard");

    });

}


function updateHeader() {

    document.getElementById("headerName").innerText =
        `${user.username} • Lv. ${user.level}`;

    document.getElementById("avatar").innerText =
        user.username.charAt(0).toUpperCase();

}


function showPage(page) {

    document
        .querySelectorAll(".nav button")
        .forEach(button => button.classList.remove("active"));

    const nav =
        document.getElementById("nav-" + page);

    if (nav) {
        nav.classList.add("active");
    }

    if (page === "dashboard") dashboard();
    if (page === "workout") workout();
    if (page === "record") recordPage();
    if (page === "exercises") exercises();
    if (page === "progress") progress();
    if (page === "safety") safety();

}


function dashboard() {

    const page = document.getElementById("page");

    page.innerHTML = `

        <div class="hero">

            <h1>
                Welcome back, ${user.username}
            </h1>

            <p>
                Your mission today:
                move safely, build consistency,
                and level up.
            </p>

        </div>


        <div class="stats">

            <div class="card">
                <div class="stat-title">LEVEL</div>
                <div class="stat-value">${user.level}</div>
            </div>

            <div class="card">
                <div class="stat-title">XP</div>
                <div class="stat-value">${user.xp}</div>
            </div>

            <div class="card">
                <div class="stat-title">STREAK</div>
                <div class="stat-value">${user.streak} 🔥</div>
            </div>

            <div class="card">
                <div class="stat-title">TOTAL REPS</div>
                <div class="stat-value">${user.total_reps}</div>
            </div>

        </div>


        <div class="card">

            <h2>⚡ Today's Mission</h2>

            <p class="muted" style="margin-top:8px;">
                Complete a controlled training session
                and earn XP.
            </p>

            <button
                class="action primary"
                onclick="showPage('workout')">

                START TRAINING →

            </button>

        </div>


        <div class="card" style="margin-top:20px;">

            <h2>🔥 Daily Motivation</h2>

            <p class="muted" style="margin-top:12px;">
                "${QUOTES[Math.floor(Math.random() * QUOTES.length)]}"
            </p>

        </div>

    `;

}


function workout() {

    const page =
        document.getElementById("page");

    page.innerHTML = `

        <div class="hero">

            <h1>⚔️ Training Arena</h1>

            <p>
                Your performance. Your challenge.
                Your progress.
            </p>

        </div>


        <div class="card">

            <h2>One Minute Challenge</h2>

            <p class="muted">
                Record your push-up performance.
            </p>


            <div class="big-timer"
                 id="timer">
                01:00
            </div>


            <div style="text-align:center;">

                <button class="action primary"
                        onclick="startTimer()">
                    ▶ START
                </button>

                <button class="action secondary"
                        onclick="pauseTimer()">
                    ⏸ PAUSE
                </button>

                <button class="action secondary"
                        onclick="resetTimer()">
                    ↻ RESET
                </button>

            </div>


            <div style="margin-top:35px;">

                <label>
                    AI Counted Push-Ups
                </label>

                <input
                    id="repInput"
                    type="number"
                    min="0"
                    placeholder="Enter detected reps">

                <button
                    class="action primary"
                    onclick="completeWorkout()">

                    ✓ SAVE PERFORMANCE

                </button>

            </div>

        </div>

    `;

}


function startTimer() {

    if (timerRunning) return;

    timerRunning = true;

    timerInterval = setInterval(() => {

        timer--;

        updateTimer();

        if (timer <= 0) {

            clearInterval(timerInterval);

            timerRunning = false;

            alert(
                "ONE MINUTE COMPLETE! Record your reps."
            );

        }

    }, 1000);

}


function pauseTimer() {

    timerRunning = false;

    clearInterval(timerInterval);

}


function resetTimer() {

    pauseTimer();

    timer = 60;

    updateTimer();

}


function updateTimer() {

    const minutes =
        Math.floor(timer / 60);

    const seconds =
        timer % 60;

    document.getElementById("timer")
        .innerText =
        String(minutes).padStart(2, "0")
        + ":" +
        String(seconds).padStart(2, "0");

}


function completeWorkout() {

    const reps =
        Number(document.getElementById("repInput").value);

    if (reps < 0 || isNaN(reps)) {

        alert("Enter a valid rep count.");

        return;

    }

    api("/api/workout", {

        method: "POST",

        body: JSON.stringify({
            reps: reps
        })

    }).then(data => {

        if (!data.success) {

            alert(data.message);

            return;

        }

        user = data.user;

        updateHeader();

        alert(
            `MISSION COMPLETE! +${data.xp_added} XP ⚡`
        );

        showPage("dashboard");

    });

}


function recordPage() {

    const difference =
        Math.max(
            0,
            WORLD_RECORD.reps - user.best_reps
        );

    let percentage =
        Math.min(
            100,
            (user.best_reps / WORLD_RECORD.reps) * 100
        );

    document.getElementById("page").innerHTML = `

        <div class="hero">

            <h1>🏆 World Record Arena</h1>

            <p>
                See how close your current best is
                to the official benchmark.
            </p>

        </div>


        <div class="record">

            <div class="card">

                <div class="muted">
                    OFFICIAL STANDARD
                </div>

                <div class="record-number">
                    ${WORLD_RECORD.reps}
                </div>

                <h2>
                    Standard Push-Ups / 1 Minute
                </h2>

                <p class="muted"
                   style="margin-top:10px;">

                    👤 ${WORLD_RECORD.holder}

                    <br>

                    🌎 ${WORLD_RECORD.country}

                    <br>

                    📅 ${WORLD_RECORD.date}

                </p>

            </div>


            <div class="card">

                <div class="muted">
                    YOUR PERSONAL BEST
                </div>

                <div class="record-number">
                    ${user.best_reps}
                </div>

                <h2>
                    Your Record Distance
                </h2>

                <p class="muted"
                   style="margin-top:10px;">

                    ${
                        difference === 0
                        ? "🏆 You matched the benchmark!"
                        : `${difference} reps behind the benchmark`
                    }

                </p>


                <div class="progress-container">

                    <div
                        class="progress-bar"
                        style="width:${percentage}%">
                    </div>

                </div>

                <p class="muted">
                    ${percentage.toFixed(1)}% of benchmark
                </p>

            </div>

        </div>


        <div class="card"
             style="margin-top:20px;">

            <h2>🎯 Your Next Target</h2>

            <p class="muted"
               style="margin-top:8px;">

                ${
                    user.best_reps < WORLD_RECORD.reps
                    ? `Next target: ${Math.min(
                        WORLD_RECORD.reps,
                        user.best_reps + 5
                      )} push-ups`
                    : "Push beyond your current level."
                }

            </p>

        </div>

    `;

}


function exercises() {

    let cards = "";

    ${JSON.stringify(EXERCISES)};

    const exercisesData =
        ${JSON.stringify(EXERCISES)};

    exercisesData.forEach(ex => {

        cards += `

            <div class="card">

                <div class="exercise-icon">
                    ${ex.icon}
                </div>

                <div class="exercise-name">
                    ${ex.name}
                </div>

                <p class="muted"
                   style="margin-top:7px;">
                    ${ex.description}
                </p>

                <p style="color:#00eaff;margin-top:10px;">
                    ${ex.category}
                </p>

                <button
                    class="action secondary"
                    onclick='tutorial(${JSON.stringify(ex)})'>

                    VIEW TUTORIAL

                </button>

            </div>

        `;

    });

    document.getElementById("page").innerHTML = `

        <div class="hero">

            <h1>💪 Exercise Database</h1>

            <p>
                Learn the movement before increasing
                the challenge.
            </p>

        </div>

        <div class="grid">
            ${cards}
        </div>

    `;

}


function tutorial(ex) {

    alert(
        `${ex.icon} ${ex.name}\n\n` +
        `HOW TO PERFORM:\n${ex.steps}\n\n` +
        `RECOMMENDATION:\n${ex.recommendation}\n\n` +
        `PRECAUTION:\n${ex.precautions}`
    );

}


function progress() {

    const nextXP =
        user.level * 100;

    const percentage =
        Math.min(
            100,
            (user.xp / nextXP) * 100
        );

    document.getElementById("page").innerHTML = `

        <div class="hero">

            <h1>📈 Your Progress</h1>

            <p>
                Every session contributes to your
                PUSHCLASH journey.
            </p>

        </div>


        <div class="card">

            <h2>
                Level ${user.level}
            </h2>

            <div class="progress-container">

                <div class="progress-bar"
                     style="width:${percentage}%">
                </div>

            </div>

            <p class="muted">
                ${user.xp} / ${nextXP} XP
            </p>

        </div>


        <div class="stats"
             style="margin-top:20px;">

            <div class="card">
                <div class="stat-title">
                    WORKOUTS
                </div>
                <div class="stat-value">
                    ${user.workouts}
                </div>
            </div>

            <div class="card">
                <div class="stat-title">
                    TOTAL REPS
                </div>
                <div class="stat-value">
                    ${user.total_reps}
                </div>
            </div>

            <div class="card">
                <div class="stat-title">
                    PERSONAL BEST
                </div>
                <div class="stat-value">
                    ${user.best_reps}
                </div>
            </div>

            <div class="card">
                <div class="stat-title">
                    STREAK
                </div>
                <div class="stat-value">
                    ${user.streak} 🔥
                </div>
            </div>

        </div>

    `;

}


function safety() {

    let items = "";

    ${JSON.stringify(SAFETY)};

    const safetyData =
        ${JSON.stringify(SAFETY)};

    safetyData.forEach(item => {

        items += `
            <p class="muted"
               style="margin-top:12px;">
                • ${item}
            </p>
        `;

    });

    document.getElementById("page").innerHTML = `

        <div class="hero">

            <h1>🛡️ Safety Protocol</h1>

            <p>
                Getting stronger starts with training
                intelligently.
            </p>

        </div>


        <div class="card">

            <h2>Safety Rules</h2>

            ${items}

            <p class="muted"
               style="margin-top:25px;">

                PUSHCLASH provides general fitness
                information and is not a substitute
                for individualized medical advice.

            </p>

        </div>

    `;

}


function logout() {

    localStorage.removeItem(
        "pushclash_logged_in"
    );

    location.reload();

}


window.addEventListener("load", () => {

    const logged =
        localStorage.getItem(
            "pushclash_logged_in"
        );

    if (logged === "true") {

        api("/api/user").then(data => {

            if (data.success) {

                user = data.user;

                document
                    .getElementById("loginScreen")
                    .classList.add("hidden");

                document
                    .getElementById("appScreen")
                    .classList.remove("hidden");

                updateHeader();

                showPage("dashboard");

            }

        });

    }

});

</script>

</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(
        HTML,
        WORLD_RECORD=WORLD_RECORD,
        EXERCISES=EXERCISES,
        SAFETY=SAFETY
    )


@app.route("/api/login", methods=["POST"])
def login():

    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip()
    age = data.get("age", 0)

    if not username or not email or not age:
        return jsonify({
            "success": False,
            "message": "Please complete all fields."
        }), 400

    if "@" not in email:
        return jsonify({
            "success": False,
            "message": "Invalid email."
        }), 400

    try:
        age = int(age)
    except ValueError:
        return jsonify({
            "success": False,
            "message": "Invalid age."
        }), 400

    user = load_user()

    user["username"] = username
    user["email"] = email
    user["age"] = age

    save_user(user)

    return jsonify({
        "success": True,
        "user": user
    })


@app.route("/api/user")
def get_user():

    user = load_user()

    if not user.get("username"):
        return jsonify({
            "success": False
        })

    return jsonify({
        "success": True,
        "user": user
    })


@app.route("/api/workout", methods=["POST"])
def workout():

    data = request.get_json(silent=True) or {}

    try:
        reps = int(data.get("reps", 0))
    except (ValueError, TypeError):
        reps = 0

    if reps < 0:
        reps = 0

    user = load_user()

    user = add_workout(user, reps)

    xp_added = 50 + min(reps, 100)

    return jsonify({
        "success": True,
        "user": user,
        "xp_added": xp_added
    })


@app.route("/health")
def health():

    return jsonify({
        "status": "online",
        "app": APP_NAME
    })


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
