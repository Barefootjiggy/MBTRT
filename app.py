import os
import time
import json
import re
from redis import Redis
from flask_session import Session
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
John Doe's last phone call was 4 days ago. They committed to exercising 7 times this week. John Doe's beginning weight was 201lbs. (91.17 kgs.) and current weight is 193lbs. Consistency for May is 100%. Total weight loss is 8lbs. 

PART 1: Rate how well you ate today: ⭐⭐⭐⭐ (4 stars) Cups of water: 3 Meal 1 Time: 8:45 a.m. Meal 1: Ate an apple and a banana at 6:30 a.m. Ate 1/2 cup of steel cut oatmeal wtih bluberries, flaxseeds and walnuts at 8:45 a.m. Meal 2 Time: 2 p.m. Meal 2: Ate tofu wtth sliced peppers, onions and mushrooms in a wheat wrap and a salad at 2 p.m. FULLNESS SCALE: 4 Meal 3 Time: 7:30 p.m. Meal 3: Ate 3 small vegan tacos with a small serving of rice and beans and a salad (No Beer or guacamole) and a very small serving of chips at 7:30 p.m. (birthday dinner at a restaurant with my wife at my favorite vegan Mexican restaurant) Did not fast because it was my wife's birthday. Will fast on Wednesday instead. FULLNESS SCALE: 4  

PART 2: MY MOVEMENT Yesterday I said I would: Jog for at least 1 mile. Day #1,170 of the CORE EXERCISE STREAK. Day #1,105 of the UPPER BODY STREAK. Day #7 of the NO SNACKS AFTER DINNER STREAK. Rate today's activity (Only if you had any): ⭐⭐⭐⭐ (4 stars)Tell me what you achieved today: Jogged 1.80 miles. (Day #1,496 of the JOGGING STREAK)(Total Distance Jogged during STREAK: 2,861.78 miles) Day #1,170 of the CORE EXERCISE STREAK. Day #1,105 of the UPPER BODY STREAK. Day #7 of the NO SNACKS AFTER DINNER STREAK. Tell me what you commit to achieving tomorrow: Jog for at least 1 mile. Day #1,171 of the CORE EXERCISE STREAK. Day #1,106 of the UPPER BODY STREAK. Day #8 of the NO SNACKS AFTER DINNER STREAK.  

PART 3: HOW I FEEL Are there any food or movement/activity victories you're excited about? Hours of sleep last night: 7.5  

PART 4: THE NEW ME Three things I am grateful for today: My wife. We celebrated her birthday last night. Yesterday I said I would: 1-3 tasks I will accomplish tomorrow (not food or movement related): Questions or Comments:
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
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_REDIS'] = Redis.from_url(os.getenv("REDIS_URL"), ssl_cert_reqs=None)
Session(app)


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

    parts[labels[0]] = extract_client_info(tokens[0])  # Client Info

    for i in range(1, len(tokens), 2):
        marker  = tokens[i]
        content = tokens[i+1]
        idx     = markers.index(marker) + 1

        if labels[idx] == "Part 1: HOW I ATE":
            parts[labels[idx]] = clean_part_1(content)
        elif labels[idx] == "Part 2: MY WORKOUT":
            parts[labels[idx]] = clean_part_2(content)
        else:
            parts[labels[idx]] = clean_generic_part(content, marker)

    return parts

def extract_star_rating_from_html(html):
    rating_map = {
        "The Pits!": 1,
        "Mediocre": 2,
        "Decent": 3,
        "Good Stuff!": 4,
        "Amazing": 5
    }
    matches = re.findall(r'<input[^>]+type="radio"[^>]+title="([^"]+)"[^>]+checked', html)
    if matches:
        label = matches[0]  # e.g., "Mediocre"
        return rating_map.get(label, None)
    return None


