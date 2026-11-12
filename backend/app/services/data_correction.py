import re
from typing import Any


EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


def correct_email(value: Any) -> dict:
    """Classify an email and return a safe normalization or suggestion."""

    if value is None:
        return {
            "original_value": None,
            "corrected_value": None,
            "action": "human_review",
            "confidence": 0.0,
            "method": "missing_value",
            "message": "Email is missing.",
        }

    original = str(value)
    trimmed = original.strip()

    if not trimmed:
        return {
            "original_value": original,
            "corrected_value": None,
            "action": "human_review",
            "confidence": 0.0,
            "method": "empty_value",
            "message": "Email is empty.",
        }

    normalized = trimmed.lower()

    if re.search(r"\s", normalized):
        candidate = None

        if normalized.count("@") == 1:
            local_part, domain = normalized.split("@", 1)
            candidate = re.sub(r"\s+", ".", local_part) + "@" + domain

            if not EMAIL_PATTERN.fullmatch(candidate):
                candidate = None

        return {
            "original_value": original,
            "corrected_value": candidate,
            "action": "human_review",
            "confidence": 0.0,
            "method": "internal_whitespace_suggestion",
            "message": (
                "Internal whitespace detected. Verify the suggested "
                "address with the employee."
            ),
        }

    if not EMAIL_PATTERN.fullmatch(normalized):
        return {
            "original_value": original,
            "corrected_value": None,
            "action": "human_review",
            "confidence": 0.0,
            "method": "invalid_email_format",
            "message": "The email format is invalid.",
        }

    changed = normalized != original

    return {
        "original_value": original,
        "corrected_value": normalized,
        "action": "auto_correct" if changed else "no_change",
        "confidence": 1.0,
        "method": "trim_and_lowercase" if changed else "already_normalized",
        "message": (
            "Email safely normalized."
            if changed
            else "Email is already normalized."
        ),
    }


def classify_duplicate_email(value: str) -> dict:
    return {
        "original_value": value,
        "corrected_value": None,
        "action": "human_review",
        "confidence": 0.0,
        "method": "duplicate_email",
        "message": (
            "Duplicate email detected. Verify the correct address "
            "before changing it."
        ),
    }