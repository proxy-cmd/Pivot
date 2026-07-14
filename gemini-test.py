import os

from google import genai

api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    raise SystemExit('Set GEMINI_API_KEY in the environment before running this check.')

client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model='gemini-3.5-flash',
    contents='Reply with only: Gemini API is working.',
)

print(response.text)
