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
    markers = ["PART 1", "PART 2", "PART 3", "PART 4"]
    labels  = [
        "Client Info",
        "Part 1: HOW I ATE",
        "Part 2: MY WORKOUT",
        "Part 3: HOW I FEEL",
        "Part 4: THE NEW ME",
    ]

    tokens = re.split(r"(PART 1|PART 2|PART 3|PART 4)", text)
    parts = {}
    parts[labels[0]] = extract_client_info(tokens[0])
  # Client Info

    for i in range(1, len(tokens), 2):
        marker  = tokens[i]
        content = tokens[i+1]
        idx     = markers.index(marker) + 1
        label   = labels[idx]

        # Apply custom cleaner based on the section
        if label == "Part 1: HOW I ATE":
            cleaned = clean_part_1(content)
        elif label == "Part 2: MY WORKOUT":
            cleaned = clean_part_2(content)
        elif label == "Part 3: HOW I FEEL":
            cleaned = clean_part_3(content)
        elif label == "Part 4: THE NEW ME":
            cleaned = clean_part_4(content)
        else:
            cleaned = content.strip()

        parts[label] = cleaned

    return parts

# ————————————————————————————————————————————————————————————————
@app.route("/")
def landing():
    return render_template("landing.html")

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
def extract_client_info(text):
    """
    Trim UI clutter and return only relevant client info sentences.
    """
    # 1. Cut off everything after "Show Details"
    snippet = re.split(r'(?i)\bshow details\b', text)[0]

    # 2. Break into sentences
    sentences = re.split(r'(?<=[\.\?!])\s+', snippet)

    keywords = [
        "phone call", "beginning weight", "current weight",
        "lost", "Consistency", "Total weight loss"
    ]

    # 3. Find the index of the first sentence that contains any keyword
    start = next((i for i, s in enumerate(sentences) if any(kw in s for kw in keywords)), 0)

    # 4. Only keep sentences from that point onward
    cleaned = [
        s.strip() for s in sentences[start:]
        if any(kw in s for kw in keywords)
    ]

    return " ".join(cleaned)

def clean_part_1(text):
    """Keep meals and ratings, cut intro."""
    match = re.search(r"(Rate how well you ate today.*?)Tutor Feedback", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()

def clean_part_2(text):
    """Keep movement details, remove leading ': MY MOVEMENT' and cut at Tutor Feedback."""
    text = re.sub(r"^:? ?MY MOVEMENT", "", text.strip(), flags=re.IGNORECASE)
    return re.split(r'Tutor Feedback', text, flags=re.IGNORECASE)[0].strip()


def clean_part_3(text):
    """Keep feelings, goals. Remove leading ': HOW I FEEL' and cut at Tutor Feedback."""
    text = re.sub(r"^:? ?HOW I FEEL", "", text.strip(), flags=re.IGNORECASE)
    return re.split(r'Tutor Feedback', text, flags=re.IGNORECASE)[0].strip()

def clean_part_4(text):
    """Keep gratitude, tomorrow tasks. Remove ': THE NEW ME' and cut off at Questions or Comments or Tutor Feedback."""
    text = re.sub(r"^:? ?THE NEW ME", "", text.strip(), flags=re.IGNORECASE)
    return re.split(r'(Questions or Comments|Tutor Feedback|Adam\'s Food For Thought)', text, flags=re.IGNORECASE)[0].strip()

@app.route("/generate/<client_id>/<date>", methods=["GET"])
@app.route("/generate/<client_id>/<date>/", methods=["GET"])
def generate(client_id, date):
    email    = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    feedback_text = get_client_feedback_by_id(email, password, client_id, date)

    # 2) Look up the client name from your cached dashboard
    dashboard = session.get("dashboard", {})
    waiting   = dashboard.get("waiting_for_response", [])
    match     = next(
        (c for c in waiting if str(c.get("id")) == str(client_id)),
        None
    )
    client_name = match["name"] if match and "name" in match else f"Client {client_id}"
    
    parts         = parse_parts(feedback_text)
    # no AI calls here—just placeholders
    responses     = { label: None for label in parts }

    session["current_feedback"] = {
        "client_name": client_name,
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
        client_name=   client_name,
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
