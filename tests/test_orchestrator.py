from app.orchestrator import AppointmentOrchestrator
from app.prompts import EMERGENCY_RESPONSE, SYSTEM_PROMPT
from app.scheduling_tools import SchedulingTools
from app.store import InMemoryAppointmentStore


class MockOpenAIClient:
    def __init__(self, responses: list[dict] | None = None):
        self.responses = responses or []
        self.calls = 0
        self.last_messages = None

    def call_llm(self, messages, tools=None, tool_choice="auto"):
        self.calls += 1
        self.last_messages = messages
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
    assert response.state_summary["last_intent"]["intent"] == "book"


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
    assert response.state_summary["last_intent"]["intent"] == "emergency"
    assert mock.calls == 0


def test_expanded_urgent_terms_trigger_emergency_response() -> None:
    mock = MockOpenAIClient()
    agent = AppointmentOrchestrator(openai_client=mock)
    response = agent.handle_message("I was in an accident and need an appointment.", session_id="accident")
    assert response.message == EMERGENCY_RESPONSE
    assert mock.calls == 0


def test_fall_and_head_injury_trigger_emergency_response() -> None:
    mock = MockOpenAIClient()
    agent = AppointmentOrchestrator(openai_client=mock)
    response = agent.handle_message("I fell and hit my head. Can I get an appointment?", session_id="fall")
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


def test_emergency_clarification_allows_scheduling_to_resume() -> None:
    mock = MockOpenAIClient([assistant_response("I can help with primary care. Do you have a preferred day?")])
    agent = AppointmentOrchestrator(openai_client=mock)
    first = agent.handle_message("I just fell from my bed.", session_id="emergency-clarify")
    second = agent.handle_message(
        "Sorry, I made a mistake. I did not get injured. I just need an appointment for primary care.",
        session_id="emergency-clarify",
    )

    assert first.message == EMERGENCY_RESPONSE
    assert second.message == "I can help with primary care. Do you have a preferred day?"
    assert second.state_summary["emergency_active"] is False
    assert mock.calls == 1


def test_minor_injury_clarification_resumes_scheduling() -> None:
    mock = MockOpenAIClient([assistant_response("I can help with primary care. What day works best?")])
    agent = AppointmentOrchestrator(openai_client=mock)
    first = agent.handle_message("I just fell from my bed.", session_id="minor-injury")
    second = agent.handle_message(
        "No, but it's not that much broken. It is small. It is very minimal pain. So I can just go with a primary care doctor.",
        session_id="minor-injury",
    )

    assert first.message == EMERGENCY_RESPONSE
    assert second.message == "I can help with primary care. What day works best?"
    assert second.state_summary["emergency_active"] is False
    assert mock.calls == 1


def test_just_kidding_clarification_resumes_scheduling() -> None:
    mock = MockOpenAIClient([assistant_response("I can help schedule primary care. Do you have a preferred time?")])
    agent = AppointmentOrchestrator(openai_client=mock)
    first = agent.handle_message("I just fell from my bed.", session_id="just-kidding")
    second = agent.handle_message(
        "I was just kidding. Can you please help me get an appointment for primary care?",
        session_id="just-kidding",
    )

    assert first.message == EMERGENCY_RESPONSE
    assert second.message == "I can help schedule primary care. Do you have a preferred time?"
    assert second.state_summary["emergency_active"] is False
    assert mock.calls == 1


def test_non_emergency_injury_context_does_not_get_medical_advice() -> None:
    mock = MockOpenAIClient([assistant_response("This should not be called.")])
    agent = AppointmentOrchestrator(openai_client=mock)
    response = agent.handle_message(
        "I just got injured on my right hand which is a broken bone.",
        session_id="minor-injury-context",
    )

    assert "I can help schedule an appointment" in response.message
    assert "primary care" in response.message
    assert response.state_summary["emergency_active"] is False
    assert mock.calls == 0


def test_orchestrator_normalizes_tts_unfriendly_output() -> None:
    mock = MockOpenAIClient([assistant_response("Fri, Jun 26 \u2014 9:00\u20139:30 AM works.")])
    agent = AppointmentOrchestrator(openai_client=mock)
    response = agent.handle_message("Show me a time.", session_id="normalize")
    assert response.message == "Friday, June 26, 9:00 to 9:30 AM works."


def test_orchestrator_can_lookup_existing_booking_by_phone() -> None:
    store = InMemoryAppointmentStore()
    patient = {"patient_name": "Sample Patient", "phone_number": "555-0100"}
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
    assert "bookings" not in response.tool_calls[0].output
    assert response.tool_calls[0].output["appointment_details"][0]["booking_id"] == booking.booking_id
    assert response.tool_calls[0].output["appointment_details"][0]["provider_name"] == "Dr. Elena Rivera"
    assert response.tool_calls[0].output["appointment_details"][0]["location"] == "Heart Center"
    assert booking.booking_id in response.message


def test_orchestrator_bounds_llm_history() -> None:
    mock = MockOpenAIClient([assistant_response("I can help with that. What specialty do you need?")])
    agent = AppointmentOrchestrator(openai_client=mock)
    state = agent.get_state("history")
    for index in range(30):
        state.messages.append({"role": "user", "content": f"user {index}"})
        state.messages.append({"role": "assistant", "content": f"assistant {index}"})
        state.messages.append({"role": "tool", "content": '{"large":"payload"}'})

    agent.handle_message("I need an appointment.", session_id="history")

    assert mock.last_messages is not None
    assert len(mock.last_messages) <= 15
    assert all(message.get("role") != "tool" for message in mock.last_messages)
