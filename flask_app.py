import json
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

APP_NAME = "NEO//FIT"
DATA_FILE = "neoFitUser.json"

# ============================================================
# WORLD / PERFORMANCE BENCHMARK
# ============================================================

WORLD_RECORD = {
    "exercise": "Standard Push-Ups",
    "reps": 119,
    "duration": 60,
    "athlete": "Jarrad Young",
    "country": "Australia",
    "date": "June 28, 2021"
}

# ============================================================
# EXERCISES
# ============================================================

EXERCISES = [
    {
        "name": "Bodyweight Squat", "icon": "🦵", "category": "Strength",
        "description": "A simple lower-body movement.",
        "steps": "Stand with feet around shoulder-width apart. Sit your hips back while bending your knees. Keep your chest comfortable and knees tracking in the same direction as your toes. Return to standing with control.",
        "recommendation": "Start with controlled repetitions and focus on form.",
        "precautions": "Do not force depth. Stop if you experience sharp pain."
    },
    {
        "name": "Wall Push-Up", "icon": "💪", "category": "Upper Body",
        "description": "Beginner-friendly pushing exercise.",
        "steps": "Stand facing a wall. Place your hands on the wall around chest height. Bend your elbows to bring your body toward the wall, then push away.",
        "recommendation": "Use a comfortable number of repetitions while maintaining control.",
        "precautions": "Keep your body stable and avoid painful shoulder movement."
    },
    {
        "name": "Plank", "icon": "🔥", "category": "Core",
        "description": "Build core stability.",
        "steps": "Place your forearms or hands on a stable surface. Keep your body in a comfortable straight line. Brace your core gently and breathe normally.",
        "recommendation": "Begin with short holds rather than chasing long times.",
        "precautions": "Stop if you develop back or shoulder pain."
    },
    {
        "name": "Jumping Jack", "icon": "⚡", "category": "Cardio",
        "description": "Simple full-body cardio movement.",
        "steps": "Stand tall. Jump or step your feet outward while raising your arms. Return to the starting position.",
        "recommendation": "Start slowly and increase pace only when comfortable.",
        "precautions": "Use a suitable surface and choose a lower-impact version if needed."
    },
    {
        "name": "Glute Bridge", "icon": "🍑", "category": "Lower Body",
        "description": "Targets the hips and posterior chain.",
        "steps": "Lie on your back with knees bent and feet planted. Lift your hips gradually, pause briefly, then lower with control.",
        "recommendation": "Focus on controlled movement rather than height.",
        "precautions": "Avoid forcing your lower back into an uncomfortable position."
    },
    {
        "name": "Bird Dog", "icon": "🐦", "category": "Core",
        "description": "Balance and core-control exercise.",
        "steps": "Start on hands and knees. Extend one arm and the opposite leg while keeping your torso stable. Return slowly and switch sides.",
        "recommendation": "Use slow repetitions and prioritize balance.",
        "precautions": "Keep the movement controlled and avoid twisting."
    },
    {
        "name": "March in Place", "icon": "🏃", "category": "Cardio",
        "description": "Low-impact way to get moving.",
        "steps": "Stand tall and alternately lift your feet while moving your arms naturally.",
        "recommendation": "Use this as a warm-up or low-impact cardio option.",
        "precautions": "Use a stable surface and comfortable pace."
    },
    {
        "name": "Mobility Flow", "icon": "🧘", "category": "Mobility",
        "description": "Gentle mobility sequence.",
        "steps": "Move through comfortable ranges of motion for the shoulders, hips, ankles and spine.",
        "recommendation": "Move slowly and never force a stretch.",
        "precautions": "Avoid painful ranges of motion."
    }
]

# ============================================================
# MOTIVATION
# ============================================================

QUOTES = [
    "Small progress is still progress.",
    "Train with control. Progress with patience.",
    "Your only competition is yesterday's version of you.",
    "Consistency creates results.",
    "Build the habit before chasing the numbers.",
    "Strong body. Strong discipline.",
    "One workout at a time."
]

# ============================================================
# SAFETY
# ============================================================

SAFETY = {
    "Before Exercise": [
        "Warm up gradually.",
        "Use a safe, open training area.",
        "Wear suitable footwear.",
        "Learn the movement before adding difficulty.",
        "Stay hydrated."
    ],
    "During Exercise": [
        "Use controlled technique.",
        "Do not compete with other people's weights or repetitions.",
        "Stop if you feel sharp pain, dizziness, faintness, or unusual symptoms.",
        "Take rest when needed."
    ],
    "Ages 14–17": [
        "Prioritize technique and general fitness.",
        "Use age-appropriate resistance.",
        "Consider supervision when learning unfamiliar exercises.",
        "Do not use maximum-effort challenges simply to compete."
    ],
    "Ages 18–24": [
        "Progress gradually.",
        "Keep recovery days in your schedule.",
        "Increase training difficulty only when technique remains solid."
    ]
}

# ============================================================
# ACHIEVEMENTS
# ============================================================

