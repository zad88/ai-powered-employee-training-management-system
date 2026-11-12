from backend.app.services.data_correction import (
    correct_email,
    classify_duplicate_email,
)


def test_email_whitespace_is_normalized():
    result = correct_email("  USER@EXAMPLE.COM  ")

    assert result["corrected_value"] == "user@example.com"
    assert result["action"] == "auto_correct"
    assert result["confidence"] == 1.0


def test_already_normalized_email_is_unchanged():
    result = correct_email("user@example.com")

    assert result["corrected_value"] == "user@example.com"
    assert result["action"] == "no_change"


def test_internal_spaces_require_review():
    result = correct_email("user name@example.com")

    assert result["action"] == "human_review"
    assert result["method"] == "internal_whitespace_suggestion"
    assert result["corrected_value"] == "user.name@example.com"


def test_missing_email_requires_review():
    result = correct_email(None)

    assert result["action"] == "human_review"
    assert result["corrected_value"] is None


def test_invalid_email_requires_review():
    result = correct_email("not-an-email")

    assert result["action"] == "human_review"
    assert result["corrected_value"] is None


def test_duplicate_email_requires_review():
    result = classify_duplicate_email("user@example.com")

    assert result["action"] == "human_review"
    assert result["corrected_value"] is None