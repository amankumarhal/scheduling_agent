from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from app.sample_data import SPECIALTIES
from app.models import (
    AppointmentBooking,
    AppointmentSlot,
    BookAppointmentInput,
    BookAppointmentOutput,
    BookingStatus,
    CancelAppointmentInput,
    CancelAppointmentOutput,
    HoldSlotInput,
    HoldSlotOutput,
    RescheduleAppointmentInput,
    RescheduleAppointmentOutput,
    SearchSlotsInput,
    SearchSlotsOutput,
)
from app.store import InMemoryAppointmentStore


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


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
    iso_date = slot.start_time.date().isoformat()
    weekday = slot.start_time.strftime("%A").lower()
    return text in iso_date or text in weekday or iso_date in text or weekday in text


def _error_output(output_model: type[BaseModel], message: str) -> BaseModel:
    return output_model(success=False, message=message)


class SchedulingTools:
    def __init__(self, store: InMemoryAppointmentStore):
        self.store = store

    def list_specialties(self) -> dict[str, Any]:
        return {"success": True, "message": "Available specialties returned.", "specialties": SPECIALTIES}

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

        specialty_norm = _normalize(data.specialty)
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
            return SearchSlotsOutput(
                success=True,
                message="No matching available slots were found. Offer alternatives or ask for a broader time.",
                slots=[],
            )
        return SearchSlotsOutput(success=True, message=f"Found {len(matches)} available slot(s).", slots=matches)

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
            return {"success": False, "message": "Booking not found.", "booking": None}
        return {"success": True, "message": "Booking found.", "booking": booking.model_dump(mode="json")}

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
