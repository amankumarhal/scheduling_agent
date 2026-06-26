from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, ValidationError

from app.sample_data import SPECIALTIES
from app.models import (
    AppointmentDetail,
    AppointmentBooking,
    AppointmentSlot,
    AppointmentSlotOption,
    BookAppointmentInput,
    BookAppointmentOutput,
    BookingStatus,
    CancelAppointmentInput,
    CancelAppointmentOutput,
    HoldSlotInput,
    HoldSlotOutput,
    RescheduleAppointmentInput,
    RescheduleAppointmentOutput,
    SearchBookingsByPhoneInput,
    SearchBookingsByPhoneOutput,
    SearchProviderSlotsInput,
    SearchSlotsInput,
    SearchSlotsOutput,
)
from app.store import InMemoryAppointmentStore


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _digits_only(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


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
    "derm": "Dermatology",
    "skin doctor": "Dermatology",
    "skin specialist": "Dermatology",
    "pediatrics": "Pediatrics",
    "pediatrician": "Pediatrics",
    "child doctor": "Pediatrics",
    "children doctor": "Pediatrics",
    "physical therapy": "Physical therapy",
    "physical therapist": "Physical therapy",
    "physio": "Physical therapy",
    "pt": "Physical therapy",
}


def _canonical_specialty(value: str | None) -> str:
    text = _normalize(value)
    if not text:
        return ""
    collapsed = " ".join(text.replace("-", " ").split())
    if collapsed in SPECIALTY_ALIASES:
        return SPECIALTY_ALIASES[collapsed]

    candidates = {specialty: specialty for specialty in SPECIALTIES}
    candidates.update(SPECIALTY_ALIASES)
    best_label = ""
    best_score = 0.0
    for candidate, label in candidates.items():
        candidate_norm = _normalize(candidate)
        if candidate_norm in collapsed or collapsed in candidate_norm:
            return label
        score = SequenceMatcher(None, collapsed, candidate_norm).ratio()
        if score > best_score:
            best_label = label
            best_score = score
    return best_label if best_score >= 0.72 else value.strip()


def _name_similarity(left: str, right: str) -> float:
    left_norm = _normalize(left).replace("dr.", "").replace("dr ", "").strip()
    right_norm = _normalize(right).replace("dr.", "").replace("dr ", "").strip()
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 1.0
    left_tokens = set(left_norm.replace(",", " ").split())
    right_tokens = set(right_norm.replace(",", " ").split())
    token_overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    sequence_score = SequenceMatcher(None, left_norm, right_norm).ratio()
    return max(token_overlap, sequence_score)


def _time_window_matches(slot: AppointmentSlot, preferred_time_window: str | None) -> bool:
    if not preferred_time_window:
        return True
    window = preferred_time_window.lower()
    hour = slot.start_time.hour
    if "morning" in window:
        return hour < 12
    if "afternoon" in window:
        return 12 <= hour < 17
    if "evening" in window:
        return hour >= 17
    return True


def _date_matches(slot: AppointmentSlot, preferred_date: str | None) -> bool:
    if not preferred_date:
        return True
    text = preferred_date.strip().lower()
    today = datetime.now().date()
    if "today" in text:
        return slot.start_time.date() == today
    if "tomorrow" in text:
        return slot.start_time.date() == today + timedelta(days=1)
    iso_date = slot.start_time.date().isoformat()
    weekday = slot.start_time.strftime("%A").lower()
    normalized_text = text.replace("next ", "")
    return normalized_text in iso_date or normalized_text in weekday or iso_date in text or weekday in normalized_text


def _format_appointment_time(slot: AppointmentSlot | None) -> str | None:
    if not slot:
        return None
    start = slot.start_time.strftime("%A, %B %-d, %Y at %-I:%M %p")
    end = slot.end_time.strftime("%-I:%M %p")
    return f"{start} to {end}"


def _slot_options(slots: list[AppointmentSlot]) -> list[AppointmentSlotOption]:
    options = []
    for slot in slots:
        appointment_time = _format_appointment_time(slot)
        if not appointment_time:
            continue
        options.append(
            AppointmentSlotOption(
                slot_id=slot.slot_id,
                provider_name=slot.provider_name,
                specialty=slot.specialty,
                location=slot.location,
                appointment_time=appointment_time,
            )
        )
    return options


def _error_output(output_model: type[BaseModel], message: str) -> BaseModel:
    return output_model(success=False, message=message)


