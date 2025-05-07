import os
import time
import json
import re

from flask import (
    Flask, render_template, request,
    redirect, session, url_for, jsonify
)
from openai import OpenAI
from dotenv import load_dotenv
from billing_tracker import log_usage
from scraper import get_dashboard_sections, get_client_feedback_by_id

# ————————————————————————————————————————————————————————————————
# Mock override for demo user
MOCK_FEEDBACK = """
Hello, this is a mock intro for your feedback page.  
PART 1: Today I ate an apple and a salad.  
PART 2: I walked 3 miles.  
PART 3: I feel energized!  
PART 4: I plan to keep this up tomorrow.
"""

_original_get = get_client_feedback_by_id
def get_client_feedback_by_id(email, password, client_id, date):
    if client_id == "MOCK123":
        return MOCK_FEEDBACK
    return _original_get(email, password, client_id, date)

# ————————————————————————————————————————————————————————————————
# Bootstrapping
load_dotenv()
client = OpenAI()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# per-token rates
MODEL_RATES = {
    "gpt-3.5-turbo": 0.002 / 1000,
    "gpt-4":         0.03  / 1000,
}

# ————————————————————————————————————————————————————————————————
def generate_response(feedback, model_name="gpt-3.5-turbo", section=None):
    """Return { content, usage } from OpenAI, or an error message."""
    prompt = (
        f"Only generate the tutor response for this specific section: {section}. Feedback: '{feedback}'"
        if section
        else f"Respond professionally and empathetically to this client feedback: '{feedback}'"
    )
    try:
        chat = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a supportive and empathetic fitness coach."},
                {"role": "user",   "content": prompt}
            ]
        )
        usage = chat.usage
        log_usage(model_name, usage.prompt_tokens, usage.completion_tokens)
        content = chat.choices[0].message.content.strip()
        return {"content": content, "usage": usage}
    except Exception as e:
        return {"content": f"[Error generating response: {e}]", "usage": None}

# ————————————————————————————————————————————————————————————————
def parse_parts(text):
    """
    Split the feedback into exactly five pieces:
      1. Client Info
      2. Part 1: HOW I ATE
      3. Part 2: MY WORKOUT
      4. Part 3: HOW I FEEL
      5. Part 4: THE NEW ME
    """
    markers = ["PART 1", "PART 2", "PART 3", "PART 4"]
    labels  = [
        "Client Info",
        "Part 1: HOW I ATE",
        "Part 2: MY WORKOUT",
        "Part 3: HOW I FEEL",
        "Part 4: THE NEW ME",
    ]

    # split on each marker, but keep the marker tokens
    tokens = re.split(r"(PART 1|PART 2|PART 3|PART 4)", text)

    parts = {}
    # tokens looks like: [intro, "PART 1", part1, "PART 2", part2, …, "PART 4", part4]
    parts[labels[0]] = tokens[0].strip()

    # each marker-content pair lives at odd-even indices
    for i in range(1, len(tokens), 2):
        marker  = tokens[i]     # e.g. "PART 1"
        content = tokens[i+1]   # the text after that marker
        idx     = markers.index(marker) + 1
        parts[labels[idx]] = content.strip()

    return parts

# ————————————————————————————————————————————————————————————————
@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/demo_login")
def demo_login():
    session["email"]    = "DEMO_USER"
    session["password"] = "DEMO_PASS"
    return redirect(url_for("mock_dashboard"))

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if request.method == "POST":
        session["email"]    = request.form["email"]
        session["password"] = request.form["password"]

    email    = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    now  = time.time()
    last = session.get("last_fetch_time", 0)
    data = session.get("dashboard", {})

    if now - last > 600 or not data or request.args.get("refresh"):
        print("🔄 Refreshing dashboard data...")
        data = get_dashboard_sections(email, password)
        session["dashboard"]       = data
        session["last_fetch_time"] = now
    else:
        print("✅ Using cached dashboard data")

    return render_template("dashboard.html", **data)

# ————————————————————————————————————————————————————————————————
@app.route("/generate/<client_id>/<date>", methods=["GET"])
@app.route("/generate/<client_id>/<date>/", methods=["GET"])
def generate(client_id, date):
    email    = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    feedback_text = get_client_feedback_by_id(email, password, client_id, date)
    parts         = parse_parts(feedback_text)
    # no AI calls here—just placeholders
    responses     = { label: None for label in parts }

    session["current_feedback"] = {
        "client_id":  client_id,
        "date":       date,
        "parts":      parts,
        "generated":  responses,
        "model":      "gpt-3.5-turbo",
        "usage":      [],
        "total_cost": 0.0
    }

    return render_template(
        "client_feedback.html",
        client_id=     client_id,
        date=          date,
        parts=         parts,
        responses=     responses
    )

@app.route("/api/regenerate_section", methods=["POST"])
def api_regenerate_section():
    """Regenerate a single section via AJAX, returning only that content."""
    payload = request.get_json() or {}
    label   = payload.get("label")
    model   = payload.get("model", "gpt-3.5-turbo")

    cf    = session.get("current_feedback", {})
    parts = cf.get("parts", {})

    if label not in parts:
        return jsonify({"error": "Unknown section"}), 400

    resp = generate_response(parts[label], model_name=model, section=label)
    new_content = resp["content"]

    # update session store so repeated AJAX calls work
    cf["generated"][label]       = new_content
    cf["model"]                  = model
    session["current_feedback"]  = cf

    return jsonify({
        "label":   label,
        "content": new_content
    })

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/mock_dashboard")
def mock_dashboard():
    """Stand-in data for demo_login → dashboard."""
    session["dashboard"] = {
        "weekend_reports":      [],
        "waiting_for_response": [
            {
                "name":           "Jane Doe (Silver)",
                "date":           "2025-04-22",
                "submitted_when": "just now",
                "id":             "MOCK123"
            }
        ],
        "feedback_report": {
            "Missed 5+ Days":   [],
            "Missed 4 Days":    [],
            "Missed 3 Days":    [],
            "Missed 2 Days":    [],
            "Missed Yesterday": []
        }
    }
    session["last_fetch_time"] = time.time()
    return redirect(url_for("dashboard"))

# ————————————————————————————————————————————————————————————————
if __name__ == "__main__":
    app.run(debug=True)
