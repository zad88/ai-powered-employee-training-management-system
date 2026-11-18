import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm() -> ChatOpenAI:
    """Create and return the configured OpenAI chat model."""
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing from your .env file.")

    model = os.getenv("OPENAI_MODEL", "gpt-5.4")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=0,
    )


def ask_llm(prompt: str) -> str:
    """Send a prompt to OpenAI and return its text response."""
    response = get_llm().invoke(prompt)

    if not response.content:
        raise RuntimeError("OpenAI returned no text.")

    if isinstance(response.content, str):
        return response.content

    return str(response.content)
