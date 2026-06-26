from app.text_utils import normalize_for_voice


def test_normalize_for_voice_expands_dates_and_removes_dashes() -> None:
    text = "Fri, Jun 26, 2026, 9:00\u20139:30 AM \u2014 Dr. Patel"
    normalized = normalize_for_voice(text)
    assert "Friday" in normalized
    assert "June" in normalized
    assert "\u2014" not in normalized
    assert "\u2013" not in normalized
    assert "9:00 to 9:30" in normalized
