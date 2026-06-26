from __future__ import annotations

import re

WEEKDAY_NAMES = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Tues": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Thur": "Thursday",
    "Thurs": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday",
}

MONTH_NAMES = {
    "Jan": "January",
    "Feb": "February",
    "Mar": "March",
    "Apr": "April",
    "Jun": "June",
    "Jul": "July",
    "Aug": "August",
    "Sep": "September",
    "Sept": "September",
    "Oct": "October",
    "Nov": "November",
    "Dec": "December",
}


def normalize_for_voice(text: str) -> str:
    """Make model output friendlier for TTS and product consistency."""
    normalized = text.replace("\u2014", ", ")
    normalized = normalized.replace("\u2013", " to ")
    normalized = normalized.replace("“", '"').replace("”", '"')

    for short, full in {**WEEKDAY_NAMES, **MONTH_NAMES}.items():
        normalized = re.sub(rf"\b{re.escape(short)}\b\.?", full, normalized)

    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\s+([,.;:])", r"\1", normalized)
    normalized = re.sub(r",\s*,", ",", normalized)
    return normalized.strip()
