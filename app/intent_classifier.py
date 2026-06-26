from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.models import IntentClassification, IntentEntities
from app.sample_data import SPECIALTIES


SPECIALTY_ALIASES = {
    "primary care": "Primary care",
    "primary": "Primary care",
    "pcp": "Primary care",
    "family medicine": "Primary care",
    "general doctor": "Primary care",
    "general physician": "Primary care",
    "cardiology": "Cardiology",
    "cardiologist": "Cardiology",
    "heart doctor": "Cardiology",
    "heart specialist": "Cardiology",
    "dermatology": "Dermatology",
    "dermatologist": "Dermatology",
    "dermitalogist": "Dermatology",
    "derm": "Dermatology",
    "skin doctor": "Dermatology",
    "skin specialist": "Dermatology",
    "pediatrics": "Pediatrics",
    "pediatrician": "Pediatrics",
    "kid doctor": "Pediatrics",
    "child doctor": "Pediatrics",
    "children doctor": "Pediatrics",
    "physical therapy": "Physical therapy",
    "physical therapist": "Physical therapy",
    "physio": "Physical therapy",
    "pt": "Physical therapy",
}

SPECIALTY_CANDIDATES = tuple((candidate.lower(), label) for candidate, label in SPECIALTY_ALIASES.items())
SPECIALTY_CANONICALS = tuple((specialty.lower(), specialty) for specialty in SPECIALTIES)
FUZZY_SPECIALTY_TERMS = tuple(
    sorted(
        {
            *SPECIALTY_CANDIDATES,
            *SPECIALTY_CANONICALS,
        },
        key=lambda item: len(item[0]),
        reverse=True,
    )
)

EMERGENCY_PATTERNS = [
    r"\b(chest pain|chest hurts|severe chest pain)\b",
    r"\b(trouble breathing|can't breathe|cannot breathe|shortness of breath)\b",
    r"\b(severe bleeding|bleeding heavily)\b",
    r"\b(stroke|face drooping|slurred speech)\b",
    r"\b(suicidal|suicide|kill myself|self harm)\b",
    r"\b(excruciating pain|unbearable pain|worst pain)\b",
    r"\b(had a fall|took a fall|bad fall|serious fall|fell|fallen)\b",
    r"\b(serious injury|head injury|hit my head)\b",
    r"\b(accident|car accident|car crash|crash|collision)\b",
]

SYMPTOM_SPECIALTIES = {
    "rash": "Dermatology",
    "mole": "Dermatology",
    "skin": "Dermatology",
    "fever": "Pediatrics",
    "kid has": "Pediatrics",
    "child has": "Pediatrics",
    "back pain": "Primary care",
    "hand pain": "Primary care",
    "knee pain": "Primary care",
}


def classify_intent(text: str) -> IntentClassification:
    """Classify the latest user utterance before the LLM decides the next response."""
    original = text or ""
    lowered = _normalize(original)
    entities = IntentEntities(
        specialty=_extract_specialty(lowered),
        provider=_extract_provider(original),
        date_phrase=_extract_date_phrase(original),
        patient_is_caller=_extract_patient_is_caller(lowered),
    )

    if not lowered or lowered in {"noise", "silence", "um", "uh"}:
        return _result("unclear", "low", entities, None)

    if _matches_any(lowered, EMERGENCY_PATTERNS):
        return _result("emergency", "high", entities, None)

    if _has_crosstalk(lowered):
        return _result("unclear", "low", entities, "multiple speakers or crosstalk.")

    if _is_medical_advice(lowered):
        return _result("question", "medium", entities, "medical_advice, redirect, do not advise.")

    if _is_out_of_scope(lowered):
        return _result("out_of_scope", "high", entities, None)

    if _is_general_question(lowered):
        return _result("question", "high", entities, None)

    if _is_reschedule(lowered):
        confidence = "medium" if "change my appointment" in lowered else "high"
        flag = "confirm whether reschedule or cancel." if "change my appointment" in lowered else None
        if re.search(r"\bcancel\b.*\b(move|reschedule|instead|book)\b", lowered):
            confidence = "low"
            flag = "caller mid-correction."
        return _result("reschedule", confidence, entities, flag)

    if _is_cancel(lowered):
        return _result("cancel", "high", entities, None)

    if _is_lookup(lowered):
        return _result("confirm_lookup", "high", entities, None)

    symptom_specialty = _symptom_specialty(lowered)
    if symptom_specialty and not entities.specialty:
        entities.specialty = symptom_specialty
        return _result("book", "medium", entities, None)

    if _is_booking(lowered, entities):
        confidence = "low" if _looks_cut_off(lowered) else "high"
        return _result("book", confidence, entities, None)

    if _is_vague(lowered):
        return _result("unclear", "low", entities, None)

    return _result("unclear", "low", entities, "intent not recognized.")


def _result(
    intent: str,
    confidence: str,
    entities: IntentEntities,
    ambiguity_flag: str | None,
) -> IntentClassification:
    """Create a typed classifier result with controlled literal values."""
    return IntentClassification(
        intent=intent,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        entities=entities,
        ambiguity_flag=ambiguity_flag,
    )


