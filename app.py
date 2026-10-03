from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import threading
import os
import reminder
from werkzeug.security import generate_password_hash, check_password_hash
from pywebpush import webpush, WebPushException

load_dotenv()

app = Flask(__name__)

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")

if not VAPID_PRIVATE_KEY:
    raise RuntimeError(
        "VAPID_PRIVATE_KEY is not set in the environment."
    )

VAPID_CLAIMS = {
    "sub": "mailto:akinkumar345@gmail.com"
}


app.secret_key = "smart_medicine_reminder_secret_key"

def start_reminder_thread():

    reminder_thread = threading.Thread(
        target=reminder.start_reminder,
        args=(VAPID_PRIVATE_KEY, VAPID_CLAIMS),
        daemon=True
    )

    reminder_thread.start()



# =========================================================
# DATABASE CONNECTION
# =========================================================


def db_fetchone(conn, query, params=()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchone()


def db_fetchall(conn, query, params=()):
    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchall()

def get_db():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

def init_db():

    conn = get_db()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Profile table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT,
            age INTEGER,
            gender TEXT,
            weight REAL,
            medical_condition TEXT,
            contact TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Medicines table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            medicine_type TEXT NOT NULL,
            strength REAL NOT NULL,
            from_date TEXT NOT NULL,
            to_date TEXT NOT NULL,
            time TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
        # Push notification subscriptions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()

        user = db_fetchone(conn, 
            "SELECT * FROM users WHERE username = %s",
            (username,)
        )

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("dashboard"))

        return """
        <script>
            alert("Invalid username or password!");
            window.location.href="/login";
        </script>
        """

    return render_template("login.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Check password
        if password != confirm_password:

            return """
            <script>
                alert("Passwords do not match!");
                window.location.href="/register";
            </script>
            """

        # Hash password
        hashed_password = generate_password_hash(password)

        conn = get_db()

        try:

            conn.cursor().execute(
                """
                INSERT INTO users
                (username, password)
                VALUES (%s, %s)
                """,
                (username, hashed_password)
            )

            conn.commit()
            conn.close()

            return """
            <script>
                alert("Registration successful!");
                window.location.href="/login";
            </script>
            """

        except psycopg2.IntegrityError:

            conn.close()

            return """
            <script>
                alert("Username already exists!");
                window.location.href="/register";
            </script>
            """

    return render_template("register.html")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        username=session["username"]
    )


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db()

    if request.method == "POST":

        name = request.form["name"]
        age = request.form["age"]
        gender = request.form["gender"]
        weight = request.form["weight"]
        medical_condition = request.form["medical_condition"]
        contact = request.form["contact"]

        # Check whether profile already exists
        existing_profile = db_fetchone(conn, 
            "SELECT id FROM profiles WHERE user_id = %s",
            (user_id,)
        )

        if existing_profile:

            conn.cursor().execute(
                """
                UPDATE profiles
                SET name = %s,
                    age = %s,
                    gender = %s,
                    weight = %s,
                    medical_condition = %s,
                    contact = %s
                WHERE user_id = %s
                """,
                (
                    name,
                    age,
                    gender,
                    weight,
                    medical_condition,
                    contact,
                    user_id
                )
            )

        else:

            conn.cursor().execute(
                """
                INSERT INTO profiles
                (
                    user_id,
                    name,
                    age,
                    gender,
                    weight,
                    medical_condition,
                    contact
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    name,
                    age,
                    gender,
                    weight,
                    medical_condition,
                    contact
                )
            )

        conn.commit()
        conn.close()

        return """
        <script>
            alert("Profile saved successfully!");
            window.location.href="/profile";
        </script>
        """

    # Get existing profile
    profile_data = db_fetchone(conn, 
        """
        SELECT *
        FROM profiles
        WHERE user_id = %s
        """,
        (user_id,)
    )

    conn.close()

    # Existing profiles are view-only until Edit Profile is clicked.
    # New users can enter their profile information immediately.
    edit_mode = request.args.get("edit") == "1"

    return render_template(
        "profile.html",
        profile=profile_data,
        edit_mode=edit_mode
    )


# =========================================================
# MEDICINE DETAILS
# =========================================================

@app.route("/medicine", methods=["GET", "POST"])
def medicine():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        medicine_type = request.form["medicine_type"]
        strength = request.form["strength"]
        from_date = request.form["from_date"]
        to_date = request.form["to_date"]
        medicine_time = request.form["time"]

        # Check date range
        if from_date > to_date:

            return """
            <script>
                alert("To Date must be after From Date!");
                window.location.href="/medicine";
            </script>
            """

        conn = get_db()

        conn.cursor().execute(
            """
            INSERT INTO medicines
            (
                user_id,
                medicine_type,
                strength,
                from_date,
                to_date,
                time
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                session["user_id"],
                medicine_type,
                strength,
                from_date,
                to_date,
                medicine_time
            )
        )

        conn.commit()
        conn.close()

        return """
        <script>
            alert("Medicine saved successfully!");
            window.location.href="/view";
        </script>
        """

    return render_template("medicine.html")


