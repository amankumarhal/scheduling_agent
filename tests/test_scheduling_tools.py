import json

from app.models import PatientInfo
from app.scheduling_tools import SchedulingTools
from app.store import InMemoryAppointmentStore, JsonAppointmentStore


def make_tools() -> SchedulingTools:
    return SchedulingTools(InMemoryAppointmentStore())


def patient() -> dict:
    return PatientInfo(
        patient_name="Sample Patient",
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


def test_search_understands_tomorrow() -> None:
    tools = make_tools()
    result = tools.search_available_slots("Primary care", preferred_date="tomorrow")
    assert result.success is True
    assert result.slots
    assert result.slots[0].provider_name == "Dr. Maya Patel"
    assert result.slot_options
    assert result.slot_options[0].appointment_time.startswith(result.slots[0].start_time.strftime("%A"))


def test_search_returns_alternatives_when_preferred_time_has_no_match() -> None:
    tools = make_tools()
    result = tools.search_available_slots("Primary care", preferred_time_window="evening")
    assert result.success is True
    assert result.slots
    assert "soonest available alternatives" in result.message
    assert all(slot.specialty == "Primary care" for slot in result.slots)
    assert len(result.slot_options) == len(result.slots)


def test_provider_search_returns_alternatives_when_preferred_time_has_no_match() -> None:
    tools = make_tools()
    result = tools.search_provider_slots("Maya Patel", preferred_time_window="evening")
    assert result.success is True
    assert result.slots
    assert "soonest available alternatives" in result.message
    assert all(slot.provider_name == "Dr. Maya Patel" for slot in result.slots)
    assert len(result.slot_options) == len(result.slots)


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


def test_booking_uses_minimal_patient_fields() -> None:
    tools = make_tools()
    result = tools.book_appointment("slot_card_1", patient(), "Follow-up", True)
    assert result.success is True
    assert result.booking is not None
    assert set(PatientInfo.model_fields) == {"patient_name", "phone_number"}


def test_provider_search_fuzzy_matches_doctor_name_and_infers_specialty() -> None:
    tools = make_tools()
    result = tools.search_provider_slots("Maya Patl")
    assert result.success is True
    assert result.slots
    assert all(slot.provider_name == "Dr. Maya Patel" for slot in result.slots)
    assert all(slot.specialty == "Primary care" for slot in result.slots)
    assert "Specialty inferred as Primary care" in result.message


def test_booking_changes_slot_status() -> None:
    tools = make_tools()
    result = tools.book_appointment("slot_card_1", patient(), "Follow-up", True)
    assert result.success is True
    slot = tools.store.get_slot("slot_card_1")
    assert slot is not None
    assert slot.is_booked is True
    assert slot.is_available is False


def test_booking_id_uses_digits_only_for_voice() -> None:
    tools = make_tools()
    result = tools.book_appointment("slot_card_1", patient(), "Follow-up", True)
    assert result.booking is not None
    assert result.booking.booking_id.isdigit()


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


def test_search_bookings_by_phone_returns_scheduled_appointments() -> None:
    tools = make_tools()
    booking = tools.book_appointment("slot_card_1", patient(), "Follow-up", True).booking
    assert booking is not None

    result = tools.search_bookings_by_phone("5550100")

    assert result.success is True
    assert len(result.bookings) == 1
    assert result.bookings[0].booking_id == booking.booking_id
    assert len(result.appointment_details) == 1
    assert result.appointment_details[0].booking_id == booking.booking_id
    assert result.appointment_details[0].provider_name == "Dr. Elena Rivera"
    assert result.appointment_details[0].specialty == "Cardiology"
    assert result.appointment_details[0].location == "Heart Center"
    assert result.appointment_details[0].appointment_time is not None
    assert "slot_card_1" not in result.appointment_details[0].model_dump_json()


def test_get_booking_returns_voice_friendly_appointment_detail() -> None:
    tools = make_tools()
    booking = tools.book_appointment("slot_pc_1", patient(), "Hand pain", True).booking
    assert booking is not None

    result = tools.get_booking(booking.booking_id)

    assert result["success"] is True
    assert result["appointment_detail"]["booking_id"] == booking.booking_id
    assert result["appointment_detail"]["provider_name"] == "Dr. Maya Patel"
    assert result["appointment_detail"]["specialty"] == "Primary care"
    assert result["appointment_detail"]["location"] == "Downtown Clinic"
    assert result["appointment_detail"]["appointment_time"] is not None
    assert "slot_pc_1" not in result["appointment_detail"].__str__()


def test_search_bookings_by_phone_ignores_canceled_by_default() -> None:
    tools = make_tools()
    booking = tools.book_appointment("slot_card_1", patient(), "Follow-up", True).booking
    assert booking is not None
    tools.cancel_appointment(booking.booking_id, explicit_confirmation=True)

    active_result = tools.search_bookings_by_phone("555-0100")
    history_result = tools.search_bookings_by_phone("555-0100", include_canceled=True)

    assert active_result.success is True
    assert active_result.bookings == []
    assert len(history_result.bookings) == 1
    assert history_result.bookings[0].booking_id == booking.booking_id


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


def test_json_store_persists_booking_across_instances(tmp_path) -> None:
    first_store = JsonAppointmentStore(tmp_path)
    first_tools = SchedulingTools(first_store)
    booking = first_tools.book_appointment("slot_card_1", patient(), "Follow-up", True).booking
    assert booking is not None

    second_store = JsonAppointmentStore(tmp_path)
    persisted_booking = second_store.get_booking(booking.booking_id)
    persisted_slot = second_store.get_slot("slot_card_1")
    persisted_lookup = SchedulingTools(second_store).search_bookings_by_phone("555-0100")

    assert persisted_booking is not None
    assert persisted_booking.booking_id == booking.booking_id
    assert persisted_slot is not None
    assert persisted_slot.is_booked is True
    assert len(persisted_lookup.bookings) == 1
    assert persisted_lookup.bookings[0].booking_id == booking.booking_id


def test_json_store_migrates_legacy_booking_ids_to_digits(tmp_path) -> None:
    first_store = JsonAppointmentStore(tmp_path)
    first_store.bookings_path.write_text(
        json.dumps(
            [
                {
                    "booking_id": "bk_08358756",
                    "slot_id": "slot_pc_1",
                    "patient_info": {"patient_name": "Aman Kumar", "phone_number": "9193496712"},
                    "appointment_reason": "hand pain",
                    "status": "booked",
                    "created_at": "2026-06-26T20:29:42.581210",
                }
            ]
        ),
        encoding="utf-8",
    )

    migrated_store = JsonAppointmentStore(tmp_path)
    migrated_booking = migrated_store.list_bookings()[0]
    lookup = SchedulingTools(migrated_store).search_bookings_by_phone("9193496712")

    assert migrated_booking.booking_id.isdigit()
    assert lookup.appointment_details[0].booking_id.isdigit()
    assert lookup.appointment_details[0].provider_name == "Dr. Maya Patel"
