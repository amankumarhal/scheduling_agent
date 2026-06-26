from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.models import AgentResponse, ConversationState, ToolCallRecord
from app.openai_client import OpenAIClient
from app.prompts import EMERGENCY_RESPONSE, SYSTEM_PROMPT
from app.scheduling_tools import SchedulingTools
from app.session_logger import SessionLogger
from app.store import InMemoryAppointmentStore, create_default_store
from app.text_utils import normalize_for_voice


EMERGENCY_PATTERNS = [
    r"\b(chest pain|severe chest pain)\b",
    r"\b(trouble breathing|can't breathe|cannot breathe|shortness of breath)\b",
    r"\b(severe bleeding|bleeding heavily)\b",
    r"\b(stroke|face drooping|slurred speech)\b",
    r"\b(suicidal|suicide|kill myself|self harm)\b",
]


def is_emergency(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in EMERGENCY_PATTERNS)


def is_emergency_clarification(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in ["not an emergency", "not emergency", "false alarm"])


def _schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


OPENAI_TOOLS = [
    _schema(
        "list_specialties",
        "Call when the user needs to know which appointment specialties are available.",
        {},
        [],
    ),
    _schema(
        "search_available_slots",
        "Search available, non-booked slots after the user has provided a specialty.",
        {
            "specialty": {"type": "string"},
            "preferred_date": {"type": ["string", "null"], "description": "Optional date text, ISO date, or weekday."},
            "preferred_time_window": {
                "type": ["string", "null"],
                "description": "Optional time preference such as morning, afternoon, or evening.",
            },
            "provider_name": {"type": ["string", "null"], "description": "Optional provider name filter."},
        },
        ["specialty", "preferred_date", "preferred_time_window", "provider_name"],
    ),
    _schema(
        "hold_slot",
        "Temporarily hold a slot the user is considering. This does not book the appointment.",
        {
            "slot_id": {"type": "string"},
            "patient_id": {"type": ["string", "null"]},
        },
        ["slot_id", "patient_id"],
    ),
    _schema(
        "book_appointment",
        "Book an appointment only after explicit user confirmation of all booking details.",
        {
            "slot_id": {"type": "string"},
            "patient_info": {
                "type": "object",
                "properties": {
                    "patient_name": {"type": "string"},
                    "date_of_birth": {"type": "string"},
                    "phone_number": {"type": "string"},
                },
                "required": ["patient_name", "date_of_birth", "phone_number"],
                "additionalProperties": False,
            },
            "appointment_reason": {"type": "string"},
            "explicit_confirmation": {"type": "boolean"},
        },
        ["slot_id", "patient_info", "appointment_reason", "explicit_confirmation"],
    ),
    _schema(
        "get_booking",
        "Retrieve a booking by booking ID before cancellation or rescheduling.",
        {"booking_id": {"type": "string"}},
        ["booking_id"],
    ),
    _schema(
        "search_bookings_by_phone",
        "Look up already scheduled appointments by patient phone number. Call only when the user asks about an existing appointment, cancellation, or rescheduling and does not have a booking ID.",
        {
            "phone_number": {"type": "string"},
            "include_canceled": {
                "type": "boolean",
                "description": "Whether to include canceled appointments in the lookup. Use false unless the user asks for canceled appointment history.",
            },
        },
        ["phone_number", "include_canceled"],
    ),
    _schema(
        "cancel_appointment",
        "Cancel an appointment only after explicit user confirmation.",
        {
            "booking_id": {"type": "string"},
            "patient_name": {"type": ["string", "null"]},
            "explicit_confirmation": {"type": "boolean"},
        },
        ["booking_id", "patient_name", "explicit_confirmation"],
    ),
    _schema(
        "reschedule_appointment",
        "Move a booking to a new slot only after explicit user confirmation.",
        {
            "booking_id": {"type": "string"},
            "new_slot_id": {"type": "string"},
            "explicit_confirmation": {"type": "boolean"},
        },
        ["booking_id", "new_slot_id", "explicit_confirmation"],
    ),
]


