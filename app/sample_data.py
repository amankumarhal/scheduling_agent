from datetime import datetime, timedelta

from app.models import AppointmentSlot

SPECIALTIES = [
    "Primary care",
    "Cardiology",
    "Dermatology",
    "Pediatrics",
    "Physical therapy",
]


def _next_weekday(days_ahead: int, hour: int, minute: int = 0) -> datetime:
    base = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base + timedelta(days=days_ahead)


def create_sample_slots() -> list[AppointmentSlot]:
    raw_slots = [
        ("slot_pc_1", "Dr. Maya Patel", "Primary care", "Downtown Clinic", 1, 9, 0),
        ("slot_pc_2", "Dr. Maya Patel", "Primary care", "Downtown Clinic", 2, 14, 0),
        ("slot_card_1", "Dr. Elena Rivera", "Cardiology", "Heart Center", 5, 9, 30),
        ("slot_card_2", "Dr. Omar Khan", "Cardiology", "Heart Center", 5, 11, 0),
        ("slot_derm_1", "Dr. Naomi Chen", "Dermatology", "Westside Clinic", 3, 10, 0),
        ("slot_derm_2", "Dr. Naomi Chen", "Dermatology", "Westside Clinic", 4, 15, 30),
        ("slot_peds_1", "Dr. Sofia Martin", "Pediatrics", "Children's Clinic", 1, 13, 0),
        ("slot_peds_2", "Dr. Leo Brooks", "Pediatrics", "Children's Clinic", 6, 9, 0),
        ("slot_pt_1", "Alex Morgan, PT", "Physical therapy", "Rehab Center", 2, 8, 30),
        ("slot_pt_2", "Jordan Lee, PT", "Physical therapy", "Rehab Center", 7, 16, 0),
    ]
    slots: list[AppointmentSlot] = []
    for slot_id, provider, specialty, location, days, hour, minute in raw_slots:
        start = _next_weekday(days, hour, minute)
        slots.append(
            AppointmentSlot(
                slot_id=slot_id,
                provider_name=provider,
                specialty=specialty,
                location=location,
                start_time=start,
                end_time=start + timedelta(minutes=30),
            )
        )
    return slots
