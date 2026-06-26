from __future__ import annotations

import json
import atexit
import threading
import time
from copy import deepcopy
from pathlib import Path

from app.config import get_settings
from app.sample_data import create_sample_slots
from app.models import AppointmentBooking, AppointmentSlot, generate_booking_reference


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
        self._lock = threading.RLock()
        self._persist_event = threading.Event()
        self._stop_event = threading.Event()
        self._persist_thread = threading.Thread(target=self._persist_worker, daemon=True)
        self.slots = self._load_slots()
        self.bookings = self._load_bookings()
        self._persist_now()
        self._persist_thread.start()
        atexit.register(self.shutdown)

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
        bookings: dict[str, AppointmentBooking] = {}
        for item in data:
            booking = AppointmentBooking.model_validate(item)
            while not booking.booking_id.isdigit() or booking.booking_id in bookings:
                booking.booking_id = generate_booking_reference()
            bookings[booking.booking_id] = booking
        return bookings

    def _persist_now(self) -> None:
        with self._lock:
            slots_payload = [
                slot.model_dump(mode="json") for slot in sorted(self.slots.values(), key=lambda item: item.slot_id)
            ]
            bookings_payload = [
                booking.model_dump(mode="json")
                for booking in sorted(self.bookings.values(), key=lambda item: item.created_at)
            ]
        self._write_json(
            self.slots_path,
            slots_payload,
        )
        self._write_json(
            self.bookings_path,
            bookings_payload,
        )

    def _request_persist(self) -> None:
        self._persist_event.set()

    def _persist_worker(self) -> None:
        while not self._stop_event.is_set():
            if not self._persist_event.wait(timeout=0.25):
                continue
            time.sleep(0.05)
            self._persist_event.clear()
            self._persist_now()

    def flush(self) -> None:
        self._persist_event.clear()
        self._persist_now()

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self.flush()
        self._persist_thread.join(timeout=2)

    @staticmethod
    def _write_json(path: Path, payload: list[dict]) -> None:
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        temp_path.replace(path)

    def save_slot(self, slot: AppointmentSlot) -> None:
        with self._lock:
            super().save_slot(slot)
        self._request_persist()

    def add_booking(self, booking: AppointmentBooking) -> AppointmentBooking:
        with self._lock:
            result = super().add_booking(booking)
        self._request_persist()
        return result

    def save_booking(self, booking: AppointmentBooking) -> AppointmentBooking:
        with self._lock:
            result = super().save_booking(booking)
        self._request_persist()
        return result

    def reset(self) -> None:
        with self._lock:
            super().reset()
        self._request_persist()


def create_default_store() -> JsonAppointmentStore:
    return JsonAppointmentStore()