# =========================================================
# VIEW MEDICINES
# =========================================================

@app.route("/view")
def view():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    medicines = db_fetchall(conn, 
        """
        SELECT *
        FROM medicines
        WHERE user_id = %s
        ORDER BY from_date, time
        """,
        (session["user_id"],)
    )

    conn.close()

    return render_template(
        "view.html",
        medicines=medicines
    )


# =========================================================
# CHATBOT
# =========================================================

@app.route("/chatbot")
def chatbot():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("chatbot.html")


@app.route("/api/chatbot", methods=["POST"])
def chatbot_api():
    """Medicine-reminder assistant API.

    This endpoint handles app/navigation questions and returns the
    logged-in user's own medicine schedule when requested. It does
    not diagnose conditions or recommend changing medicine doses.
    """

    if "user_id" not in session:
        return jsonify({
            "success": False,
            "reply": "Please log in first to use the Medicine Assistant."
        }), 401

    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    text = message.lower()

    if not message:
        return jsonify({
            "success": False,
            "reply": "Please type a question. For example: “How do I add a medicine?”"
        })

    # ---- Navigation / app help ----
    if (
        ("add" in text or "save" in text or "create" in text)
        and "medicine" in text
    ):
        return jsonify({
            "success": True,
            "intent": "add_medicine",
            "reply": (
                "To add a medicine: open Dashboard → Medicine Details. "
                "Enter the medicine type/name, strength, From Date, To Date "
                "and reminder time, then save it. After saving, your medicine "
                "appears in View Medicines."
            )
        })

    if (
        ("view" in text or "see" in text or "show" in text or "list" in text)
        and ("medicine" in text or "medication" in text)
    ):
        return jsonify({
            "success": True,
            "intent": "view_medicines",
            "reply": "You can open View Medicines from the Dashboard. I can also show your saved medicine schedule here.",
            "action": {"label": "Open View Medicines", "url": "/view"}
        })

    if (
        ("my medicine" in text or "my medicines" in text or
         "my medication" in text or "what medicine" in text or
         "which medicine" in text or "medicine list" in text)
    ):
        conn = get_db()
        medicines = db_fetchall(conn, 
            """
            SELECT medicine_type, strength, from_date, to_date, time
            FROM medicines
            WHERE user_id = %s
            ORDER BY from_date, time
            """,
            (session["user_id"],)
        )
        conn.close()

        if not medicines:
            reply = (
                "You do not have any saved medicines yet. "
                "Open Medicine Details to add your first medicine."
            )
        else:
            lines = ["Here are your saved medicines:"]
            for med in medicines:
                lines.append(
                    f"• {med['medicine_type']} — {med['strength']} "
                    f"from {med['from_date']} to {med['to_date']} at {med['time']}"
                )
            reply = "\n".join(lines)

        return jsonify({
            "success": True,
            "intent": "my_medicines",
            "reply": reply,
            "action": {"label": "Open View Medicines", "url": "/view"}
        })

    if "profile" in text or "personal details" in text:
        return jsonify({
            "success": True,
            "intent": "profile",
            "reply": (
                "Open Profile from the Dashboard to manage your personal and "
                "medical information."
            ),
            "action": {"label": "Open Profile", "url": "/profile"}
        })

    if (
        "notification" in text or "notifications" in text or
        "push notification" in text
    ):
        return jsonify({
            "success": True,
            "intent": "notifications",
            "reply": (
                "On the Dashboard, click “Enable Notifications” and allow "
                "browser notifications. Your browser must permit notifications "
                "for the reminder alerts to appear."
            ),
            "action": {"label": "Open Dashboard", "url": "/dashboard"}
        })

    if "reminder" in text or "remind" in text or "alert" in text:
        return jsonify({
            "success": True,
            "intent": "reminders",
            "reply": (
                "A reminder is based on the From Date, To Date and Time saved "
                "with your medicine. Make sure browser notifications are enabled "
                "on the Dashboard."
            ),
            "action": {"label": "Open Dashboard", "url": "/dashboard"}
        })

    if (
        "forgot" in text and ("dose" in text or "medicine" in text)
    ) or "missed dose" in text:
        return jsonify({
            "success": True,
            "intent": "missed_dose",
            "reply": (
                "For a missed dose, the correct action depends on the medicine. "
                "Do not automatically take a double dose. Check the medicine's "
                "official patient instructions or contact a pharmacist/doctor "
                "for advice specific to your medicine."
            )
        })

    # ---- General medicine information ----
    if any(k in text for k in [
        "what is medicine", "what are medicines", "what is medication",
        "medicine meaning", "medication meaning"
    ]):
        return jsonify({
            "success": True,
            "intent": "medicine_basics",
            "reply": (
                "A medicine is a substance used to prevent, diagnose, relieve, "
                "or treat a health condition. Medicines can have benefits, "
                "side effects, interactions, and precautions, so they should "
                "be used according to the prescribed or official instructions."
            )
        })

    if any(k in text for k in [
        "side effect", "side effects", "adverse effect", "reaction"
    ]):
        return jsonify({
            "success": True,
            "intent": "side_effects",
            "reply": (
                "Side effects depend on the specific medicine and person. "
                "Common effects can sometimes be mild, but severe or unusual "
                "symptoms need prompt medical attention. Tell me the exact "
                "medicine name if you want help understanding its usual "
                "patient-information warnings; I will not diagnose you."
            )
        })

    if any(k in text for k in [
        "interaction", "drug interaction", "medicine interaction",
        "can i take", "take together"
    ]):
        return jsonify({
            "success": True,
            "intent": "interactions",
            "reply": (
                "Medicine interactions depend on the exact medicines, doses, "
                "medical conditions, and sometimes food or supplements. "
                "Please provide the exact medicine names, and verify the "
                "combination with a pharmacist or doctor before taking them "
                "together."
            )
        })

    if any(k in text for k in [
        "stop medicine", "stopping medicine", "can i stop", "discontinue"
    ]):
        return jsonify({
            "success": True,
            "intent": "stopping_medicine",
            "reply": (
                "Do not stop a prescribed medicine just because symptoms "
                "improve unless your prescriber tells you to. Some medicines "
                "can cause problems if stopped suddenly."
            )
        })

    if any(k in text for k in [
        "storage", "store medicine", "keep medicine", "where to keep"
    ]):
        return jsonify({
            "success": True,
            "intent": "storage",
            "reply": (
                "Storage instructions vary by medicine. Follow the label or "
                "patient information leaflet. In general, keep medicines in "
                "their original container, away from children, excessive heat "
                "and moisture, unless the label gives different instructions."
            )
        })

    if any(k in text for k in [
        "expired", "expiry", "expiration", "expired medicine"
    ]):
        return jsonify({
            "success": True,
            "intent": "expiry",
            "reply": (
                "Do not use a medicine after its expiry date unless a qualified "
                "health professional specifically advises otherwise. Check the "
                "package for the expiry date and ask a pharmacist about safe "
                "disposal."
            )
        })

    if any(k in text for k in [
        "overdose", "too much medicine", "took too much", "extra dose"
    ]):
        return jsonify({
            "success": True,
            "intent": "overdose",
            "reply": (
                "If you may have taken too much medicine, treat it as a "
                "potentially urgent situation. Contact local emergency "
                "services or a poison-control service immediately, especially "
                "if there are symptoms such as severe sleepiness, breathing "
                "problems, confusion, seizures, or loss of consciousness."
            )
        })

    if any(k in text for k in [
        "pregnant", "pregnancy", "breastfeeding", "breast feeding"
    ]):
        return jsonify({
            "success": True,
            "intent": "pregnancy",
            "reply": (
                "Medicine safety during pregnancy or breastfeeding depends on "
                "the exact medicine and situation. Do not start, stop, or "
                "change a medicine based only on a chatbot response; check "
                "with your doctor or pharmacist."
            )
        })

    # ---- Greetings / general help ----
    if any(k in text for k in ["hello", "hi", "hey", "good morning", "good evening"]):
        return jsonify({
            "success": True,
            "intent": "greeting",
            "reply": (
                "Hello! 👋 I’m your Smart Medicine Assistant. You can ask me "
                "about adding medicines, viewing your medicines, reminders, "
                "notifications, your saved schedule, or general medicine safety."
            )
        })

    if "thank" in text:
        return jsonify({
            "success": True,
            "intent": "thanks",
            "reply": "You're welcome! 💊 Stay safe and follow your prescribed medicine instructions."
        })

    return jsonify({
        "success": True,
        "intent": "fallback",
        "reply": (
            "I can help with:\n"
            "• Adding a medicine\n"
            "• Viewing your saved medicines\n"
            "• Checking your medicine schedule\n"
            "• Reminders and notifications\n"
            "• Profile and dashboard navigation\n"
            "• General medicine safety, side effects, interactions, storage and missed doses\n\n"
            "For medicine-specific questions, send the exact medicine name and your question. "
            "I won't guess a dose or tell you to start/stop a prescription."
        )
    })
    # =========================================================
