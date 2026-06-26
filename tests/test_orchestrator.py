from app.orchestrator import AppointmentOrchestrator
from app.prompts import EMERGENCY_RESPONSE, SYSTEM_PROMPT
from app.scheduling_tools import SchedulingTools
from app.store import InMemoryAppointmentStore


class MockOpenAIClient:
    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self.calls = 0

    def call_llm(self, messages, tools=None, tool_choice="auto"):
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I’m sorry you’re dealing with that. What type of appointment would you like?",
                    }
                }
            ]
        }


def assistant_response(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def tool_call_response(tool_name: str, arguments: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_lookup",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": arguments},
                        }
                    ],
                }
            }
        ]
    }


def test_orchestrator_asks_for_missing_info_instead_of_hallucinating() -> None:
    mock = MockOpenAIClient([assistant_response("I can help with that. What type of appointment do you need?")])
    agent = AppointmentOrchestrator(openai_client=mock)
    response = agent.handle_message("I need an appointment.", session_id="missing")
    assert "what type" in response.message.lower()
    assert response.tool_calls == []


def test_orchestrator_keeps_tone_empathetic() -> None:
    assert "empathetic" in SYSTEM_PROMPT.lower()
    mock = MockOpenAIClient(
        [assistant_response("I’m sorry for the hassle. I can help you reschedule it. Could you share your booking ID?")]
    )
    agent = AppointmentOrchestrator(openai_client=mock)
    response = agent.handle_message("I need to move my appointment. This is frustrating.", session_id="tone")
    assert "sorry" in response.message.lower()
    assert "help" in response.message.lower()


def test_emergency_message_triggers_emergency_response() -> None:
    mock = MockOpenAIClient()
    agent = AppointmentOrchestrator(openai_client=mock)
    response = agent.handle_message("I have severe chest pain and need an appointment.", session_id="emergency")
    assert response.message == EMERGENCY_RESPONSE
    assert mock.calls == 0


def test_emergency_response_does_not_continue_scheduling() -> None:
    mock = MockOpenAIClient()
    agent = AppointmentOrchestrator(openai_client=mock)
    first = agent.handle_message("I think I'm having a stroke. Can I schedule something?", session_id="emergency-stop")
    second = agent.handle_message("Can you find cardiology slots?", session_id="emergency-stop")
    assert first.message == EMERGENCY_RESPONSE
    assert second.message == EMERGENCY_RESPONSE
    assert second.tool_calls == []
    assert mock.calls == 0


def test_orchestrator_normalizes_tts_unfriendly_output() -> None:
    mock = MockOpenAIClient([assistant_response("Fri, Jun 26 \u2014 9:00\u20139:30 AM works.")])
    agent = AppointmentOrchestrator(openai_client=mock)
    response = agent.handle_message("Show me a time.", session_id="normalize")
    assert response.message == "Friday, June 26, 9:00 to 9:30 AM works."


def test_orchestrator_can_lookup_existing_booking_by_phone() -> None:
    store = InMemoryAppointmentStore()
    patient = {"patient_name": "Sample Patient", "date_of_birth": "1990-01-01", "phone_number": "555-0100"}
    booking = SchedulingTools(store).book_appointment("slot_card_1", patient, "Follow-up", True).booking
    assert booking is not None
    mock = MockOpenAIClient(
        [
            tool_call_response(
                "search_bookings_by_phone",
                '{"phone_number":"555-0100","include_canceled":false}',
            ),
            assistant_response(f"I found your scheduled appointment. Booking ID: {booking.booking_id}"),
        ]
    )
    agent = AppointmentOrchestrator(openai_client=mock, store=store)

    response = agent.handle_message("Can you find my already scheduled appointment? My phone is 555-0100.")

    assert response.tool_calls[0].tool_name == "search_bookings_by_phone"
    assert response.tool_calls[0].output["bookings"][0]["booking_id"] == booking.booking_id
    assert booking.booking_id in response.message