class SchedulingTools:
    def __init__(self, store: InMemoryAppointmentStore):
        self.store = store

    def list_specialties(self) -> dict[str, Any]:
        return {"success": True, "message": "Available specialties returned.", "specialties": SPECIALTIES}

    def _appointment_detail(self, booking: AppointmentBooking) -> AppointmentDetail:
        slot = self.store.get_slot(booking.slot_id)
        return AppointmentDetail(
            booking_id=booking.booking_id,
            patient_name=booking.patient_info.patient_name,
            phone_number=booking.patient_info.phone_number,
            appointment_reason=booking.appointment_reason,
            status=booking.status,
            provider_name=slot.provider_name if slot else None,
            specialty=slot.specialty if slot else None,
            location=slot.location if slot else None,
            appointment_time=_format_appointment_time(slot),
            created_at=booking.created_at,
        )

    def _available_slots_for_scope(self, specialty: str | None = None, provider_name: str | None = None) -> list[AppointmentSlot]:
        specialty_norm = _normalize(_canonical_specialty(specialty))
        provider_norm = _normalize(provider_name)
        slots = []
        for slot in self.store.list_slots():
            if not slot.is_available or slot.is_booked:
                continue
            if specialty_norm and _normalize(slot.specialty) != specialty_norm:
                continue
            if provider_norm and provider_norm not in _normalize(slot.provider_name):
                continue
            slots.append(slot)
        return sorted(slots, key=lambda item: item.start_time)

    def search_available_slots(
        self,
        specialty: str,
        preferred_date: str | None = None,
        preferred_time_window: str | None = None,
        provider_name: str | None = None,
    ) -> SearchSlotsOutput:
        try:
            data = SearchSlotsInput(
                specialty=specialty,
                preferred_date=preferred_date,
                preferred_time_window=preferred_time_window,
                provider_name=provider_name,
            )
        except ValidationError as exc:
            return _error_output(SearchSlotsOutput, f"Invalid search input: {exc.errors()}")  # type: ignore[return-value]

        specialty = _canonical_specialty(data.specialty)
        specialty_norm = _normalize(specialty)
        provider_norm = _normalize(data.provider_name)
        matches = []
        for slot in self.store.list_slots():
            if not slot.is_available or slot.is_booked:
                continue
            if _normalize(slot.specialty) != specialty_norm:
                continue
            if provider_norm and provider_norm not in _normalize(slot.provider_name):
                continue
            if not _date_matches(slot, data.preferred_date):
                continue
            if not _time_window_matches(slot, data.preferred_time_window):
                continue
            matches.append(slot)

        if not matches:
            alternatives = []
            if data.preferred_date or data.preferred_time_window:
                alternatives = self._available_slots_for_scope(data.specialty, data.provider_name)[:3]
            if alternatives:
                return SearchSlotsOutput(
                    success=True,
                    message=(
                        "No slots match the requested date or time. "
                        "List these soonest available alternatives in the same response and ask whether one works."
                    ),
                    slots=alternatives,
                    slot_options=_slot_options(alternatives),
                )
            return SearchSlotsOutput(
                success=True,
                message="No matching available slots were found. Ask one follow-up question for a broader date or time.",
                slots=[],
            )
        return SearchSlotsOutput(
            success=True,
            message=f"Found {len(matches)} available slot(s).",
            slots=matches,
            slot_options=_slot_options(matches),
        )

    def search_provider_slots(
        self,
        provider_query: str,
        preferred_date: str | None = None,
        preferred_time_window: str | None = None,
    ) -> SearchSlotsOutput:
        try:
            data = SearchProviderSlotsInput(
                provider_query=provider_query,
                preferred_date=preferred_date,
                preferred_time_window=preferred_time_window,
            )
        except ValidationError as exc:
            return _error_output(SearchSlotsOutput, f"Invalid provider search input: {exc.errors()}")  # type: ignore[return-value]

        ranked_providers: list[tuple[float, str]] = []
        seen = set()
        for slot in self.store.list_slots():
            if slot.provider_name in seen:
                continue
            seen.add(slot.provider_name)
            score = _name_similarity(data.provider_query, slot.provider_name)
            if score >= 0.45:
                ranked_providers.append((score, slot.provider_name))

        if not ranked_providers:
            return SearchSlotsOutput(
                success=True,
                message="No matching provider was found. Ask the user to clarify the provider name or choose a specialty.",
                slots=[],
            )

        ranked_providers.sort(reverse=True)
        best_score, best_provider = ranked_providers[0]
        if len(ranked_providers) > 1 and best_score < 0.75:
            provider_names = [name for _, name in ranked_providers[:3]]
            return SearchSlotsOutput(
                success=True,
                message=f"Multiple similar providers were found: {provider_names}. Ask which provider the user means.",
                slots=[],
            )

        slots = []
        for slot in self.store.list_slots():
            if slot.provider_name != best_provider:
                continue
            if not slot.is_available or slot.is_booked:
                continue
            if not _date_matches(slot, data.preferred_date):
                continue
            if not _time_window_matches(slot, data.preferred_time_window):
                continue
            slots.append(slot)

        if not slots:
            alternatives = []
            if data.preferred_date or data.preferred_time_window:
                alternatives = self._available_slots_for_scope(provider_name=best_provider)[:3]
            if alternatives:
                return SearchSlotsOutput(
                    success=True,
                    message=(
                        f"Provider {best_provider} was found, but no slots match the requested date or time. "
                        "List these soonest available alternatives in the same response and ask whether one works."
                    ),
                    slots=alternatives,
                    slot_options=_slot_options(alternatives),
                )
            return SearchSlotsOutput(
                success=True,
                message=f"Provider {best_provider} was found, but no matching available slots were found. Offer another time or specialty.",
                slots=[],
            )
        specialty = slots[0].specialty
        return SearchSlotsOutput(
            success=True,
            message=f"Found {len(slots)} available slot(s) for {best_provider}. Specialty inferred as {specialty}.",
            slots=slots,
            slot_options=_slot_options(slots),
        )

    def hold_slot(self, slot_id: str, patient_id: str | None = None) -> HoldSlotOutput:
        try:
            data = HoldSlotInput(slot_id=slot_id, patient_id=patient_id)
        except ValidationError as exc:
            return _error_output(HoldSlotOutput, f"Invalid hold input: {exc.errors()}")  # type: ignore[return-value]

        slot = self.store.get_slot(data.slot_id)
        if not slot:
            return HoldSlotOutput(success=False, message="Slot not found.")
        if slot.is_booked:
            return HoldSlotOutput(success=False, message="Slot is already booked.")
        if not slot.is_available:
            return HoldSlotOutput(success=False, message="Slot is not available.")
        slot.is_held = True
        self.store.save_slot(slot)
        return HoldSlotOutput(success=True, message="Slot held temporarily. Confirm before booking.", slot=slot)

    def book_appointment(
        self,
        slot_id: str,
        patient_info: dict[str, Any],
        appointment_reason: str,
        explicit_confirmation: bool,
    ) -> BookAppointmentOutput:
        try:
            data = BookAppointmentInput(
                slot_id=slot_id,
                patient_info=patient_info,
                appointment_reason=appointment_reason,
                explicit_confirmation=explicit_confirmation,
            )
        except ValidationError as exc:
            return BookAppointmentOutput(success=False, message=f"Missing or invalid booking information: {exc.errors()}")

        if not data.explicit_confirmation:
            return BookAppointmentOutput(success=False, message="Explicit confirmation is required before booking.")

        slot = self.store.get_slot(data.slot_id)
        if not slot:
            return BookAppointmentOutput(success=False, message="Slot not found.")
        if slot.is_booked:
            return BookAppointmentOutput(success=False, message="Slot is already booked.")
        if not slot.is_available:
            return BookAppointmentOutput(success=False, message="Slot is not available.")

        slot.is_booked = True
        slot.is_available = False
        slot.is_held = False
        self.store.save_slot(slot)
        booking = AppointmentBooking(
            slot_id=slot.slot_id,
            patient_info=data.patient_info,
            appointment_reason=data.appointment_reason,
            status=BookingStatus.booked,
            created_at=datetime.utcnow(),
        )
        self.store.add_booking(booking)
        return BookAppointmentOutput(success=True, message="Appointment booked successfully.", booking=booking)

    def get_booking(self, booking_id: str) -> dict[str, Any]:
        booking = self.store.get_booking(booking_id)
        if not booking:
            return {"success": False, "message": "Booking not found.", "booking": None, "appointment_detail": None}
        return {
            "success": True,
            "message": "Booking found. Use appointment_detail for the user-facing response and do not mention internal slot IDs.",
            "booking": booking.model_dump(mode="json"),
            "appointment_detail": self._appointment_detail(booking).model_dump(mode="json"),
        }

    def search_bookings_by_phone(
        self,
        phone_number: str,
        include_canceled: bool = False,
    ) -> SearchBookingsByPhoneOutput:
        try:
            data = SearchBookingsByPhoneInput(phone_number=phone_number, include_canceled=include_canceled)
        except ValidationError as exc:
            return SearchBookingsByPhoneOutput(
                success=False,
                message=f"Invalid booking lookup input: {exc.errors()}",
            )

        requested_phone = _digits_only(data.phone_number)
        if len(requested_phone) < 7:
            return SearchBookingsByPhoneOutput(
                success=False,
                message="Please provide a valid phone number with at least seven digits.",
            )

        matches = []
        for booking in self.store.list_bookings():
            booking_phone = _digits_only(booking.patient_info.phone_number)
            if booking_phone != requested_phone:
                continue
            if booking.status == BookingStatus.canceled and not data.include_canceled:
                continue
            matches.append(booking)

        if not matches:
            return SearchBookingsByPhoneOutput(
                success=True,
                message="No scheduled appointments were found for that phone number.",
                bookings=[],
                appointment_details=[],
            )

        return SearchBookingsByPhoneOutput(
            success=True,
            message=(
                f"Found {len(matches)} appointment(s) for that phone number. "
                "Use appointment_details for the user-facing response and do not mention internal slot IDs."
            ),
            bookings=matches,
            appointment_details=[self._appointment_detail(booking) for booking in matches],
        )

    def cancel_appointment(
        self,
        booking_id: str,
        patient_name: str | None = None,
        explicit_confirmation: bool = False,
    ) -> CancelAppointmentOutput:
        try:
            data = CancelAppointmentInput(
                booking_id=booking_id,
                patient_name=patient_name,
                explicit_confirmation=explicit_confirmation,
            )
        except ValidationError as exc:
            return CancelAppointmentOutput(success=False, message=f"Invalid cancellation input: {exc.errors()}")

        if not data.explicit_confirmation:
            return CancelAppointmentOutput(success=False, message="Explicit confirmation is required before cancellation.")
        booking = self.store.get_booking(data.booking_id)
        if not booking:
            return CancelAppointmentOutput(success=False, message="Booking not found.")
        if data.patient_name and _normalize(data.patient_name) != _normalize(booking.patient_info.patient_name):
            return CancelAppointmentOutput(success=False, message="Patient name does not match the booking.")
        if booking.status == BookingStatus.canceled:
            return CancelAppointmentOutput(success=False, message="Booking is already canceled.", booking=booking)

        booking.status = BookingStatus.canceled
        self.store.save_booking(booking)
        slot = self.store.get_slot(booking.slot_id)
        if slot:
            slot.is_booked = False
            slot.is_available = True
            slot.is_held = False
            self.store.save_slot(slot)
        return CancelAppointmentOutput(success=True, message="Appointment canceled successfully.", booking=booking)

    def reschedule_appointment(
        self,
        booking_id: str,
        new_slot_id: str,
        explicit_confirmation: bool = False,
    ) -> RescheduleAppointmentOutput:
        try:
            data = RescheduleAppointmentInput(
                booking_id=booking_id,
                new_slot_id=new_slot_id,
                explicit_confirmation=explicit_confirmation,
            )
        except ValidationError as exc:
            return RescheduleAppointmentOutput(success=False, message=f"Invalid reschedule input: {exc.errors()}")

        if not data.explicit_confirmation:
            return RescheduleAppointmentOutput(success=False, message="Explicit confirmation is required before rescheduling.")
        booking = self.store.get_booking(data.booking_id)
        if not booking:
            return RescheduleAppointmentOutput(success=False, message="Booking not found.")
        if booking.status == BookingStatus.canceled:
            return RescheduleAppointmentOutput(success=False, message="Cannot reschedule a canceled booking.")

        old_slot = self.store.get_slot(booking.slot_id)
        new_slot = self.store.get_slot(data.new_slot_id)
        if not new_slot:
            return RescheduleAppointmentOutput(success=False, message="New slot not found.")
        if new_slot.is_booked:
            return RescheduleAppointmentOutput(success=False, message="New slot is already booked.")
        if not new_slot.is_available:
            return RescheduleAppointmentOutput(success=False, message="New slot is not available.")

        old_slot_id = booking.slot_id
        if old_slot:
            old_slot.is_booked = False
            old_slot.is_available = True
            old_slot.is_held = False
            self.store.save_slot(old_slot)
        new_slot.is_booked = True
        new_slot.is_available = False
        new_slot.is_held = False
        self.store.save_slot(new_slot)
        booking.slot_id = new_slot.slot_id
        booking.status = BookingStatus.booked
        self.store.save_booking(booking)
        return RescheduleAppointmentOutput(
            success=True,
            message="Appointment rescheduled successfully.",
            booking=booking,
            old_slot_id=old_slot_id,
            new_slot=new_slot,
        )
