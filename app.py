import os
import time
import json
from flask import Flask, render_template, request, redirect, session, url_for
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

# approximate prices per token
MODEL_RATES = {
    "gpt-3.5-turbo": 0.002 / 1000,   # $0.002 per 1k tokens
    "gpt-4":         0.03  / 1000    # $0.03 per 1k tokens
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
                {"role": "user",   "content": prompt}
            ]
        )
        usage = chat_completion.usage
        # log for billing dashboard, etc.
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
        session["email"]    = request.form["email"]
        session["password"] = request.form["password"]

    email    = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    now       = time.time()
    last      = session.get("last_fetch_time", 0)
    data      = session.get("dashboard", {})

    # refresh every 10m or on manual ?refresh
    if now - last > 600 or not data or request.args.get("refresh"):
        print("🔄 Refreshing dashboard data...")
        data = get_dashboard_sections(email, password)
        session["dashboard"]        = data
        session["last_fetch_time"]  = now
    else:
        print("✅ Using cached dashboard data")

    return render_template("dashboard.html", **data)

@app.route("/generate/<client_id>/<date>", methods=["GET", "POST"])
@app.route("/generate/<client_id>/<date>/", methods=["GET", "POST"])
def generate(client_id, date):
    email    = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    # pick up model from form or default
    model_name = request.values.get("model", "gpt-3.5-turbo")

    feedback_text = get_client_feedback_by_id(email, password, client_id, date)

    # simple PART-based splitter
    def parse_parts(text):
        parts   = {}
        markers = ["PART 1", "PART 2", "PART 3", "PART 4"]
        chunks  = text
        for i, marker in enumerate(markers):
            if marker in chunks:
                before, chunks = chunks.split(marker, 1)
                label = (
                    "Part 1: How I Ate"
                    if i == 0
                    else f"Part {i}:"
                )
                parts[label] = before.strip()
        parts["Part 4: The New Me"] = chunks.strip()
        return parts

    parts      = parse_parts(feedback_text)
    total_cost = 0.0
    usage_list = []
    generated  = {}

    for label, content in parts.items():
        if not content:
            generated[label] = "[No content submitted]"
            continue

        resp = generate_response(content, model_name=model_name, section=label)
        generated[label] = resp["content"]

        if resp["usage"]:
            p     = resp["usage"].prompt_tokens
            c     = resp["usage"].completion_tokens
            rate  = MODEL_RATES.get(model_name, MODEL_RATES["gpt-3.5-turbo"])
            cost  = (p + c) * rate
            total_cost += cost
            usage_list.append({
                "label":             label,
                "prompt_tokens":     p,
                "completion_tokens": c,
                "cost":              cost
            })

    # stash for potential section‐only regenerate
    session["current_feedback"] = {
        "client_id":   client_id,
        "date":        date,
        "parts":       parts,
        "generated":   generated,
        "model":       model_name,
        "usage":       usage_list,
        "total_cost":  total_cost
    }

    return render_template(
        "client_feedback.html",
        client_id=     client_id,
        date=          date,
        parts=         parts,
        responses=     generated,
        model_selected=model_name,
        usage=         usage_list,
        total_cost=    total_cost
    )

@app.route("/regenerate_section", methods=["POST"])
def regenerate_section():
    data       = session.get("current_feedback", {})
    label      = request.form.get("label")
    model_name = data.get("model", "gpt-3.5-turbo")
    parts      = data.get("parts", {})
    gen        = data.get("generated", {})
    total_cost = 0.0
    usage_list = []

    if label in parts:
        resp = generate_response(parts[label], model_name=model_name, section=label)
        gen[label] = resp["content"]
        if resp["usage"]:
            p    = resp["usage"].prompt_tokens
            c    = resp["usage"].completion_tokens
            rate = MODEL_RATES.get(model_name)
            cost = (p + c) * rate
            usage_list.append({
                "label":             label,
                "prompt_tokens":     p,
                "completion_tokens": c,
                "cost":              cost
            })
            total_cost += cost

    # merge back in—(you could decide to recalc full list here)
    session["current_feedback"].update({
        "generated":  gen,
        "usage":      usage_list,
        "total_cost": total_cost
    })

    return redirect(url_for("generate",
                            client_id=data.get("client_id"),
                            date=data.get("date")))

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
