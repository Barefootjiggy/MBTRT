from flask import Flask, render_template, request, redirect, session, url_for
from openai import OpenAI
from dotenv import load_dotenv
from scraper import get_dashboard_sections, get_client_feedback_by_id
from billing_tracker import log_usage
from PIL import Image
import pytesseract
import json
import os

load_dotenv()
client = OpenAI()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret")
CACHE_FILE = "response_cache.json"
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# ---------- Helper Functions ----------

def generate_response(feedback, model_name="gpt-3.5-turbo", section=None):
    prompt = f"Only generate the tutor response for this specific section: {section}. Feedback: '{feedback}'" if section else f"Respond professionally and empathetically to this client feedback: '{feedback}'"

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
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"[Error generating response: {str(e)}]"

def extract_text_from_image(image):
    return pytesseract.image_to_string(image)

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def parse_parts(text):
    return {
        "Part 1: How I Ate": text.split("PART 2")[0] if "PART 2" in text else text,
        "Part 2: My Movement": text.split("PART 2")[-1].split("PART 3")[0] if "PART 3" in text else "",
        "Part 3: How I Feel": text.split("PART 3")[-1].split("PART 4")[0] if "PART 4" in text else "",
        "Part 4: The New Me": text.split("PART 4")[-1] if "PART 4" in text else ""
    }

# ---------- Routes ----------

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/dashboard", methods=["POST", "GET"])
def dashboard():
    if request.method == "POST":
        session["email"] = request.form.get("email")
        session["password"] = request.form.get("password")

    email = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    sections = get_dashboard_sections(email, password)
    session["dashboard"] = sections  # Cache in session
    return render_template("dashboard.html", **sections)

@app.route("/generate/<client_id>/<date>/")
def generate(client_id, date):
    email = session.get("email")
    password = session.get("password")
    if not email or not password:
        return redirect("/")

    feedback_text = get_client_feedback_by_id(email, password, client_id, date)
    parts = parse_parts(feedback_text)
    model_name = "gpt-3.5-turbo"

    generated_parts = {
        label: generate_response(content, model_name=model_name, section=label)
        for label, content in parts.items()
    }

    # Save to cache
    session["current_feedback"] = {
        "client_id": client_id,
        "date": date,
        "parts": parts,
        "generated": generated_parts
    }

    return render_template("client_feedback.html", client_id=client_id, parts=parts, responses=generated_parts)

@app.route("/regenerate_section", methods=["POST"])
def regenerate_section():
    label = request.form.get("label")
    model_name = request.form.get("model", "gpt-3.5-turbo")

    feedback_data = session.get("current_feedback", {})
    parts = feedback_data.get("parts", {})
    generated = feedback_data.get("generated", {})

    if label in parts:
        new_response = generate_response(parts[label], model_name=model_name, section=label)
        generated[label] = new_response
        session["current_feedback"]["generated"] = generated

    return redirect(url_for('generate', client_id=feedback_data.get("client_id"), date=feedback_data.get("date")))

@app.route("/billing")
def billing():
    billing_data = {}
    if os.path.exists("billing_log.json"):
        with open("billing_log.json", "r") as f:
            billing_data = json.load(f)
    return render_template("billing.html", billing_data=billing_data)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