# SAVE PUSH NOTIFICATION SUBSCRIPTION
# =========================================================

@app.route("/save-subscription", methods=["POST"])
def save_subscription():

    if "user_id" not in session:
        return {
            "success": False,
            "message": "Please login first"
        }, 401

    data = request.get_json()

    endpoint = data["endpoint"]
    p256dh = data["keys"]["p256dh"]
    auth = data["keys"]["auth"]

    conn = get_db()

    # Remove old subscription(s) for this user
    conn.cursor().execute(
        """
        DELETE FROM push_subscriptions
        WHERE user_id = %s
        """,
        (session["user_id"],)
    )

    # Save the new subscription
    conn.cursor().execute(
        """
        INSERT INTO push_subscriptions
        (
            user_id,
            endpoint,
            p256dh,
            auth
        )
        VALUES (%s, %s, %s, %s)
        """,
        (
            session["user_id"],
            endpoint,
            p256dh,
            auth
        )
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Notification subscription saved"
    }

# =========================================================
# TEST PUSH NOTIFICATION
# =========================================================

@app.route("/test-notification")
def test_notification():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    subscriptions = db_fetchall(conn, 
        """
        SELECT id, endpoint, p256dh, auth
        FROM push_subscriptions
        WHERE user_id = %s
        """,
        (session["user_id"],)
    )
    print(
        "TEST NOTIFICATION: subscription_count =",
        len(subscriptions)
    )

    print(
        "TEST NOTIFICATION: subscriptions =",
        subscriptions
    )
    conn.close()

    if not subscriptions:
        return "No notification subscription found. Enable notifications first."

    notification_sent = False

    for subscription in subscriptions:

        push_subscription = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"]
            }
        }

        try:

            print("PUSH: Sending notification...")
            print("PUSH: subscription_id =", subscription["id"])

            response = webpush(
                subscription_info=push_subscription,
                data='{"title":"💊 Smart Medicine Reminder","body":"This is a test medicine reminder notification."}',
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )

            print("PUSH: Notification sent successfully")
            print("PUSH: Response =", response)

            notification_sent = True

        except WebPushException as error:

            print("PUSH WEBPUSH ERROR:", repr(error))
            print("PUSH WEBPUSH ERROR TEXT:", str(error))

            # Remove expired subscription
            if "410" in str(error):

                conn = get_db()

                conn.cursor().execute(
                    """
                    DELETE FROM push_subscriptions
                    WHERE id = %s
                    """,
                    (subscription["id"],)
                )

                conn.commit()
                conn.close()

            else:
                return (
            "Notification failed. "
            "Check the Render logs for the PUSH WEBPUSH ERROR."
        ), 500

        except Exception as error:

            print("PUSH GENERAL ERROR:", repr(error))
            print("PUSH GENERAL ERROR TEXT:", str(error))

            return (
                "Notification failed because of a server error. "
                "Check the Render logs."
            ), 500

    if notification_sent:
        return "Test notification sent successfully!"

    return "No valid notification subscription found."

# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# Start database and reminder thread when deployed with Gunicorn
print(">>> STARTING DATABASE <<<")
init_db()

print(">>> STARTING REMINDER THREAD <<<")
start_reminder_thread()

print(">>> APP INITIALIZATION COMPLETE <<<")

# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    init_db()
    start_reminder_thread()

    print("----------------------------------------")
    print(" Smart Medicine Reminder")
    print("----------------------------------------")
    print(" Database initialized")
    print(" Flask server starting...")
    print("----------------------------------------")

    app.run(
        debug=False,
        host="127.0.0.1",
        port=5000
    )