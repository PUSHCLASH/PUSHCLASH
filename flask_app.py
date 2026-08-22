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
# WORLD RECORD DATA
# ============================================================

WORLD_RECORD = {
    "reps": 119,
    "name": "Jarrad Young",
    "country": "Australia",
    "date": "June 28, 2021",
    "category": "Most standard push-ups in one minute"
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
# QUOTES
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


class NeoFit(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title(APP_NAME)
        self.geometry("1200x760")
        self.minsize(900, 650)
        self.configure(bg="#070812")

        self.user = {
            "username": "",
            "email": "",
            "age": 0,
            "xp": 0,
            "level": 1,
            "streak": 0,
            "workouts": 0,
            "best_pushups": 0
        }

        self.timer_seconds = 30
        self.timer_running = False
        self.timer_token = 0
        self.current_exercise = None

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

        self.show_login()
        self.load_user()

    # ========================================================
    # BUTTON
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
            text="Prototype login — connect a real authentication "
                 "backend for production use.",
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
    # ENTER APP
    # ========================================================

    def enter_app(self):

        self.build_app()
        self.show_page("dashboard")

    # ========================================================
    # BUILD APP
    # ========================================================

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
        ).pack(
            side="left",
            padx=25
        )

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

        nav = tk.Frame(
            self,
            bg="#090b17",
            width=210
        )

        nav.pack(
            side="left",
            fill="y"
        )

        self.nav_buttons = {}

        # ====================================================
        # NEW WORLD RECORD BUTTON ADDED HERE
        # ====================================================

        for key, text in [
            ("dashboard", "🏠 Dashboard"),
            ("exercises", "💪 Exercises"),
            ("workout", "⚔️ Workout"),
            ("progress", "📈 Progress"),
            ("world_record", "🌍 World Record"),
            ("safety", "🛡️ Safety")
        ]:

            b = self.make_button(
                nav,
                text,
                lambda k=key: self.show_page(k)
            )

            b.pack(
                fill="x",
                padx=12,
                pady=5
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

    # ========================================================
    # CLEAR
    # ========================================================

    def clear(self):

        for widget in self.winfo_children():
            widget.destroy()

    # ========================================================
    # HEADER
    # ========================================================

    def update_header(self):

        if hasattr(self, "header_name"):

            self.header_name.config(
                text=f"{self.user['username']}  •  Lv. {self.user['level']}"
            )

            self.avatar.config(
                text=self.user["username"][:1].upper() or "P"
            )

    # ========================================================
    # PAGE SYSTEM
    # ========================================================

    def show_page(self, page):

        for w in self.content.winfo_children():
            w.destroy()

        for k, b in self.nav_buttons.items():

            b.config(
                bg="#0b0e1b",
                fg="#aeb5d2"
            )

        self.nav_buttons[page].config(
            bg="#101a2c",
            fg="#00eaff"
        )

        if page == "dashboard":
            self.dashboard()

        elif page == "exercises":
            self.exercises_page()

        elif page == "workout":
            self.workout_page()

        elif page == "progress":
            self.progress_page()

        elif page == "world_record":
            self.world_record_page()

        elif page == "safety":
            self.safety_page()

    # ========================================================
    # HERO
    # ========================================================

    def hero(self, title, subtitle):

        f = tk.Frame(
            self.content,
            bg="#101323",
            highlightbackground="#292e4b",
            highlightthickness=1
        )

        f.pack(
            fill="x",
            pady=(0, 20)
        )

        tk.Label(
            f,
            text=title,
            bg="#101323",
            fg="white",
            font=("Arial", 30, "bold")
        ).pack(
            anchor="w",
            padx=25,
            pady=(25, 5)
        )

        tk.Label(
            f,
            text=subtitle,
            bg="#101323",
            fg="#9da5c5",
            font=("Arial", 11),
            wraplength=800,
            justify="left"
        ).pack(
            anchor="w",
            padx=25,
            pady=(0, 25)
        )

    # ========================================================
    # CARD
    # ========================================================

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
    # DASHBOARD
    # ========================================================

    def dashboard(self):

        self.hero(
            f"Welcome back, {self.user['username']}",
            "Your mission today: move safely, build consistency, "
            "and level up one workout at a time."
        )

        stats = tk.Frame(
            self.content,
            bg="#070812"
        )

        stats.pack(fill="x")

        for label, value in [
            ("LEVEL", self.user["level"]),
            ("XP", self.user["xp"]),
            ("STREAK", f"{self.user['streak']} 🔥"),
            ("WORKOUTS", self.user["workouts"])
        ]:

            c = self.card(stats)

            c.pack(
                side="left",
                fill="both",
                expand=True,
                padx=5
            )

            tk.Label(
                c,
                text=label,
                bg="#101323",
                fg="#9da5c5",
                font=("Arial", 9)
            ).pack(
                anchor="w",
                padx=15,
                pady=(15, 0)
            )

            tk.Label(
                c,
                text=value,
                bg="#101323",
                fg="#00eaff",
                font=("Arial", 22, "bold")
            ).pack(
                anchor="w",
                padx=15,
                pady=(5, 15)
            )

        mission = self.card(
            self.content,
            "Today's Mission"
        )

        mission.pack(
            fill="x",
            pady=20
        )

        tk.Label(
            mission,
            text="⚡ Beginner Full Body",
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
            text=f"Balanced session for age {self.user['age']}.",
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
            f"Learn the movement before increasing the challenge. "
            f"Recommended for age {self.user['age']}."
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

    # ========================================================
    # EXERCISE WINDOW
    # ========================================================

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

        self.timer_label.pack(pady=15)

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

    # ========================================================
    # TIMER
    # ========================================================

    def format_time(self):

        return f"{self.timer_seconds // 60:02d}:{self.timer_seconds % 60:02d}"

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
    # COMPLETE WORKOUT
    # ========================================================

    def complete_workout(self):

        self.user["workouts"] += 1
        self.user["xp"] += 50
        self.user["streak"] += 1

        self.check_level()

        self.save_user()
        self.update_header()

        messagebox.showinfo(
            "MISSION COMPLETE",
            "MISSION COMPLETE! +50 XP ⚡"
        )

        self.reset_timer()

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
            "Every completed session gives you XP."
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

    # ========================================================
    # 🌍 WORLD RECORD PAGE
    # ========================================================

    def world_record_page(self):

        self.hero(
            "🌍 World Record",
            "See how your one-minute push-up performance compares "
            "with the published benchmark."
        )

        # ----------------------------------------------------
        # RECORD CARD
        # ----------------------------------------------------

        record = self.card(
            self.content
        )

        record.pack(
            fill="both",
            expand=True,
            pady=5
        )

        tk.Label(
            record,
            text="🌍 WORLD RECORD BENCHMARK",
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 11, "bold")
        ).pack(
            pady=(30, 5)
        )

        tk.Label(
            record,
            text="MOST STANDARD PUSH-UPS\nIN ONE MINUTE",
            bg="#101323",
            fg="white",
            font=("Arial", 23, "bold"),
            justify="center"
        ).pack(pady=10)

        # Big record number

        tk.Label(
            record,
            text=str(WORLD_RECORD["reps"]),
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 65, "bold")
        ).pack(pady=(10, 0))

        tk.Label(
            record,
            text="PUSH-UPS / 60 SECONDS",
            bg="#101323",
            fg="#9da5c5",
            font=("Arial", 10, "bold")
        ).pack()

        # Person

        tk.Label(
            record,
            text="🏆 " + WORLD_RECORD["name"],
            bg="#101323",
            fg="white",
            font=("Arial", 20, "bold")
        ).pack(pady=(25, 5))

        tk.Label(
            record,
            text="🇦🇺 " + WORLD_RECORD["country"],
            bg="#101323",
            fg="#b7bed8",
            font=("Arial", 12)
        ).pack()

        tk.Label(
            record,
            text="📅 " + WORLD_RECORD["date"],
            bg="#101323",
            fg="#7f87a8",
            font=("Arial", 10)
        ).pack(pady=5)

        tk.Label(
            record,
            text=WORLD_RECORD["category"],
            bg="#101323",
            fg="#9da5c5",
            font=("Arial", 9)
        ).pack(pady=(0, 20))

        # ----------------------------------------------------
        # COMPARISON
        # ----------------------------------------------------

        compare = tk.Frame(
            record,
            bg="#101323"
        )

        compare.pack(
            fill="x",
            padx=80,
            pady=15
        )

        tk.Label(
            compare,
            text="YOUR 1-MINUTE PUSH-UP COUNT",
            bg="#101323",
            fg="#cbd1ef",
            font=("Arial", 10, "bold")
        ).pack()

        self.record_reps_var = tk.StringVar()

        entry = tk.Entry(
            compare,
            textvariable=self.record_reps_var,
            bg="#090c18",
            fg="white",
            insertbackground="white",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#292e49",
            justify="center",
            font=("Arial", 15, "bold")
        )

        entry.pack(
            pady=10,
            ipadx=10,
            ipady=8
        )

        self.make_button(
            compare,
            "⚡ COMPARE WITH WORLD RECORD",
            self.compare_record,
            True
        ).pack(pady=10)

        # ----------------------------------------------------
        # RESULTS
        # ----------------------------------------------------

        self.record_result_frame = tk.Frame(
            record,
            bg="#101323"
        )

        self.record_result_frame.pack(
            fill="x",
            padx=50,
            pady=10
        )

        self.record_result_label = tk.Label(
            self.record_result_frame,
            text="Enter your one-minute result to see your comparison.",
            bg="#101323",
            fg="#9da5c5",
            font=("Arial", 11),
            wraplength=700,
            justify="center"
        )

        self.record_result_label.pack(
            pady=15
        )

        self.record_progress = ttk.Progressbar(
            self.record_result_frame,
            maximum=100,
            value=0
        )

        self.record_progress.pack(
            fill="x",
            padx=20,
            pady=10
        )

        self.record_percentage_label = tk.Label(
            self.record_result_frame,
            text="0% of benchmark",
            bg="#101323",
            fg="#00eaff",
            font=("Arial", 18, "bold")
        )

        self.record_percentage_label.pack(
            pady=5
        )

        self.record_remaining_label = tk.Label(
            self.record_result_frame,
            text="",
            bg="#101323",
            fg="#b7bed8",
            font=("Arial", 11)
        )

        self.record_remaining_label.pack(
            pady=5
        )

    # ========================================================
    # WORLD RECORD CALCULATOR
    # ========================================================

    def compare_record(self):

        value = self.record_reps_var.get().strip()

        if not value:

            messagebox.showwarning(
                "World Record",
                "Please enter your one-minute push-up count."
            )

            return

        try:

            reps = int(value)

        except ValueError:

            messagebox.showwarning(
                "World Record",
                "Please enter a whole number."
            )

            return

        if reps < 0:

            messagebox.showwarning(
                "World Record",
                "Push-up count cannot be negative."
            )

            return

        record = WORLD_RECORD["reps"]

        percentage = (
            reps / record
        ) * 100

        remaining = max(
            record - reps,
            0
        )

        # Cap progress bar at 100%

        display_percentage = min(
            percentage,
            100
        )

        self.record_progress["value"] = display_percentage

        self.record_percentage_label.config(
            text=f"{percentage:.1f}% of benchmark"
        )

        # ----------------------------------------------------
        # Record reached
        # ----------------------------------------------------

        if reps >= record:

            self.record_result_label.config(
                text=(
                    f"🔥 INCREDIBLE!\n\n"
                    f"You reached {reps} push-ups in one minute.\n"
                    f"That equals or exceeds the {record}-rep benchmark."
                ),
                fg="#00eaff"
            )

            self.record_remaining_label.config(
                text=(
                    f"Benchmark reached by "
                    f"{reps - record} reps."
                ),
                fg="#00eaff"
            )

        else:

            self.record_result_label.config(
                text=(
                    f"You completed {reps} push-ups.\n\n"
                    f"You are {remaining} reps away "
                    f"from the benchmark."
                ),
                fg="white"
            )

            self.record_remaining_label.config(
                text=(
                    f"{remaining} more reps would reach "
                    f"the {record}-rep benchmark."
                ),
                fg="#b7bed8"
            )

        # Save best result

        if reps > self.user.get("best_pushups", 0):

            self.user["best_pushups"] = reps
            self.save_user()

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

        tk.Label(
            c,
            text="This app provides general fitness information, not individualized medical advice. "
                 "If someone has an injury, medical condition, or concerns about exercise safety, "
                 "they should consult an appropriate healthcare or fitness professional.",
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
    # SAVE USER
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

    # ========================================================
    # LOAD USER
    # ========================================================

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

                    self.user.update(saved)

                    # Make sure older user files
                    # get the new field.

                    if "best_pushups" not in self.user:
                        self.user["best_pushups"] = 0

                    self.enter_app()

        except (
            OSError,
            json.JSONDecodeError
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
