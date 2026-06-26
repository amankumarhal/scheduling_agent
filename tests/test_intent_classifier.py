from app.intent_classifier import classify_intent


def assert_intent(text: str, intent: str, confidence: str | None = None) -> None:
    result = classify_intent(text)
    assert result.intent == intent
    if confidence:
        assert result.confidence == confidence


def test_implicit_booking_without_book_verb() -> None:
    result = classify_intent("I need to see a dermatologist.")
    assert result.intent == "book"
    assert result.entities.specialty == "Dermatology"


def test_slot_question_is_booking() -> None:
    result = classify_intent("Does Dr. Patel have anything next week?")
    assert result.intent == "book"
    assert result.entities.provider == "Dr. Patel"
    assert result.entities.date_phrase == "next week"


def test_nonurgent_symptom_routes_to_booking_with_specialty() -> None:
    result = classify_intent("I have a rash.")
    assert result.intent == "book"
    assert result.confidence == "medium"
    assert result.entities.specialty == "Dermatology"


def test_possible_emergency_overrides_booking() -> None:
    assert_intent("I have chest pain and need an appointment.", "emergency", "high")


def test_booking_for_someone_else() -> None:
    result = classify_intent("I want to book for my daughter.")
    assert result.intent == "book"
    assert result.entities.patient_is_caller is False


def test_cancel_plus_book_is_reschedule() -> None:
    result = classify_intent("Cancel Tuesday and book me for Thursday instead.")
    assert result.intent == "reschedule"
    assert result.ambiguity_flag == "caller mid-correction."


def test_existing_appointment_reference_is_reschedule() -> None:
    result = classify_intent("I need to move my appointment with Dr. Lee.")
    assert result.intent == "reschedule"


def test_lookup_is_not_booking() -> None:
    assert_intent("When is my appointment?", "confirm_lookup", "high")


def test_general_question_is_not_booking() -> None:
    assert_intent("What are your hours?", "question", "high")


def test_out_of_scope_request() -> None:
    assert_intent("I need a prescription refill.", "out_of_scope", "high")


def test_medical_advice_question_is_flagged() -> None:
    result = classify_intent("Should I be worried about this mole?")
    assert result.intent == "question"
    assert result.ambiguity_flag == "medical_advice, redirect, do not advise."


def test_vague_opener_is_unclear() -> None:
    assert_intent("I need some help.", "unclear", "low")


def test_ambiguous_change_is_reschedule_with_flag() -> None:
    result = classify_intent("I want to change my appointment.")
    assert result.intent == "reschedule"
    assert result.confidence == "medium"
    assert result.ambiguity_flag == "confirm whether reschedule or cancel."


def test_cut_off_booking_is_low_confidence() -> None:
    result = classify_intent("I wanna book a...")
    assert result.intent == "book"
    assert result.confidence == "low"


def test_empty_input_is_unclear() -> None:
    assert_intent("", "unclear", "low")
