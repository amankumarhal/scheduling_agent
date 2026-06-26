from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from app.config import get_settings
from app.sample_data import create_sample_slots
from app.models import AppointmentBooking, AppointmentSlot


class InMemoryAppointmentStore:
    """Small in-memory scheduling backend with sample data only."""

    def __init__(self, slots: list[AppointmentSlot] | None = None):
        self.slots: dict[str, AppointmentSlot] = {
            slot.slot_id: deepcopy(slot) for slot in (slots or create_sample_slots())
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

    def list_bookings(self) -> list[AppointmentBooking]:
        return list(self.bookings.values())

    def save_booking(self, booking: AppointmentBooking) -> AppointmentBooking:
        self.bookings[booking.booking_id] = booking
        return booking

    def reset(self) -> None:
        self.slots = {slot.slot_id: slot for slot in create_sample_slots()}
        self.bookings = {}


class JsonAppointmentStore(InMemoryAppointmentStore):
    """JSON-backed store for local persistence without an external database."""

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir or get_settings().appointment_data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.slots_path = self.data_dir / "slots.json"
        self.bookings_path = self.data_dir / "bookings.json"
        self.slots = self._load_slots()
        self.bookings = self._load_bookings()
        self._persist()

    def _load_slots(self) -> dict[str, AppointmentSlot]:
        if not self.slots_path.exists():
            return {slot.slot_id: slot for slot in create_sample_slots()}
        with self.slots_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {item["slot_id"]: AppointmentSlot.model_validate(item) for item in data}

    def _load_bookings(self) -> dict[str, AppointmentBooking]:
        if not self.bookings_path.exists():
            return {}
        with self.bookings_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {item["booking_id"]: AppointmentBooking.model_validate(item) for item in data}

    def _persist(self) -> None:
        self._write_json(
            self.slots_path,
            [slot.model_dump(mode="json") for slot in sorted(self.slots.values(), key=lambda item: item.slot_id)],
        )
        self._write_json(
            self.bookings_path,
            [
                booking.model_dump(mode="json")
                for booking in sorted(self.bookings.values(), key=lambda item: item.created_at)
            ],
        )

    @staticmethod
    def _write_json(path: Path, payload: list[dict]) -> None:
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        temp_path.replace(path)

    def save_slot(self, slot: AppointmentSlot) -> None:
        super().save_slot(slot)
        self._persist()

    def add_booking(self, booking: AppointmentBooking) -> AppointmentBooking:
        result = super().add_booking(booking)
        self._persist()
        return result

    def save_booking(self, booking: AppointmentBooking) -> AppointmentBooking:
        result = super().save_booking(booking)
        self._persist()
        return result

    def reset(self) -> None:
        super().reset()
        self._persist()


def create_default_store() -> JsonAppointmentStore:
    return JsonAppointmentStore()