ACHIEVEMENTS = [
    {
        "id": "first_workout",
        "name": "FIRST MISSION",
        "icon": "🚀",
        "description": "Complete your first workout.",
        "check": lambda u: u["workouts"] >= 1
    },
    {
        "id": "five_workouts",
        "name": "CONSISTENCY",
        "icon": "🔥",
        "description": "Complete 5 workouts.",
        "check": lambda u: u["workouts"] >= 5
    },
    {
        "id": "ten_workouts",
        "name": "WARRIOR MODE",
        "icon": "⚔️",
        "description": "Complete 10 workouts.",
        "check": lambda u: u["workouts"] >= 10
    },
    {
        "id": "level_five",
        "name": "LEVEL 5",
        "icon": "⭐",
        "description": "Reach Level 5.",
        "check": lambda u: u["level"] >= 5
    },
    {
        "id": "hundred_reps",
        "name": "CENTURY",
        "icon": "💯",
        "description": "Reach 100 total reps.",
        "check": lambda u: u.get("total_reps", 0) >= 100
    },
    {
        "id": "record_chaser",
        "name": "RECORD CHASER",
        "icon": "🌍",
        "description": "Record 50+ push-ups.",
        "check": lambda u: u.get("best_pushups", 0) >= 50
    },
    {
        "id": "elite",
        "name": "ELITE",
        "icon": "👑",
        "description": "Record 100+ push-ups.",
        "check": lambda u: u.get("best_pushups", 0) >= 100
    },
    {
        "id": "streak_seven",
        "name": "7 DAY WARRIOR",
        "icon": "🔥",
        "description": "Reach a 7 workout streak.",
        "check": lambda u: u["streak"] >= 7
    }
]

# ============================================================
# CHALLENGE POOL
# ============================================================

CHALLENGES = [
    {
        "title": "THE STARTER",
        "description": "Complete one controlled training session.",
        "goal": 1,
        "reward": 75
    },
    {
        "title": "CONSISTENCY RUN",
        "description": "Complete 2 workouts.",
        "goal": 2,
        "reward": 120
    },
    {
        "title": "XP HUNTER",
        "description": "Earn 150 XP.",
        "goal": 150,
        "reward": 150
    },
    {
        "title": "CENTURY PROJECT",
        "description": "Reach 100 total exercise repetitions.",
        "goal": 100,
        "reward": 200
    },
    {
        "title": "RECORD CHASER",
        "description": "Reach 50 push-ups in your personal record.",
        "goal": 50,
        "reward": 250
    }
]


