
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing from your .env file.")

client = genai.Client(api_key=api_key)


def ask_llm(prompt: str) -> str:
    """Send a prompt to Gemini and return its text response."""
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
    )

    if not response.text:
        raise RuntimeError("Gemini returned no text.")

    return response.text

