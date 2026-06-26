from app.models import PatientInfo
from app.scheduling_tools import SchedulingTools
from app.store import InMemoryAppointmentStore


def make_tools() -> SchedulingTools:
    return SchedulingTools(InMemoryAppointmentStore())


def patient() -> dict:
    return PatientInfo(
        patient_name="Sample Patient",
        date_of_birth="1990-01-01",
        phone_number="555-0100",
    ).model_dump()


def test_search_returns_available_slots() -> None:
    tools = make_tools()
    result = tools.search_available_slots("Cardiology")
    assert result.success is True
    assert result.slots
    assert all(slot.is_available and not slot.is_booked for slot in result.slots)


def test_search_filters_by_specialty() -> None:
    tools = make_tools()
    result = tools.search_available_slots("Dermatology")
    assert result.success is True
    assert result.slots
    assert all(slot.specialty == "Dermatology" for slot in result.slots)


def test_search_filters_by_provider_if_provided() -> None:
    tools = make_tools()
    result = tools.search_available_slots("Cardiology", provider_name="Rivera")
    assert result.success is True
    assert result.slots
    assert all("Rivera" in slot.provider_name for slot in result.slots)


def test_booking_requires_explicit_confirmation() -> None:
    tools = make_tools()
    result = tools.book_appointment("slot_card_1", patient(), "Follow-up", False)
    assert result.success is False
    assert "Explicit confirmation" in result.message


def test_booking_requires_patient_name() -> None:
    tools = make_tools()
    bad_patient = patient()
    bad_patient["patient_name"] = ""
    result = tools.book_appointment("slot_card_1", bad_patient, "Follow-up", True)
    assert result.success is False
    assert "patient_name" in result.message


def test_booking_requires_date_of_birth() -> None:
    tools = make_tools()
    bad_patient = patient()
    bad_patient["date_of_birth"] = ""
    result = tools.book_appointment("slot_card_1", bad_patient, "Follow-up", True)
    assert result.success is False
    assert "date_of_birth" in result.message


def test_booking_requires_phone_number() -> None:
    tools = make_tools()
    bad_patient = patient()
    bad_patient["phone_number"] = ""
    result = tools.book_appointment("slot_card_1", bad_patient, "Follow-up", True)
    assert result.success is False
    assert "phone_number" in result.message


def test_booking_requires_appointment_reason() -> None:
    tools = make_tools()
    result = tools.book_appointment("slot_card_1", patient(), "", True)
    assert result.success is False
    assert "appointment_reason" in result.message or "Appointment reason" in result.message


def test_booking_changes_slot_status() -> None:
    tools = make_tools()
    result = tools.book_appointment("slot_card_1", patient(), "Follow-up", True)
    assert result.success is True
    slot = tools.store.get_slot("slot_card_1")
    assert slot is not None
    assert slot.is_booked is True
    assert slot.is_available is False


def test_cannot_double_book_same_slot() -> None:
    tools = make_tools()
    first = tools.book_appointment("slot_card_1", patient(), "Follow-up", True)
    second = tools.book_appointment("slot_card_1", patient(), "Follow-up", True)
    assert first.success is True
    assert second.success is False
    assert "already booked" in second.message


def test_cancel_requires_explicit_confirmation() -> None:
    tools = make_tools()
    booking = tools.book_appointment("slot_card_1", patient(), "Follow-up", True).booking
    assert booking is not None
    result = tools.cancel_appointment(booking.booking_id, explicit_confirmation=False)
    assert result.success is False
    assert "Explicit confirmation" in result.message


def test_cancel_marks_appointment_canceled() -> None:
    tools = make_tools()
    booking = tools.book_appointment("slot_card_1", patient(), "Follow-up", True).booking
    assert booking is not None
    result = tools.cancel_appointment(booking.booking_id, explicit_confirmation=True)
    assert result.success is True
    assert result.booking is not None
    assert result.booking.status == "canceled"
    slot = tools.store.get_slot("slot_card_1")
    assert slot is not None
    assert slot.is_available is True


def test_reschedule_requires_explicit_confirmation() -> None:
    tools = make_tools()
    booking = tools.book_appointment("slot_card_1", patient(), "Follow-up", True).booking
    assert booking is not None
    result = tools.reschedule_appointment(booking.booking_id, "slot_card_2", explicit_confirmation=False)
    assert result.success is False
    assert "Explicit confirmation" in result.message


def test_reschedule_moves_booking_to_new_slot() -> None:
    tools = make_tools()
    booking = tools.book_appointment("slot_card_1", patient(), "Follow-up", True).booking
    assert booking is not None
    result = tools.reschedule_appointment(booking.booking_id, "slot_card_2", explicit_confirmation=True)
    assert result.success is True
    assert result.booking is not None
    assert result.booking.slot_id == "slot_card_2"
    old_slot = tools.store.get_slot("slot_card_1")
    new_slot = tools.store.get_slot("slot_card_2")
    assert old_slot is not None and old_slot.is_available is True
    assert new_slot is not None and new_slot.is_booked is True
