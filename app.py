from flask import Flask, render_template, request
import openai
import os
from dotenv import load_dotenv
from scraper import get_feedback  # Import scraper

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

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

@app.route("/", methods=["GET", "POST"])
def home():
    responses = []
    email = ""
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        feedback_list = get_feedback(email, password)

        for feedback in feedback_list:
            ai_response = generate_response(feedback)
            responses.append({"feedback": feedback, "response": ai_response})

    return render_template("index.html", responses=responses, email=email)

if __name__ == "__main__":
    app.run(debug=True)
