import os
import requests

# Ensure the OPENAI_API_KEY is set in your environment
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("Error: OPENAI_API_KEY is not set in the environment.")
    exit(1)

# Test the OpenAI API by listing available models
url = "https://api.openai.com/v1/models"
headers = {
    "Authorization": f"Bearer {api_key}"
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()  # Raise an error for HTTP errors
    models = response.json()
    print("Success! Available models:")
    for model in models.get("data", []):
        print(f"- {model['id']}")
except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e}")
except requests.exceptions.RequestException as e:
    print(f"Request Error: {e}")
except Exception as e:
    print(f"Unexpected Error: {e}")
