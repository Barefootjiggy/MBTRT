import json
import os
from datetime import datetime

BILLING_FILE = "billing_log.json"

def log_usage(model, input_tokens, output_tokens):
    today = datetime.now().strftime("%Y-%m-%d")

    if os.path.exists(BILLING_FILE):
        with open(BILLING_FILE, "r") as f:
            data = json.load(f)
    else:
        data = {}

    # Ensure today's entry exists
    if today not in data:
        data[today] = {
            "gpt-3.5-turbo": {"input": 0, "output": 0},
            "gpt-4": {"input": 0, "output": 0}
        }

    # Initialize the model's token structure if missing
    if model not in data[today]:
        data[today][model] = {"input": 0, "output": 0}

    # Accumulate tokens
    data[today][model]["input"] += input_tokens
    data[today][model]["output"] += output_tokens

    with open(BILLING_FILE, "w") as f:
        json.dump(data, f, indent=2)
