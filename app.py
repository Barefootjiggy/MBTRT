from flask import Flask, render_template, request, redirect
from openai import OpenAI
import os
from dotenv import load_dotenv
from scraper import get_feedback
from billing_tracker import log_usage
from PIL import Image
import pytesseract
import json

load_dotenv()
client = OpenAI()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
CACHE_FILE = "response_cache.json"

def generate_response(feedback, model_name="gpt-3.5-turbo", section=None):
    if section:
        prompt = f"Only generate the tutor response for this specific section: {section}. Feedback: '{feedback}'"
    else:
        prompt = f"Respond professionally and empathetically to this client feedback: '{feedback}'"
    
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
        return f"[Mock Response] Feedback received. (Could not contact OpenAI API: {str(e)})"

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

# 👇 Landing Page Route
@app.route("/")
def landing():
    return render_template("landing.html")

# 👇 Feedback Generator
@app.route("/generate", methods=["GET", "POST"])
def generate():
    responses = []
    email = ""
    model_name = request.form.get("model", "gpt-3.5-turbo")
    cache_data = {}
    image_url = None

    if request.method == "POST":
        feedback_list = []
        mode = request.form.get("mode")

        if mode == "scrape":
            email = request.form.get("email")
            password = request.form.get("password")
            feedback_list = get_feedback(email, password)

        elif mode == "manual":
            manual_feedback = request.form.get("manual_feedback")
            if manual_feedback:
                feedback_list.append(manual_feedback)

            if "image" in request.files:
                image_file = request.files["image"]
                if image_file and image_file.filename != "":
                    img_path = os.path.join(app.config['UPLOAD_FOLDER'], image_file.filename)
                    image_file.save(img_path)
                    image = Image.open(img_path)
                    extracted_text = extract_text_from_image(image)
                    feedback_list.append(extracted_text)
                    image_url = os.path.join("static/uploads", image_file.filename)

        for feedback in feedback_list:
            parts = {
                "Part 1: How I Ate": feedback.split("PART 2")[0] if "PART 2" in feedback else feedback,
                "Part 2: My Movement": feedback.split("PART 2")[-1].split("PART 3")[0] if "PART 3" in feedback else "",
                "Part 3: How I Feel": feedback.split("PART 3")[-1].split("PART 4")[0] if "PART 4" in feedback else "",
                "Part 4: The New Me": feedback.split("PART 4")[-1] if "PART 4" in feedback else ""
            }

            generated_parts = {
                label: generate_response(content, model_name=model_name, section=label)
                for label, content in parts.items()
            }

            result = {
                "feedback": feedback,
                "summary": "Auto-generated summary coming soon...",
                "parts": parts,
                "generated_parts": generated_parts,
                "image_url": image_url
            }
            responses.append(result)

        cache_data["responses"] = responses
        save_cache(cache_data)

    else:
        cache_data = load_cache()
        responses = cache_data.get("responses", [])

    return render_template("index.html", responses=responses, email=email)

@app.route("/regenerate_part", methods=["POST"])
def regenerate_part():
    label = request.form["label"]
    index = int(request.form["index"])
    model_name = request.form.get("model", "gpt-3.5-turbo")

    cache_data = load_cache()

    if "responses" in cache_data and index < len(cache_data["responses"]):
        feedback = cache_data["responses"][index]["parts"].get(label, "")
        new_response = generate_response(feedback, model_name=model_name, section=label)
        cache_data["responses"][index]["generated_parts"][label] = new_response
        save_cache(cache_data)

    return redirect("/generate")

@app.route("/billing")
def billing():
    billing_data = {}
    if os.path.exists("billing_log.json"):
        with open("billing_log.json", "r") as f:
            billing_data = json.load(f)
    return render_template("billing.html", billing_data=billing_data)

if __name__ == "__main__":
    app.run(debug=True)
