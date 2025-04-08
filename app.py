from flask import Flask, render_template, request
from openai import OpenAI
import os
from dotenv import load_dotenv
from scraper import get_feedback
from billing_tracker import log_usage
from PIL import Image
import pytesseract
import json

# Load environment variables
load_dotenv()
client = OpenAI()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

def generate_response(feedback, model_name="gpt-3.5-turbo"):
    prompt = f"Respond professionally and empathetically to this client feedback: '{feedback}'"
    try:
        chat_completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a supportive and empathetic fitness coach."},
                {"role": "user", "content": prompt}
            ]
        )
        # Token logging
        usage = chat_completion.usage
        log_usage(model_name, usage.prompt_tokens, usage.completion_tokens)

        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"[Mock Response] Feedback received. (Could not contact OpenAI API: {str(e)})"

def extract_text_from_image(image):
    return pytesseract.image_to_string(image)

@app.route("/", methods=["GET", "POST"])
def home():
    responses = []
    email = ""
    mode = request.form.get("mode")
    model_name = request.form.get("model", "gpt-3.5-turbo")

    if request.method == "POST":
        feedback_list = []

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

        for feedback in feedback_list:
            ai_response = generate_response(feedback, model_name)
            responses.append({"feedback": feedback, "response": ai_response})

    return render_template("index.html", responses=responses, email=email)

@app.route("/billing")
def billing():
    billing_data = {}
    if os.path.exists("billing_log.json"):
        with open("billing_log.json", "r") as f:
            billing_data = json.load(f)
    return render_template("billing.html", billing_data=billing_data)

if __name__ == "__main__":
    app.run(debug=True)
