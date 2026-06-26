from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class BookingStatus(str, Enum):
    booked = "booked"
    canceled = "canceled"
    rescheduled = "rescheduled"


class PatientInfo(BaseModel):
    patient_name: str = Field(..., min_length=1)
    date_of_birth: str = Field(..., min_length=1, description="Patient date of birth, preferably YYYY-MM-DD")
    phone_number: str = Field(..., min_length=7)

    @field_validator("patient_name", "date_of_birth", "phone_number")
    @classmethod
    def not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be blank.")
        return cleaned


class AppointmentSlot(BaseModel):
    slot_id: str
    provider_name: str
    specialty: str
    location: str
    start_time: datetime
    end_time: datetime
    is_available: bool = True
    is_held: bool = False
    is_booked: bool = False


class AppointmentBooking(BaseModel):
    booking_id: str = Field(default_factory=lambda: f"bk_{uuid4().hex[:8]}")
    slot_id: str
    patient_info: PatientInfo
    appointment_reason: str = Field(..., min_length=1)
    status: BookingStatus = BookingStatus.booked
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("appointment_reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Appointment reason is required.")
        return cleaned


class AppointmentRequest(BaseModel):
    specialty: str | None = None
    preferred_date: str | None = None
    preferred_time_window: str | None = None
    provider_name: str | None = None
    appointment_reason: str | None = None
    patient_info: PatientInfo | None = None


class SearchSlotsInput(BaseModel):
    specialty: str
    preferred_date: str | None = None
    preferred_time_window: str | None = None
    provider_name: str | None = None


class SearchSlotsOutput(BaseModel):
    success: bool
    message: str
    slots: list[AppointmentSlot] = Field(default_factory=list)


class HoldSlotInput(BaseModel):
    slot_id: str
    patient_id: str | None = None


class HoldSlotOutput(BaseModel):
    success: bool
    message: str
    slot: AppointmentSlot | None = None


class BookAppointmentInput(BaseModel):
    slot_id: str
    patient_info: PatientInfo
    appointment_reason: str = Field(..., min_length=1)
    explicit_confirmation: bool = False

    @field_validator("appointment_reason")
    @classmethod
    def appointment_reason_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Appointment reason is required.")
        return cleaned


class BookAppointmentOutput(BaseModel):
    success: bool
    message: str
    booking: AppointmentBooking | None = None


class CancelAppointmentInput(BaseModel):
    booking_id: str
    patient_name: str | None = None
    explicit_confirmation: bool = False


class CancelAppointmentOutput(BaseModel):
    success: bool
    message: str
    booking: AppointmentBooking | None = None


class RescheduleAppointmentInput(BaseModel):
    booking_id: str
    new_slot_id: str
    explicit_confirmation: bool = False


class RescheduleAppointmentOutput(BaseModel):
    success: bool
    message: str
    booking: AppointmentBooking | None = None
    old_slot_id: str | None = None
    new_slot: AppointmentSlot | None = None


class ToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    output: dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationState(BaseModel):
    session_id: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    appointment_request: AppointmentRequest = Field(default_factory=AppointmentRequest)
    pending_action: Literal["book", "cancel", "reschedule"] | None = None
    pending_slot_id: str | None = None
    pending_booking_id: str | None = None
    last_offered_slots: list[AppointmentSlot] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    emergency_active: bool = False


class AgentResponse(BaseModel):
    message: str
    session_id: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    state_summary: dict[str, Any] = Field(default_factory=dict)