class NeoFit(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1200x760")
        self.minsize(900, 650)
        self.configure(bg="#070812")

        # ----------------------------------------------------
        # USER DATA
        # ----------------------------------------------------

        self.user = {
            "username": "",
            "email": "",
            "age": 0,
            "xp": 0,
            "level": 1,
            "streak": 0,
            "workouts": 0,
            "total_reps": 0,
            "best_pushups": 0,
            "total_score": 0,
            "sessions": [],
            "achievements": [],
            "streak_shield": 1,
            "challenge_progress": 0
        }

        # ----------------------------------------------------
        # TIMER
        # ----------------------------------------------------

        self.timer_seconds = 30
        self.timer_running = False
        self.timer_token = 0
        self.current_exercise = None

        # ----------------------------------------------------
        # STYLE
        # ----------------------------------------------------

        self.style = ttk.Style(self)

        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure(
            "TCombobox",
            fieldbackground="#090c18",
            background="#090c18",
            foreground="white"
        )

        self.style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#090c18",
            background="#00eaff"
        )

        self.show_login()
        self.load_user()

    # ========================================================
    # UI HELPERS
    # ========================================================

    def make_button(self, parent, text, command, primary=False):

        bg = "#00eaff" if primary else "#0b0e1b"
        fg = "#03040a" if primary else "white"

        b = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground="#8b5cf6",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=16,
            pady=10,
            font=("Arial", 10, "bold"),
            cursor="hand2"
        )

        return b

    def clear(self):

        for widget in self.winfo_children():
            widget.destroy()

    def hero(self, title, subtitle):

        f = tk.Frame(
            self.content,
            bg="#101323",
            highlightbackground="#292e4b",
            highlightthickness=1
        )

        f.pack(fill="x", pady=(0, 20))

        tk.Label(
            f,
            text=title,
            bg="#101323",
            fg="white",
            font=("Arial", 30, "bold")
        ).pack(anchor="w", padx=25, pady=(25, 5))

        tk.Label(
            f,
            text=subtitle,
            bg="#101323",
            fg="#9da5c5",
            font=("Arial", 11),
            wraplength=800,
            justify="left"
        ).pack(anchor="w", padx=25, pady=(0, 25))

    def card(self, parent, title=None):

        f = tk.Frame(
            parent,
            bg="#101323",
            highlightbackground="#252a44",
            highlightthickness=1
        )

        if title:

            tk.Label(
                f,
                text=title,
                bg="#101323",
                fg="white",
                font=("Arial", 15, "bold")
            ).pack(
                anchor="w",
                padx=20,
                pady=(18, 5)
            )

        return f

    # ========================================================
    # LOGIN
    # ========================================================

    def show_login(self):

        self.clear()

        box = tk.Frame(
            self,
            bg="#101323",
            highlightbackground="#00eaff",
            highlightthickness=1
        )

        box.place(
            relx=.5,
            rely=.5,
            anchor="center",
            width=450,
            height=520
        )

        tk.Label(
            box,
            text="NEO//FIT",
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 34, "bold")
        ).pack(pady=(35, 5))

        tk.Label(
            box,
            text="Train. Level Up. Become Stronger.",
            bg="#101323",
            fg="#9da5c5",
            font=("Arial", 11)
        ).pack(pady=(0, 25))

        self.username_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.age_var = tk.StringVar()
        self.password_var = tk.StringVar()

        self.field(box, "Username", self.username_var)
        self.field(box, "Email", self.email_var)

        tk.Label(
            box,
            text="Age",
            bg="#101323",
            fg="#cbd1ef",
            anchor="w"
        ).pack(fill="x", padx=35)

        age = ttk.Combobox(
            box,
            textvariable=self.age_var,
            values=[str(i) for i in range(14, 25)],
            state="readonly"
        )

        age.pack(
            fill="x",
            padx=35,
            pady=(5, 15),
            ipady=7
        )

        self.field(
            box,
            "Password",
            self.password_var,
            password=True
        )

        self.make_button(
            box,
            "ENTER NEO//FIT",
            self.login,
            True
        ).pack(
            fill="x",
            padx=35,
            pady=10
        )

        tk.Label(
            box,
            text="Hackathon prototype — local demo authentication.",
            bg="#101323",
            fg="#7f87a8",
            font=("Arial", 8)
        ).pack(pady=10)

    def field(self, parent, label, variable, password=False):

        tk.Label(
            parent,
            text=label,
            bg="#101323",
            fg="#cbd1ef",
            anchor="w"
        ).pack(fill="x", padx=35)

        e = tk.Entry(
            parent,
            textvariable=variable,
            show="*" if password else "",
            bg="#090c18",
            fg="white",
            insertbackground="white",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#292e49"
        )

        e.pack(
            fill="x",
            padx=35,
            pady=(5, 15),
            ipady=9
        )

    def login(self):

        username = self.username_var.get().strip()
        email = self.email_var.get().strip()
        age = self.age_var.get()
        password = self.password_var.get()

        if not username or not email or not age or not password:

            messagebox.showwarning(
                "NEO//FIT",
                "Please complete all fields."
            )

            return

        if "@" not in email:

            messagebox.showwarning(
                "NEO//FIT",
                "Please enter a valid email."
            )

            return

        self.user.update(
            username=username,
            email=email,
            age=int(age)
        )

        self.save_user()
        self.enter_app()

    # ========================================================
    # MAIN APP
    # ========================================================

    def enter_app(self):

        self.build_app()
        self.show_page("dashboard")

    def build_app(self):

        self.clear()

        header = tk.Frame(
            self,
            bg="#070812",
            height=70
        )

        header.pack(fill="x")

        tk.Label(
            header,
            text="NEO//FIT",
            bg="#070812",
            fg="#00eaff",
            font=("Arial", 22, "bold")
        ).pack(side="left", padx=25)

        self.header_name = tk.Label(
            header,
            bg="#070812",
            fg="white",
            font=("Arial", 11, "bold")
        )

        self.header_name.pack(
            side="right",
            padx=(0, 15)
        )

        self.avatar = tk.Label(
            header,
            bg="#8b5cf6",
            fg="#05060b",
            width=3,
            font=("Arial", 12, "bold")
        )

        self.avatar.pack(side="right")

        self.make_button(
            header,
            "Logout",
            self.logout
        ).pack(
            side="right",
            padx=15
        )

        # ----------------------------------------------------
        # NAVIGATION
        # ----------------------------------------------------

        nav = tk.Frame(
            self,
            bg="#090b17",
            width=220
        )

        nav.pack(
            side="left",
            fill="y"
        )

        self.nav_buttons = {}

        navigation = [
            ("dashboard", "🏠 Dashboard"),
            ("exercises", "💪 Exercises"),
            ("workout", "⚔️ Workout"),
            ("progress", "📈 Progress"),
            ("records", "🌍 Record Radar"),
            ("challenges", "🎯 Challenges"),
            ("achievements", "🏆 Achievements"),
            ("coach", "🧠 Smart Coach"),
            ("analytics", "📊 Analytics"),
            ("safety", "🛡️ Safety")
        ]

        for key, text in navigation:

            b = self.make_button(
                nav,
                text,
                lambda k=key: self.show_page(k)
            )

            b.pack(
                fill="x",
                padx=12,
                pady=3
            )

            self.nav_buttons[key] = b

        self.content = tk.Frame(
            self,
            bg="#070812"
        )

        self.content.pack(
            side="left",
            fill="both",
            expand=True,
            padx=30,
            pady=25
        )

        self.update_header()

    def update_header(self):

        if hasattr(self, "header_name"):

            self.header_name.config(
                text=f"{self.user['username']}  •  Lv. {self.user['level']}"
            )

            self.avatar.config(
                text=self.user["username"][:1].upper() or "P"
            )

    def show_page(self, page):

        for w in self.content.winfo_children():
            w.destroy()

        for k, b in self.nav_buttons.items():

            b.config(
                bg="#0b0e1b",
                fg="#aeb5d2"
            )

        if page in self.nav_buttons:

            self.nav_buttons[page].config(
                bg="#101a2c",
                fg="#00eaff"
            )

        pages = {
            "dashboard": self.dashboard,
            "exercises": self.exercises_page,
            "workout": self.workout_page,
            "progress": self.progress_page,
            "records": self.records_page,
            "challenges": self.challenges_page,
            "achievements": self.achievements_page,
            "coach": self.coach_page,
            "analytics": self.analytics_page,
            "safety": self.safety_page
        }

        if page in pages:
            pages[page]()

    # ========================================================
    # DASHBOARD
    # ========================================================

    def dashboard(self):

        self.hero(
            f"Welcome back, {self.user['username']}",
            "Your mission today: move safely, build consistency, and level up."
        )

        stats = tk.Frame(
            self.content,
            bg="#070812"
        )

        stats.pack(fill="x")

        values = [
            ("LEVEL", self.user["level"]),
            ("XP", self.user["xp"]),
            ("STREAK", f"{self.user['streak']} 🔥"),
            ("WORKOUTS", self.user["workouts"]),
            ("BEST PUSH-UPS", self.user.get("best_pushups", 0))
        ]

        for label, value in values:

            c = self.card(stats)

            c.pack(
                side="left",
                fill="both",
                expand=True,
                padx=4
            )

            tk.Label(
                c,
                text=label,
                bg="#101323",
                fg="#9da5c5",
                font=("Arial", 8)
            ).pack(
                anchor="w",
                padx=12,
                pady=(15, 0)
            )

            tk.Label(
                c,
                text=value,
                bg="#101323",
                fg="#00eaff",
                font=("Arial", 19, "bold")
            ).pack(
                anchor="w",
                padx=12,
                pady=(5, 15)
            )

        # ----------------------------------------------------
        # MAIN MISSION
        # ----------------------------------------------------

        mission = self.card(
            self.content,
            "⚡ Today's Mission"
        )

        mission.pack(
            fill="x",
            pady=20
        )

        tk.Label(
            mission,
            text="LEVEL UP YOUR PERFORMANCE",
            bg="#101323",
            fg="white",
            font=("Arial", 17, "bold")
        ).pack(
            anchor="w",
            padx=20,
            pady=8
        )

        tk.Label(
            mission,
            text="Complete a controlled session and improve your personal performance.",
            bg="#101323",
            fg="#9da5c5"
        ).pack(
            anchor="w",
            padx=20
        )

        self.make_button(
            mission,
            "START MISSION →",
            lambda: self.show_page("workout"),
            True
        ).pack(
            anchor="w",
            padx=20,
            pady=15
        )

        # ----------------------------------------------------
        # RECORD PROXIMITY
        # ----------------------------------------------------

        record = self.card(
            self.content,
            "🌍 Record Radar"
        )

        record.pack(
            fill="x",
            pady=(0, 15)
        )

        best = self.user.get("best_pushups", 0)

        if best > 0:

            difference = max(
                WORLD_RECORD["reps"] - best,
                0
            )

            text = (
                f"Your best: {best} reps  •  "
                f"Benchmark: {WORLD_RECORD['reps']} reps  •  "
                f"{difference} reps away"
            )

        else:

            text = (
                f"No push-up record yet  •  "
                f"Benchmark: {WORLD_RECORD['reps']} reps"
            )

        tk.Label(
            record,
            text=text,
            bg="#101323",
            fg="#cbd1ef",
            font=("Arial", 11)
        ).pack(
            anchor="w",
            padx=20,
            pady=15
        )

        self.make_button(
            record,
            "OPEN RECORD RADAR →",
            lambda: self.show_page("records")
        ).pack(
            anchor="w",
            padx=20,
            pady=(0, 15)
        )

        # ----------------------------------------------------
        # MOTIVATION
        # ----------------------------------------------------

        q = self.card(
            self.content,
            "Daily Motivation"
        )

        q.pack(fill="x")

        tk.Label(
            q,
            text=f'"{random.choice(QUOTES)}"',
            bg="#101323",
            fg="#cbd1ef",
            font=("Arial", 11),
            wraplength=800,
            justify="left"
        ).pack(
            anchor="w",
            padx=20,
            pady=20
        )

    # ========================================================
    # EXERCISES
    # ========================================================

    def exercises_page(self):

        self.hero(
            "Exercise Database",
            f"Learn the movement before increasing the challenge. Recommended for age {self.user['age']}."
        )

        grid = tk.Frame(
            self.content,
            bg="#070812"
        )

        grid.pack(
            fill="both",
            expand=True
        )

        for i, ex in enumerate(EXERCISES):

            r, c = divmod(i, 3)

            card = self.card(grid)

            card.grid(
                row=r,
                column=c,
                sticky="nsew",
                padx=7,
                pady=7
            )

            grid.columnconfigure(
                c,
                weight=1
            )

            tk.Label(
                card,
                text=ex["icon"],
                bg="#101323",
                fg="#00eaff",
                font=("Arial", 25)
            ).pack(
                anchor="w",
                padx=18,
                pady=(15, 5)
            )

            tk.Label(
                card,
                text=ex["name"],
                bg="#101323",
                fg="white",
                font=("Arial", 13, "bold")
            ).pack(
                anchor="w",
                padx=18
            )

            tk.Label(
                card,
                text=ex["description"],
                bg="#101323",
                fg="#9da5c5",
                wraplength=250,
                justify="left"
            ).pack(
                anchor="w",
                padx=18,
                pady=7
            )

            tk.Label(
                card,
                text=ex["category"],
                bg="#101323",
                fg="#00eaff"
            ).pack(
                anchor="w",
                padx=18
            )

            self.make_button(
                card,
                "VIEW TUTORIAL",
                lambda idx=i: self.open_exercise(idx)
            ).pack(
                fill="x",
                padx=18,
                pady=15
            )

    def open_exercise(self, index):

        ex = EXERCISES[index]

        win = tk.Toplevel(self)

        win.title(ex["name"])
        win.geometry("650x500")
        win.configure(bg="#0d1020")

        tk.Label(
            win,
            text=ex["icon"] + "  " + ex["name"],
            bg="#0d1020",
            fg="#00eaff",
            font=("Arial", 22, "bold")
        ).pack(
            anchor="w",
            padx=25,
            pady=20
        )

        for title, text in [
            ("How to perform", ex["steps"]),
            ("Recommended starting point", ex["recommendation"]),
            ("Precautions", ex["precautions"])
        ]:

            tk.Label(
                win,
                text=title,
                bg="#0d1020",
                fg="white",
                font=("Arial", 13, "bold")
            ).pack(
                anchor="w",
                padx=25,
                pady=(10, 4)
            )

            tk.Label(
                win,
                text=text,
                bg="#0d1020",
                fg="#b7bed8",
                wraplength=580,
                justify="left"
            ).pack(
                anchor="w",
                padx=25
            )

        self.make_button(
            win,
            "CLOSE",
            win.destroy
        ).pack(pady=20)

    # ========================================================
    # WORKOUT
    # ========================================================

    def workout_page(self):

        self.hero(
            "Training Arena",
            "Complete your session at a controlled pace."
        )

        box = self.card(self.content)

        box.pack(
            fill="both",
            expand=True,
            pady=5
        )

        self.exercise_label = tk.Label(
            box,
            text="Ready?",
            bg="#101323",
            fg="white",
            font=("Arial", 22, "bold")
        )

        self.exercise_label.pack(
            pady=(55, 10)
        )

        self.timer_label = tk.Label(
            box,
            text=self.format_time(),
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 65, "bold")
        )

        self.timer_label.pack(
            pady=15
        )

        row = tk.Frame(
            box,
            bg="#101323"
        )

        row.pack()

        for text, cmd in [
            ("▶️ START", self.start_timer),
            ("⏸ PAUSE", self.pause_timer),
            ("↻ RESET", self.reset_timer),
            ("✓ COMPLETE", self.complete_workout)
        ]:

            self.make_button(
                row,
                text,
                cmd
            ).pack(
                side="left",
                padx=5
            )

        tk.Label(
            box,
            text="Select an exercise:",
            bg="#101323",
            fg="#9da5c5"
        ).pack(
            pady=(35, 5)
        )

        names = [
            e["name"]
            for e in EXERCISES
        ]

        self.exercise_choice = ttk.Combobox(
            box,
            values=names,
            state="readonly"
        )

        self.exercise_choice.pack()

        self.exercise_choice.bind(
            "<<ComboboxSelected>>",
            self.select_exercise
        )

        # ----------------------------------------------------
        # PERFORMANCE INPUT
        # ----------------------------------------------------

        tk.Label(
            box,
            text="Push-ups completed (optional):",
            bg="#101323",
            fg="#9da5c5"
        ).pack(
            pady=(20, 5)
        )

        self.pushup_var = tk.StringVar()

        tk.Entry(
            box,
            textvariable=self.pushup_var,
            bg="#090c18",
            fg="white",
            insertbackground="white",
            relief="flat",
            width=15,
            justify="center"
        ).pack(
            ipady=7
        )

    def select_exercise(self, event=None):

        name = self.exercise_choice.get()

        self.current_exercise = next(
            (
                e for e in EXERCISES
                if e["name"] == name
            ),
            None
        )

        if self.current_exercise:

            self.exercise_label.config(
                text=self.current_exercise["icon"] +
                " " +
                name
            )

    def format_time(self):

        return (
            f"{self.timer_seconds // 60:02d}:"
            f"{self.timer_seconds % 60:02d}"
        )

    def start_timer(self):

        if self.timer_running:
            return

        self.timer_running = True

        self.timer_token += 1

        token = self.timer_token

        def tick():

            if not self.timer_running or token != self.timer_token:
                return

            if self.timer_seconds > 0:

                self.timer_seconds -= 1

                if (
                    hasattr(self, "timer_label")
                    and self.timer_label.winfo_exists()
                ):

                    self.timer_label.config(
                        text=self.format_time()
                    )

                self.after(
                    1000,
                    tick
                )

            else:

                self.timer_running = False

                messagebox.showinfo(
                    "NEO//FIT",
                    "Round complete! Take a moment to recover."
                )

        tick()

    def pause_timer(self):

        self.timer_running = False
        self.timer_token += 1

    def reset_timer(self):

        self.pause_timer()

        self.timer_seconds = 30

        if (
            hasattr(self, "timer_label")
            and self.timer_label.winfo_exists()
        ):

            self.timer_label.config(
                text=self.format_time()
            )

    # ========================================================
    # WORKOUT COMPLETION + SCORING
    # ========================================================

    def complete_workout(self):

        reps = 0

        try:
            reps = int(
                self.pushup_var.get().strip()
                or 0
            )

            if reps < 0:
                reps = 0

        except ValueError:

            messagebox.showwarning(
                "Invalid input",
                "Please enter a valid number of push-ups."
            )

            return

        self.user["workouts"] += 1

        self.user["total_reps"] += reps

        if reps > self.user.get("best_pushups", 0):

            self.user["best_pushups"] = reps

        # ----------------------------------------------------
        # MISSION SCORE
        # ----------------------------------------------------

        score = self.calculate_score(reps)

        self.user["total_score"] += score

        xp_gain = 50 + score // 10

        self.user["xp"] += xp_gain

        self.user["streak"] += 1

        # ----------------------------------------------------
        # SESSION RECORD
        # ----------------------------------------------------

        session = {
            "reps": reps,
            "score": score,
            "xp": xp_gain,
            "exercise": (
                self.current_exercise["name"]
                if self.current_exercise
                else "General Workout"
            ),
            "timestamp": time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        }

        self.user.setdefault(
            "sessions",
            []
        ).append(session)

        # Keep history manageable
        self.user["sessions"] = self.user["sessions"][-50:]

        # ----------------------------------------------------
        # CHALLENGE
        # ----------------------------------------------------

        self.user["challenge_progress"] += 1

        # ----------------------------------------------------
        # LEVEL
        # ----------------------------------------------------

        self.check_level()

        # ----------------------------------------------------
        # ACHIEVEMENTS
        # ----------------------------------------------------

        new_achievements = self.check_achievements()

        self.save_user()
        self.update_header()

        message = (
            f"MISSION COMPLETE!\n\n"
            f"Performance Score: {score}/100\n"
            f"+{xp_gain} XP\n"
            f"Push-ups recorded: {reps}\n"
        )

        if new_achievements:

            message += (
                "\n🏆 ACHIEVEMENT UNLOCKED:\n"
                + "\n".join(
                    "• " + a
                    for a in new_achievements
                )
            )

        messagebox.showinfo(
            "MISSION COMPLETE",
            message
        )

        self.reset_timer()

    def calculate_score(self, reps):

        score = 40

        if reps >= 10:
            score += 10

        if reps >= 25:
            score += 10

        if reps >= 50:
            score += 15

        if reps >= 75:
            score += 15

        if reps >= WORLD_RECORD["reps"]:
            score = 100

        return min(score, 100)

    def check_level(self):

        required = self.user["level"] * 100

        while self.user["xp"] >= required:

            self.user["xp"] -= required

            self.user["level"] += 1

            messagebox.showinfo(
                "LEVEL UP!",
                f"You reached Level {self.user['level']}!"
            )

            required = self.user["level"] * 100

    # ========================================================
    # PROGRESS
    # ========================================================

    def progress_page(self):

        self.hero(
            "Your Progress",
            "Turn every workout into measurable progress."
        )

        c = self.card(
            self.content,
            "Level Progress"
        )

        c.pack(
            fill="x",
            pady=10
        )

        level = self.user["level"]
        xp = self.user["xp"]

        next_xp = level * 100

        pct = min(
            xp / next_xp,
            1
        )

        tk.Label(
            c,
            text=f"Level {level}",
            bg="#101323",
            fg="white",
            font=("Arial", 16, "bold")
        ).pack(
            anchor="w",
            padx=20,
            pady=(20, 10)
        )

        bar = ttk.Progressbar(
            c,
            maximum=100,
            value=pct * 100
        )

        bar.pack(
            fill="x",
            padx=20,
            pady=5
        )

        tk.Label(
            c,
            text=f"{xp} / {next_xp} XP",
            bg="#101323",
            fg="#b7bed8"
        ).pack(
            anchor="w",
            padx=20,
            pady=(5, 20)
        )

        # ----------------------------------------------------
        # PERFORMANCE
        # ----------------------------------------------------

        p = self.card(
            self.content,
            "Performance Snapshot"
        )

        p.pack(
            fill="x",
            pady=10
        )

        stats = [
            ("Total Reps", self.user.get("total_reps", 0)),
            ("Best Push-Ups", self.user.get("best_pushups", 0)),
            ("Total Score", self.user.get("total_score", 0)),
            ("Streak", self.user["streak"])
        ]

        for label, value in stats:

            tk.Label(
                p,
                text=f"{label}: {value}",
                bg="#101323",
                fg="#cbd1ef",
                font=("Arial", 11, "bold")
            ).pack(
                anchor="w",
                padx=20,
                pady=5
            )

        tk.Label(
            p,
            text="Your goal is not simply to exercise more — it is to build consistent measurable progress.",
            bg="#101323",
            fg="#9da5c5",
            wraplength=800,
            justify="left"
        ).pack(
            anchor="w",
            padx=20,
            pady=15
        )

    # ========================================================
    # RECORD RADAR
    # ========================================================

    def records_page(self):

        self.hero(
            "🌍 Record Radar",
            "Turn the world's benchmark into your personal performance target."
        )

        record = self.card(
            self.content,
            "WORLD BENCHMARK"
        )

        record.pack(
            fill="x",
            pady=10
        )

        tk.Label(
            record,
            text=f"{WORLD_RECORD['reps']} PUSH-UPS",
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 34, "bold")
        ).pack(
            pady=(25, 5)
        )

        tk.Label(
            record,
            text=f"in {WORLD_RECORD['duration']} seconds",
            bg="#101323",
            fg="white",
            font=("Arial", 13)
        ).pack()

        tk.Label(
            record,
            text=(
                f"{WORLD_RECORD['athlete']} • "
                f"{WORLD_RECORD['country']}\n"
                f"{WORLD_RECORD['date']}"
            ),
            bg="#101323",
            fg="#9da5c5",
            justify="center"
        ).pack(
            pady=15
        )

        best = self.user.get(
            "best_pushups",
            0
        )

        difference = max(
            WORLD_RECORD["reps"] - best,
            0
        )

        proximity = min(
            best / WORLD_RECORD["reps"] * 100,
            100
        )

        personal = self.card(
            self.content,
            "⚡ YOUR PROXIMITY"
        )

        personal.pack(
            fill="x",
            pady=10
        )

        tk.Label(
            personal,
            text=f"Personal Best: {best} reps",
            bg="#101323",
            fg="white",
            font=("Arial", 18, "bold")
        ).pack(
            anchor="w",
            padx=20,
            pady=(20, 5)
        )

        tk.Label(
            personal,
            text=(
                f"{difference} reps away from the "
                f"{WORLD_RECORD['reps']}-rep benchmark"
            ),
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 12)
        ).pack(
            anchor="w",
            padx=20,
            pady=5
        )

        bar = ttk.Progressbar(
            personal,
            maximum=100,
            value=proximity
        )

        bar.pack(
            fill="x",
            padx=20,
            pady=10
        )

        tk.Label(
            personal,
            text=f"{proximity:.1f}% of benchmark",
            bg="#101323",
            fg="#9da5c5"
        ).pack(
            anchor="w",
            padx=20,
            pady=(0, 20)
        )

        tk.Label(
            self.content,
            text=(
                "Benchmark information is presented for comparison and "
                "motivation. Do not attempt maximum-effort performance "
                "without appropriate preparation."
            ),
            bg="#070812",
            fg="#7f87a8",
            wraplength=800,
            justify="left"
        ).pack(
            anchor="w",
            pady=15
        )

    # ========================================================
    # CHALLENGES
    # ========================================================

    def challenges_page(self):

        self.hero(
            "🎯 Challenge Arena",
            "Your fitness journey becomes a game with measurable objectives."
        )

        challenge = random.choice(CHALLENGES)

        c = self.card(
            self.content,
            "ACTIVE CHALLENGE"
        )

        c.pack(
            fill="x",
            pady=10
        )

        tk.Label(
            c,
            text=challenge["title"],
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 25, "bold")
        ).pack(
            anchor="w",
            padx=20,
            pady=(25, 8)
        )

        tk.Label(
            c,
            text=challenge["description"],
            bg="#101323",
            fg="#cbd1ef",
            font=("Arial", 12)
        ).pack(
            anchor="w",
            padx=20
        )

        tk.Label(
            c,
            text=f"REWARD  +{challenge['reward']} XP",
            bg="#101323",
            fg="#8b5cf6",
            font=("Arial", 12, "bold")
        ).pack(
            anchor="w",
            padx=20,
            pady=15
        )

        self.make_button(
            c,
            "ENTER CHALLENGE →",
            lambda: self.show_page("workout"),
            True
        ).pack(
            anchor="w",
            padx=20,
            pady=(0, 20)
        )

        # ----------------------------------------------------
        # CHALLENGE PHILOSOPHY
        # ----------------------------------------------------

        info = self.card(
            self.content,
            "Why Challenge Mode?"
        )

        info.pack(
            fill="x",
            pady=15
        )

        tk.Label(
            info,
            text=(
                "Instead of simply telling users to 'work out', "
                "NEO//FIT gives them measurable missions, rewards, "
                "benchmarks and progression."
            ),
            bg="#101323",
            fg="#b7bed8",
            wraplength=800,
            justify="left"
        ).pack(
            anchor="w",
            padx=20,
            pady=20
        )

    # ========================================================
    # ACHIEVEMENTS
    # ========================================================

    def check_achievements(self):

        unlocked = []

        current = self.user.setdefault(
            "achievements",
            []
        )

        for achievement in ACHIEVEMENTS:

            if achievement["id"] in current:
                continue

            try:
                earned = achievement["check"](
                    self.user
                )
            except Exception:
                earned = False

            if earned:

                current.append(
                    achievement["id"]
                )

                unlocked.append(
                    f"{achievement['icon']} {achievement['name']}"
                )

        return unlocked

    def achievements_page(self):

        self.hero(
            "🏆 Achievement System",
            "Every milestone becomes proof of progress."
        )

        grid = tk.Frame(
            self.content,
            bg="#070812"
        )

        grid.pack(
            fill="both",
            expand=True
        )

        unlocked = self.user.get(
            "achievements",
            []
        )

        for i, achievement in enumerate(ACHIEVEMENTS):

            r, c = divmod(i, 2)

            card = self.card(grid)

            card.grid(
                row=r,
                column=c,
                sticky="nsew",
                padx=7,
                pady=7
            )

            grid.columnconfigure(
                c,
                weight=1
            )

            is_unlocked = (
                achievement["id"]
                in unlocked
            )

            status = (
                "UNLOCKED ✓"
                if is_unlocked
                else "LOCKED"
            )

            color = (
                "#00eaff"
                if is_unlocked
                else "#6c718c"
            )

            tk.Label(
                card,
                text=achievement["icon"],
                bg="#101323",
                fg=color,
                font=("Arial", 30)
            ).pack(
                anchor="w",
                padx=20,
                pady=(15, 5)
            )

            tk.Label(
                card,
                text=achievement["name"],
                bg="#101323",
                fg=color,
                font=("Arial", 14, "bold")
            ).pack(
                anchor="w",
                padx=20
            )

            tk.Label(
                card,
                text=achievement["description"],
                bg="#101323",
                fg="#9da5c5",
                wraplength=350,
                justify="left"
            ).pack(
                anchor="w",
                padx=20,
                pady=8
            )

            tk.Label(
                card,
                text=status,
                bg="#101323",
                fg=color,
                font=("Arial", 9, "bold")
            ).pack(
                anchor="w",
                padx=20,
                pady=(0, 15)
            )

    # ========================================================
    # SMART COACH
    # ========================================================

    def coach_page(self):

        self.hero(
            "🧠 Smart Coach",
            "NEO//FIT analyzes your activity and turns it into actionable guidance."
        )

        recommendations = self.generate_coach_recommendations()

        c = self.card(
            self.content,
            "AI-STYLE PERFORMANCE COACH"
        )

        c.pack(
            fill="x",
            pady=10
        )

        for recommendation in recommendations:

            tk.Label(
                c,
                text="▸ " + recommendation,
                bg="#101323",
                fg="#cbd1ef",
                wraplength=800,
                justify="left",
                font=("Arial", 11)
            ).pack(
                anchor="w",
                padx=25,
                pady=9
            )

        tk.Label(
            self.content,
            text=(
                "Coach insights are generated from the performance data "
                "stored locally in this prototype."
            ),
            bg="#070812",
            fg="#7f87a8",
            wraplength=800,
            justify="left"
        ).pack(
            anchor="w",
            pady=15
        )

    def generate_coach_recommendations(self):

        recommendations = []

        workouts = self.user["workouts"]
        streak = self.user["streak"]
        best = self.user.get("best_pushups", 0)
        total_reps = self.user.get("total_reps", 0)

        if workouts == 0:

            recommendations.append(
                "You are at the beginning of your journey. "
                "Start with one controlled session."
            )

        elif workouts < 5:

            recommendations.append(
                "Your priority right now should be consistency. "
                "Build the habit before chasing advanced targets."
            )

        else:

            recommendations.append(
                "Your consistency is developing. "
                "Use performance data to set your next target."
            )

        if streak >= 7:

            recommendations.append(
                "Excellent streak. Protect your recovery and "
                "avoid turning every session into a maximum-effort attempt."
            )

        elif streak >= 3:

            recommendations.append(
                "You have momentum. Keep the streak going while "
                "maintaining controlled technique."
            )

        else:

            recommendations.append(
                "Your next opportunity is consistency. "
                "Focus on completing another controlled session."
            )

        if best >= 100:

            recommendations.append(
                "Your push-up performance is approaching the "
                "benchmark zone. Prioritize technique and recovery."
            )

        elif best >= 50:

            recommendations.append(
                "You have entered the Record Chaser zone. "
                "Your next milestone is improving your personal best safely."
            )

        else:

            recommendations.append(
                "Your push-up baseline is still developing. "
                "Track your personal best instead of comparing yourself "
                "directly with elite performers."
            )

        recommendations.append(
            f"Your current total tracked repetitions are {total_reps}. "
            "Use this number as your long-term progress indicator."
        )

        return recommendations

    # ========================================================
    # ANALYTICS
    # ========================================================

    def analytics_page(self):

        self.hero(
            "📊 Performance Analytics",
            "Convert raw workout activity into a simple performance dashboard."
        )

        sessions = self.user.get(
            "sessions",
            []
        )

        if sessions:

            total_session_reps = sum(
                s.get("reps", 0)
                for s in sessions
            )

            avg_score = (
                sum(
                    s.get("score", 0)
                    for s in sessions
                ) / len(sessions)
            )

            avg_reps = (
                total_session_reps /
                len(sessions)
            )

        else:

            avg_score = 0
            avg_reps = 0

        metrics = self.card(
            self.content,
            "Performance Metrics"
        )

        metrics.pack(
            fill="x",
            pady=10
        )

        data = [
            ("Sessions Recorded", len(sessions)),
            ("Average Reps / Session", f"{avg_reps:.1f}"),
            ("Average Mission Score", f"{avg_score:.1f}/100"),
            ("Best Push-Ups", self.user.get("best_pushups", 0)),
            ("Total Reps", self.user.get("total_reps", 0)),
            ("Total XP", self.user.get("xp", 0))
        ]

        for label, value in data:

            row = tk.Frame(
                metrics,
                bg="#101323"
            )

            row.pack(
                fill="x",
                padx=20,
                pady=5
            )

            tk.Label(
                row,
                text=label,
                bg="#101323",
                fg="#9da5c5",
                width=25,
                anchor="w"
            ).pack(side="left")

            tk.Label(
                row,
                text=value,
                bg="#101323",
                fg="#00eaff",
                font=("Arial", 11, "bold")
            ).pack(side="left")

        # ----------------------------------------------------
        # RECENT SESSIONS
        # ----------------------------------------------------

        history = self.card(
            self.content,
            "Recent Sessions"
        )

        history.pack(
            fill="both",
            expand=True,
            pady=15
        )

        if not sessions:

            tk.Label(
                history,
                text="No sessions recorded yet.",
                bg="#101323",
                fg="#9da5c5"
            ).pack(
                pady=30
            )

        else:

            for session in reversed(sessions[-8:]):

                text = (
                    f"{session.get('timestamp', '')}   •   "
                    f"{session.get('exercise', 'Workout')}   •   "
                    f"{session.get('reps', 0)} reps   •   "
                    f"Score {session.get('score', 0)}/100"
                )

                tk.Label(
                    history,
                    text=text,
                    bg="#101323",
                    fg="#cbd1ef",
                    anchor="w"
                ).pack(
                    fill="x",
                    padx=20,
                    pady=5
                )

    # ========================================================
    # SAFETY
    # ========================================================

    def safety_page(self):

        self.hero(
            "Safety Protocol",
            "Getting stronger starts with training intelligently."
        )

        c = self.card(
            self.content
        )

        c.pack(
            fill="both",
            expand=True
        )

        for title, items in SAFETY.items():

            tk.Label(
                c,
                text=title,
                bg="#101323",
                fg="white",
                font=("Arial", 14, "bold")
            ).pack(
                anchor="w",
                padx=20,
                pady=(15, 5)
            )

            for item in items:

                tk.Label(
                    c,
                    text="• " + item,
                    bg="#101323",
                    fg="#b7bed8",
                    wraplength=800,
                    justify="left"
                ).pack(
                    anchor="w",
                    padx=35,
                    pady=2
                )

        # ----------------------------------------------------
        # INTELLIGENT AGE MESSAGE
        # ----------------------------------------------------

        age = self.user.get(
            "age",
            18
        )

        if age < 18:

            advice = (
                "Your profile is in the 14–17 age range. "
                "Focus on technique, general fitness and appropriate progression."
            )

        else:

            advice = (
                "Your profile is in the 18–24 age range. "
                "Progress gradually and keep recovery in your schedule."
            )

        tk.Label(
            c,
            text="🧠 PERSONALIZED SAFETY CHECK",
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 13, "bold")
        ).pack(
            anchor="w",
            padx=20,
            pady=(20, 5)
        )

        tk.Label(
            c,
            text=advice,
            bg="#101323",
            fg="#cbd1ef",
            wraplength=800,
            justify="left"
        ).pack(
            anchor="w",
            padx=20
        )

        tk.Label(
            c,
            text=(
                "This app provides general fitness information, not "
                "individualized medical advice. If someone has an injury, "
                "medical condition, or concerns about exercise safety, "
                "they should consult an appropriate healthcare or fitness professional."
            ),
            bg="#101323",
            fg="#9da5c5",
            wraplength=800,
            justify="left"
        ).pack(
            anchor="w",
            padx=20,
            pady=20
        )

    # ========================================================
    # SAVE / LOAD
    # ========================================================

    def save_user(self):

        try:

            Path(DATA_FILE).write_text(
                json.dumps(
                    self.user,
                    indent=2
                ),
                encoding="utf-8"
            )

        except OSError:
            pass

    def load_user(self):

        try:

            p = Path(DATA_FILE)

            if p.exists():

                saved = json.loads(
                    p.read_text(
                        encoding="utf-8"
                    )
                )

                if (
                    saved.get("username")
                    and saved.get("age")
                ):

                    # Safely merge old save files
                    self.user.update(saved)

                    # Make sure new fields exist
                    defaults = {
                        "total_reps": 0,
                        "best_pushups": 0,
                        "total_score": 0,
                        "sessions": [],
                        "achievements": [],
                        "streak_shield": 1,
                        "challenge_progress": 0
                    }

                    for key, value in defaults.items():

                        if key not in self.user:
                            self.user[key] = value

                    self.enter_app()

        except (
            OSError,
            json.JSONDecodeError,
            TypeError
        ):
            pass

    # ========================================================
    # LOGOUT
    # ========================================================

    def logout(self):

        self.pause_timer()

        self.show_login()


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    app = NeoFit()

    app.mainloop()