class AppointmentOrchestrator:
    def __init__(
        self,
        openai_client: OpenAIClient | Any | None = None,
        store: InMemoryAppointmentStore | None = None,
    ):
        self.store = store or create_default_store()
        self.tools = SchedulingTools(self.store)
        self.openai_client = openai_client or OpenAIClient()
        self.sessions: dict[str, ConversationState] = {}
        self.session_logger = SessionLogger()

    def get_state(self, session_id: str) -> ConversationState:
        if session_id not in self.sessions:
            self.sessions[session_id] = ConversationState(session_id=session_id)
        return self.sessions[session_id]

    def handle_message(self, message: str, session_id: str = "default") -> AgentResponse:
        state = self.get_state(session_id)

        if state.emergency_active and not is_emergency_clarification(message):
            self.session_logger.log(session_id, "user", {"message": message})
            return self._record_assistant_response(state, EMERGENCY_RESPONSE)
        if is_emergency(message) and not is_emergency_clarification(message):
            state.emergency_active = True
            self.session_logger.log(session_id, "user", {"message": message})
            return self._record_assistant_response(state, EMERGENCY_RESPONSE)
        if state.emergency_active and is_emergency_clarification(message):
            state.emergency_active = False

        state.messages.append({"role": "user", "content": message})
        self.session_logger.log(session_id, "user", {"message": message})
        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + state.messages

        local_tool_calls: list[ToolCallRecord] = []
        for _ in range(5):
            response = self.openai_client.call_llm(llm_messages, tools=OPENAI_TOOLS, tool_choice="auto")
            assistant_message = self._extract_message(response)
            tool_calls = self._extract_tool_calls(assistant_message)
            if not tool_calls:
                content = normalize_for_voice(self._extract_content(assistant_message))
                state.messages.append({"role": "assistant", "content": content})
                self.session_logger.log(session_id, "assistant", {"message": content})
                return self._agent_response(state, content, local_tool_calls)

            llm_messages.append(self._assistant_tool_message_for_history(assistant_message))
            state.messages.append(self._assistant_tool_message_for_history(assistant_message))
            for tool_call in tool_calls:
                record, tool_message = self._execute_tool_call(tool_call, state)
                local_tool_calls.append(record)
                state.tool_calls.append(record)
                llm_messages.append(tool_message)
                state.messages.append(tool_message)

        fallback = "I’m sorry, I hit a tool loop while working on that. Could you restate what you want to do next?"
        fallback = normalize_for_voice(fallback)
        state.messages.append({"role": "assistant", "content": fallback})
        self.session_logger.log(session_id, "assistant", {"message": fallback})
        return self._agent_response(state, fallback, local_tool_calls)

    def _execute_tool_call(self, tool_call: Any, state: ConversationState) -> tuple[ToolCallRecord, dict[str, Any]]:
        name = self._tool_name(tool_call)
        raw_arguments = self._tool_arguments(tool_call)
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            arguments = {}
            output = {"success": False, "message": "Tool arguments were not valid JSON."}
        else:
            output = self._dispatch_tool(name, arguments, state)

        record = ToolCallRecord(tool_name=name, arguments=arguments, output=output)
        self.session_logger.log(
            state.session_id,
            "tool_call",
            record.model_dump(mode="json"),
        )
        tool_message = {
            "role": "tool",
            "tool_call_id": self._tool_call_id(tool_call),
            "name": name,
            "content": json.dumps(output, default=str),
        }
        return record, tool_message

    def _dispatch_tool(self, name: str, arguments: dict[str, Any], state: ConversationState) -> dict[str, Any]:
        try:
            if name == "list_specialties":
                return self.tools.list_specialties()
            if name == "search_available_slots":
                result = self.tools.search_available_slots(**arguments)
                state.last_offered_slots = result.slots
                return result.model_dump(mode="json")
            if name == "hold_slot":
                result = self.tools.hold_slot(**arguments)
                if result.success and result.slot:
                    state.pending_slot_id = result.slot.slot_id
                    state.pending_action = "book"
                return result.model_dump(mode="json")
            if name == "book_appointment":
                result = self.tools.book_appointment(**arguments)
                if result.success:
                    state.pending_action = None
                    state.pending_slot_id = None
                return result.model_dump(mode="json")
            if name == "get_booking":
                result = self.tools.get_booking(**arguments)
                if result.get("success"):
                    state.pending_booking_id = arguments.get("booking_id")
                return result
            if name == "search_bookings_by_phone":
                result = self.tools.search_bookings_by_phone(**arguments)
                if result.success and len(result.bookings) == 1:
                    state.pending_booking_id = result.bookings[0].booking_id
                return result.model_dump(mode="json")
            if name == "cancel_appointment":
                result = self.tools.cancel_appointment(**arguments)
                if result.success:
                    state.pending_action = None
                    state.pending_booking_id = None
                return result.model_dump(mode="json")
            if name == "reschedule_appointment":
                result = self.tools.reschedule_appointment(**arguments)
                if result.success:
                    state.pending_action = None
                    state.pending_booking_id = None
                    state.pending_slot_id = None
                return result.model_dump(mode="json")
            return {"success": False, "message": f"Unknown tool: {name}"}
        except TypeError as exc:
            return {"success": False, "message": f"Invalid tool arguments for {name}: {exc}"}
        except ValidationError as exc:
            return {"success": False, "message": f"Validation failed for {name}: {exc.errors()}"}

    def _agent_response(
        self,
        state: ConversationState,
        content: str,
        local_tool_calls: list[ToolCallRecord],
    ) -> AgentResponse:
        return AgentResponse(
            message=content,
            session_id=state.session_id,
            tool_calls=local_tool_calls,
            state_summary=self._state_summary(state),
        )

    def _record_assistant_response(self, state: ConversationState, content: str) -> AgentResponse:
        content = normalize_for_voice(content)
        state.messages.append({"role": "assistant", "content": content})
        self.session_logger.log(state.session_id, "assistant", {"message": content})
        return self._agent_response(state, content, [])

    def _state_summary(self, state: ConversationState) -> dict[str, Any]:
        return {
            "session_id": state.session_id,
            "pending_action": state.pending_action,
            "pending_slot_id": state.pending_slot_id,
            "pending_booking_id": state.pending_booking_id,
            "last_offered_slot_ids": [slot.slot_id for slot in state.last_offered_slots],
            "tool_call_count": len(state.tool_calls),
            "emergency_active": state.emergency_active,
        }

    @staticmethod
    def _extract_message(response: Any) -> Any:
        if isinstance(response, dict):
            return response["choices"][0]["message"]
        return response.choices[0].message

    @staticmethod
    def _extract_content(message: Any) -> str:
        if isinstance(message, dict):
            return message.get("content") or ""
        return message.content or ""

    @staticmethod
    def _extract_tool_calls(message: Any) -> list[Any]:
        if isinstance(message, dict):
            return message.get("tool_calls") or []
        return message.tool_calls or []

    @staticmethod
    def _assistant_tool_message_for_history(message: Any) -> dict[str, Any]:
        if isinstance(message, dict):
            return message
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in (message.tool_calls or [])
            ],
        }

    @staticmethod
    def _tool_name(tool_call: Any) -> str:
        if isinstance(tool_call, dict):
            return tool_call["function"]["name"]
        return tool_call.function.name

    @staticmethod
    def _tool_arguments(tool_call: Any) -> str:
        if isinstance(tool_call, dict):
            return tool_call["function"].get("arguments", "{}")
        return tool_call.function.arguments

    @staticmethod
    def _tool_call_id(tool_call: Any) -> str:
        if isinstance(tool_call, dict):
            return tool_call.get("id", "tool_call")
        return tool_call.id