def _normalize(value: str) -> str:
    """Lowercase and collapse whitespace for regex-based matching."""
    return " ".join(value.strip().lower().split())


def _matches_any(text: str, patterns: list[str]) -> bool:
    """Return true when any regex pattern matches the normalized text."""
    return any(re.search(pattern, text) for pattern in patterns)


def _extract_specialty(text: str) -> str | None:
    """Extract a canonical specialty using aliases first and bounded fuzzy matching second."""
    for alias, specialty in SPECIALTY_CANDIDATES:
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return specialty
    for specialty_text, specialty in SPECIALTY_CANONICALS:
        if re.search(rf"\b{re.escape(specialty_text)}\b", text):
            return specialty

    if len(text) > 80:
        return None

    best_specialty: str | None = None
    best_score = 0.0
    words = re.findall(r"[a-z]+", text)
    spans = words + [" ".join(words[index : index + 2]) for index in range(max(len(words) - 1, 0))]
    for span in spans[:30]:
        if len(span) < 3:
            continue
        for candidate, specialty in FUZZY_SPECIALTY_TERMS:
            if abs(len(span) - len(candidate)) > 5:
                continue
            score = SequenceMatcher(None, span, candidate.lower()).ratio()
            if score > best_score:
                best_score = score
                best_specialty = specialty
            if best_score >= 0.92:
                return best_specialty
    return best_specialty if best_score >= 0.78 else None


def _extract_provider(text: str) -> str | None:
    """Extract simple provider mentions such as Dr. Patel or with Naomi Chen."""
    match = re.search(r"\bDr\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    if match:
        return f"Dr. {match.group(1)}"
    match = re.search(r"\bwith\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    if match:
        return match.group(1)
    return None


def _extract_date_phrase(text: str) -> str | None:
    """Pull out the raw date or time phrase for downstream slot search."""
    patterns = [
        r"\b(today|tomorrow|tonight)\b",
        r"\bnext\s+(week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(morning|afternoon|evening)\b",
        r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def _extract_patient_is_caller(text: str) -> bool | None:
    """Infer whether the caller appears to be booking for self or someone else."""
    if re.search(r"\b(my daughter|my son|my mother|my father|my mom|my dad|my wife|my husband|for someone else)\b", text):
        return False
    if re.search(r"\b(i need|i want|i would like|book me|schedule me|my appointment)\b", text):
        return True
    return None


def _has_crosstalk(text: str) -> bool:
    """Detect obvious transcription hints that multiple speakers were present."""
    return "people talking" in text or "multiple speakers" in text or "crosstalk" in text


def _is_medical_advice(text: str) -> bool:
    """Detect medical-advice questions that the assistant must not answer."""
    return bool(re.search(r"\b(should i be worried|is this normal|what does this mean|do i need treatment)\b", text))


def _is_out_of_scope(text: str) -> bool:
    """Detect requests outside scheduling, cancellation, rescheduling, or lookup."""
    return bool(re.search(r"\b(prescription refill|refill|lab result|test result|billing|bill|invoice)\b", text))


def _is_general_question(text: str) -> bool:
    """Detect operational questions that should not start a booking flow."""
    return bool(re.search(r"\b(hours|located|location|address|take blue cross|insurance|how much|cost|price)\b", text))


def _is_reschedule(text: str) -> bool:
    """Detect rescheduling, including cancel-and-book phrasing."""
    if re.search(r"\bcancel\b.*\b(book|move|reschedule|instead)\b", text):
        return True
    return bool(re.search(r"\b(reschedule|move my appointment|move it|change my appointment|change the appointment)\b", text))


def _is_cancel(text: str) -> bool:
    """Detect cancellation intent."""
    return bool(re.search(r"\b(cancel|call off)\b", text))


def _is_lookup(text: str) -> bool:
    """Detect existing-appointment lookup or confirmation intent."""
    return bool(
        re.search(
            r"\b(do i have|when is my appointment|what time is my appointment|confirm my appointment|appointment details|lookup my appointment)\b",
            text,
        )
    )


def _symptom_specialty(text: str) -> str | None:
    """Infer a routing specialty from nonurgent symptom phrases."""
    for phrase, specialty in SYMPTOM_SPECIALTIES.items():
        if phrase in text:
            return specialty
    return None


def _is_booking(text: str, entities: IntentEntities) -> bool:
    """Detect direct and implicit booking intent."""
    if re.search(r"\b(book|schedule|appointment|see a|see an|come in|get in)\b", text):
        return True
    if re.search(r"\b(do you have anything|anything available|availability|available time)\b", text):
        return True
    if entities.provider and re.search(r"\b(anything|available|next|this week|appointment)\b", text):
        return True
    return False


def _looks_cut_off(text: str) -> bool:
    """Mark partial or garbled booking phrases as lower confidence."""
    return text.endswith("...") or text.endswith(" a") or "[cut off]" in text or "garbled" in text


def _is_vague(text: str) -> bool:
    """Detect vague openers that should receive a clarification question."""
    cleaned = text.strip(" .?!")
    return cleaned in {
        "i need help",
        "i need some help",
        "help",
        "i have a question",
        "i have a question about my health",
    }
