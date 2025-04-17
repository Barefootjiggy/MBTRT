import os
import time
import json
from flask import Flask, render_template, request, redirect, session, url_for, flash
from openai import OpenAI
from dotenv import load_dotenv
from billing_tracker import log_usage
from scraper import get_dashboard_sections, get_client_feedback_by_id

load_dotenv()
client = OpenAI()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret")
CACHE_FILE = "response_cache.json"
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# approximate prices per 1k tokens
MODEL_RATES = {
    "gpt-3.5-turbo": 0.002 / 1000,   # $0.002 per 1k tokens
    "gpt-4": 0.03 / 1000            # $0.03 per 1k tokens (example)
}

def generate_response(feedback, model_name="gpt-3.5-turbo", section=None):
    """Return both the generated text and the usage object."""
    prompt = (
        f"Only generate the tutor response for this specific section: {section}. Feedback: '{feedback}'"
        if section
        else f"Respond professionally and empathetically to this client feedback: '{feedback}'"
    )
    try:
        chat_completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a supportive and empathetic fitness coach."},
                {"role": "user", "content": prompt}
            ]
        )
        usage = chat_completion.usage
        log_usage(model_name, usage.prompt_tokens, usage.completion_tokens)
        content = chat_completion.choices[0].message.content.strip()
        return {"content": content, "usage": usage}
    except Exception as e:
        return {"content": f"[Error generating response: {e}]", "usage": None}

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if request.method == "POST":
        session["email"] = request.form["email"]
        session["password"] = request.form["password"]

    email = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    now = time.time()
    last = session.get("last_fetch_time", 0)
    data = session.get("dashboard", {})

    if now - last > 600 or not data or request.args.get("refresh"):
        print("🔄 Refreshing dashboard data...")
        data = get_dashboard_sections(email, password)
        session["dashboard"] = data
        session["last_fetch_time"] = now
    else:
        print("✅ Using cached dashboard data")

    return render_template("dashboard.html", **data)

@app.route("/generate/<client_id>/<date>", methods=["GET", "POST"])
@app.route("/generate/<client_id>/<date>/", methods=["GET", "POST"])
def generate(client_id, date):
    email = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    # chosen model via form
    model_name = request.values.get("model", "gpt-3.5-turbo")

    feedback_text = get_client_feedback_by_id(email, password, client_id, date)
    # split into parts
    def parse_parts(text):
        parts = {}
        markers = ["PART 1", "PART 2", "PART 3", "PART 4"]
        chunks = text
        # naive split based on markers
        for i, marker in enumerate(markers):
            if marker in chunks:
                before, chunks = chunks.split(marker, 1)
                if i == 0:
                    parts["Part 1: How I Ate"] = before.strip()
                else:
                    parts[f"Part {i}:"] = before.strip()
        parts["Part 4: The New Me"] = chunks.strip()
        return parts

    parts = parse_parts(feedback_text)

    total_cost = 0.0
    generated = {}

    for label, content in parts.items():
        if not content:
            generated[label] = "[No content submitted]"
            continue
        resp = generate_response(content, model_name=model_name, section=label)
        generated[label] = resp["content"]
        if resp["usage"]:
            tokens = resp["usage"].prompt_tokens + resp["usage"].completion_tokens
            rate = MODEL_RATES.get(model_name, MODEL_RATES["gpt-3.5-turbo"])
            total_cost += tokens * rate

    # store in session for possible regenerate
    session["current_feedback"] = {
        "client_id": client_id,
        "date": date,
        "parts": parts,
        "generated": generated,
        "model": model_name,
        "total_cost": total_cost
    }

    return render_template(
        "client_feedback.html",
        client_id=client_id,
        date=date,
        parts=parts,
        responses=generated,
        model_selected=model_name,
        total_cost=total_cost
    )

@app.route("/regenerate_section", methods=["POST"])
def regenerate_section():
    data = session.get("current_feedback", {})
    label = request.form["label"]
    model_name = data.get("model", "gpt-3.5-turbo")
    parts = data.get("parts", {})
    gen = data.get("generated", {})
    total = 0.0

    if label in parts:
        resp = generate_response(parts[label], model_name=model_name, section=label)
        gen[label] = resp["content"]

    # recompute cost for all
    for lbl, content in parts.items():
        # assume all resp have usage saved? skip cost if none
        # For simplicity you could re-run cost calc; omitted here
        pass

    session["current_feedback"]["generated"] = gen
    session["current_feedback"]["total_cost"] = total

    return redirect(url_for("generate", client_id=data.get("client_id"), date=data.get("date")))

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
