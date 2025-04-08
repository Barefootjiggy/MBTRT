from flask import Flask, render_template, request
import openai
import os
from dotenv import load_dotenv
from scraper import get_feedback
from PIL import Image
import pytesseract

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

def generate_response(feedback):
    prompt = f"Respond professionally and empathetically to this client feedback: '{feedback}'"
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a supportive and empathetic fitness coach."},
            {"role": "user", "content": prompt}
        ]
    )
    return response["choices"][0]["message"]["content"].strip()

def extract_text_from_image(image):
    return pytesseract.image_to_string(image)

@app.route("/", methods=["GET", "POST"])
def home():
    responses = []
    email = ""
    mode = request.form.get("mode")

    if request.method == "POST":
        if mode == "scrape":
            email = request.form.get("email")
            password = request.form.get("password")
            feedback_list = get_feedback(email, password)
        elif mode == "manual":
            feedback_list = []

            # Text area input
            manual_feedback = request.form.get("manual_feedback")
            if manual_feedback:
                feedback_list.append(manual_feedback)

            # Image input
            if "image" in request.files:
                image_file = request.files["image"]
                if image_file.filename != "":
                    img_path = os.path.join(app.config['UPLOAD_FOLDER'], image_file.filename)
                    image_file.save(img_path)
                    image = Image.open(img_path)
                    extracted_text = extract_text_from_image(image)
                    feedback_list.append(extracted_text)

        for feedback in feedback_list:
            ai_response = generate_response(feedback)
            responses.append({"feedback": feedback, "response": ai_response})

    return render_template("index.html", responses=responses, email=email)
