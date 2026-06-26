from app.orchestrator import AppointmentOrchestrator
from app.prompts import EMERGENCY_RESPONSE, SYSTEM_PROMPT


class FakeOpenAIClient:
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


def test_orchestrator_asks_for_missing_info_instead_of_hallucinating() -> None:
    fake = FakeOpenAIClient([assistant_response("I can help with that. What type of appointment do you need?")])
    agent = AppointmentOrchestrator(openai_client=fake)
    response = agent.handle_message("I need an appointment.", session_id="missing")
    assert "what type" in response.message.lower()
    assert response.tool_calls == []


def test_orchestrator_keeps_tone_empathetic() -> None:
    assert "empathetic" in SYSTEM_PROMPT.lower()
    fake = FakeOpenAIClient(
        [assistant_response("I’m sorry for the hassle. I can help you reschedule it. Could you share your booking ID?")]
    )
    agent = AppointmentOrchestrator(openai_client=fake)
    response = agent.handle_message("I need to move my appointment. This is frustrating.", session_id="tone")
    assert "sorry" in response.message.lower()
    assert "help" in response.message.lower()


def test_emergency_message_triggers_emergency_response() -> None:
    fake = FakeOpenAIClient()
    agent = AppointmentOrchestrator(openai_client=fake)
    response = agent.handle_message("I have severe chest pain and need an appointment.", session_id="emergency")
    assert response.message == EMERGENCY_RESPONSE
    assert fake.calls == 0


def test_emergency_response_does_not_continue_scheduling() -> None:
    fake = FakeOpenAIClient()
    agent = AppointmentOrchestrator(openai_client=fake)
    first = agent.handle_message("I think I'm having a stroke. Can I schedule something?", session_id="emergency-stop")
    second = agent.handle_message("Can you find cardiology slots?", session_id="emergency-stop")
    assert first.message == EMERGENCY_RESPONSE
    assert second.message == EMERGENCY_RESPONSE
    assert second.tool_calls == []
    assert fake.calls == 0


def test_orchestrator_normalizes_tts_unfriendly_output() -> None:
    fake = FakeOpenAIClient([assistant_response("Fri, Jun 26 \u2014 9:00\u20139:30 AM works.")])
    agent = AppointmentOrchestrator(openai_client=fake)
    response = agent.handle_message("Show me a time.", session_id="normalize")
    assert response.message == "Friday, June 26, 9:00 to 9:30 AM works."
