from __future__ import annotations

from copy import deepcopy

from app.demo_data import create_demo_slots
from app.models import AppointmentBooking, AppointmentSlot


class InMemoryAppointmentStore:
    """Tiny fake scheduling backend with no real patient data."""

    def __init__(self, slots: list[AppointmentSlot] | None = None):
        self.slots: dict[str, AppointmentSlot] = {
            slot.slot_id: deepcopy(slot) for slot in (slots or create_demo_slots())
        }
        self.bookings: dict[str, AppointmentBooking] = {}

    def list_slots(self) -> list[AppointmentSlot]:
        return list(self.slots.values())

    def get_slot(self, slot_id: str) -> AppointmentSlot | None:
        return self.slots.get(slot_id)

    def save_slot(self, slot: AppointmentSlot) -> None:
        self.slots[slot.slot_id] = slot

    def add_booking(self, booking: AppointmentBooking) -> AppointmentBooking:
        self.bookings[booking.booking_id] = booking
        return booking

    def get_booking(self, booking_id: str) -> AppointmentBooking | None:
        return self.bookings.get(booking_id)

    def save_booking(self, booking: AppointmentBooking) -> AppointmentBooking:
        self.bookings[booking.booking_id] = booking
        return booking

    def reset(self) -> None:
        self.slots = {slot.slot_id: slot for slot in create_demo_slots()}
        self.bookings = {}