def clean_part_1(text):
    """
    Extracts the selected star rating and relevant meal info from Part 1.
    Assumes the feedback includes a line like: 'Rate how well you ate today: 2'
    """
    print("=== PART 1 RAW ===")
    print(text)

    # Step 1: Extract rating
    rating_match = re.search(r"Rate how well you ate today:\s*([1-5])", text)
    rating_line = f"Rate how well you ate today: {rating_match.group(1)} stars" if rating_match else ""

    # Step 2: Remove intro prompt
    cleaned = re.sub(r"^:? ?HOW I ATE.*?(Rate how well you ate today:\s*[1-5])", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Step 3: Cut off after Tutor Feedback (or similar)
    content_match = re.split(r"(Tutor Feedback|Adam's Food For Thought)", cleaned, flags=re.IGNORECASE)
    meal_lines = content_match[0].strip() if content_match else cleaned.strip()

    # Step 4: Combine
    final_output = rating_line + "\n" + meal_lines.strip()
    return final_output.strip()

def clean_part_2(text):
    """
    Extracts the exercise rating and relevant movement info from Part 2.
    Assumes the feedback includes a line like:
    'Rate today's activity (Only if you had any): ⭐⭐⭐⭐ (4 stars)'
    """
    print("=== PART 2 RAW ===")
    print(text)

    # Step 1: Find the rating line (already injected by scraper)
    rating_match = re.search(
        r"Rate today's activity\s*\(Only if you had any\):\s*⭐+.*?\(\d stars\)",
        text
    )
    rating_line = rating_match.group(0).strip() if rating_match else ""

    # Step 2: Just keep everything as-is — don’t cut before the rating
    # We'll simply preserve the full block and remove UI junk after
    content_after_rating = re.split(
        r"(Tutor Feedback|Adam's Food For Thought|Save Draft|Terms of Use|Privacy Policy)",
        text,
        flags=re.IGNORECASE
    )[0].strip()

    return content_after_rating

def clean_generic_part(text, label):
    text = re.sub(rf"^:? ?{re.escape(label)}", "", text.strip(), flags=re.IGNORECASE)
    text = re.split(r'Tutor Feedback|Adam\'s Food For Thought|Save Draft|Terms of Use|Privacy Policy', text, flags=re.IGNORECASE)[0]
    return text.strip()

def extract_client_info(text):
    snippet = re.split(r'(?i)show details', text)[0]
    sentences = re.split(r'(?<=[.?!])\s+', snippet)
    keywords = [
        "phone call", "beginning weight", "current weight",
        "lost", "Consistency", "Total weight loss", "They committed"
    ]
    start = next((i for i, s in enumerate(sentences) if any(kw in s for kw in keywords)), 0)
    return " ".join(s.strip() for s in sentences[start:] if any(kw in s for kw in keywords))

# ————————————————————————————————————————————————————————————————
@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/replay")
def replay_saved_feedback():
    if not session.get("email") or session.get("demo_user"):
        return redirect(url_for("login"))

@app.route("/demo_login")
def demo_login():
    session["email"]    = "DEMO_USER"
    session["password"] = "DEMO_PASS"
    session["demo_user"] = True
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

    # 🔒 Save feedback for replay (skip for MOCK clients)
    if not client_id.startswith("MOCK"):
        filename = f"saved_feedback/{client_id}_{date}.txt"
        os.makedirs("saved_feedback", exist_ok=True)
        with open(filename, "w") as f:
            f.write(feedback_text)

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

@app.route("/api/generate_summary", methods=["POST"])
def api_generate_summary():
    payload = request.get_json() or {}
    model   = payload.get("model", "gpt-3.5-turbo")

    cf = session.get("current_feedback", {})
    parts = cf.get("parts", {})

    # Combine all parts except client info
    combined_feedback = "\n\n".join(
        content for label, content in parts.items() if label != "Client Info"
    )

    prompt = (
        "Read the following feedback from a client, then provide a short, motivational summary "
        "and a tip they should keep in mind moving forward.\n\n"
        f"{combined_feedback}"
    )

    try:
        chat = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a supportive and insightful fitness coach."},
                {"role": "user", "content": prompt}
            ]
        )
        usage = chat.usage
        content = chat.choices[0].message.content.strip()

        # Save to session for consistency (optional)
        cf["summary"] = content
        cf["model"] = model
        session["current_feedback"] = cf

        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
                "name":           "John Doe (Silver)",
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

@app.route("/replay/<client_id>/<date>")
def replay(client_id, date):
    try:
        with open(f"saved_feedback/{client_id}_{date}.txt", "r") as f:
            feedback_text = f.read()
    except FileNotFoundError:
        return f"No saved feedback found for client {client_id} on {date}", 404

    parts = parse_parts(feedback_text)
    responses = {label: None for label in parts}

    return render_template(
        "client_feedback.html",
        client_id=client_id,
        client_name=f"Replay {client_id}",
        date=date,
        parts=parts,
        responses=responses
    )

@app.route("/replay_dashboard")
def replay_dashboard():
    folder = "saved_feedback"
    files = []

    if os.path.exists(folder):
        for fname in os.listdir(folder):
            if fname.endswith(".txt"):
                try:
                    client_id, date = fname.replace(".txt", "").split("_")
                    files.append({
                        "client_id": client_id,
                        "date": date,
                        "filename": fname
                    })
                except ValueError:
                    continue

    return render_template("replay_dashboard.html", files=sorted(files, key=lambda x: x['date'], reverse=True))

@app.route("/delete_feedback/<filename>", methods=["POST"])
def delete_feedback(filename):
    path = os.path.join("saved_feedback", filename)
    if os.path.exists(path):
        os.remove(path)
        return redirect(url_for("replay_dashboard"))
    return f"File {filename} not found", 404



# ————————————————————————————————————————————————————————————————
if __name__ == "__main__":
    app.run(debug=True)
