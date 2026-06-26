# Implementation Notes

This file captures the current design thinking for the appointment scheduling assistant.

## Current Direction

The system is a simple voice-enabled scheduling assistant. A user can send text or audio, and audio is transcribed to English before the message reaches the orchestrator. The orchestrator then uses one LLM conversation loop plus deterministic scheduling tools for booking, cancellation, rescheduling, and lookup.

The goal is to keep the system fast, explainable, and easy to operate locally. OpenAI handles STT, TTS, and the LLM. Scheduling state is handled by typed Python tools and a local JSON-backed store.

Booking reference numbers use digits only so they are easier to hear and repeat in a voice conversation.

Existing appointment lookup returns a user-facing appointment detail object that includes provider, specialty, location, and appointment time. Internal slot IDs stay in the backend and should not be read aloud.

## Latency Choices

Urgency detection runs before the LLM using regex patterns. This keeps urgent routing fast because the system does not wait for a model call before telling the user to call 911.

The urgent pattern list includes high-signal phrases such as chest pain, trouble breathing, severe bleeding, stroke symptoms, suicidal language, excruciating pain, serious falls, injuries, and accidents.

Speech output uses OpenAI's configurable TTS speed setting. The default is `1.25`, which makes the assistant speak faster while keeping responses understandable.

## User Information

Booking requires only patient name, phone number, appointment reason, selected slot, and explicit confirmation. Date of birth is intentionally not collected in this version.

The appointment reason is still required, but the assistant should reuse it if the user already mentioned it earlier. For example, if the user says they need an appointment for knee pain, the assistant should not ask for the reason again later.

## Provider Search

If the user asks for a specific doctor or provider, the system should prioritize provider lookup over a conflicting specialty. Provider lookup uses Python standard library fuzzy matching with `difflib.SequenceMatcher` and token overlap. When a provider is found, the specialty is inferred from that provider's slot data.

This keeps provider search lightweight and avoids adding another dependency while still handling misspellings such as partial names or small typos.

## Tool Boundary

The LLM chooses what to ask next or which tool to request. The LLM does not directly change appointment state.

State changes only happen through deterministic tools:

- `hold_slot`
- `book_appointment`
- `cancel_appointment`
- `reschedule_appointment`

Booking, cancellation, and rescheduling still require explicit user confirmation.

## Next Robustness Work

Likely next steps are better evaluation cases, more provider-name variations, more realistic slot data, and stronger guardrails around ambiguous symptoms and sensitive information. The architecture should stay simple unless a new requirement clearly needs more structure.
