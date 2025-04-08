import openai
from dotenv import load_dotenv
import os

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_response(feedback):
    prompt = f"Respond professionally and empathetically to this client feedback: '{feedback}'"

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a supportive and experienced fitness coach."},
            {"role": "user", "content": prompt}
        ]
    )
    return response["choices"][0]["message"]["content"]
