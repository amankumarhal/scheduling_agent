# Appointment Scheduling AI Agent Slides

## Slide 1: Title

Appointment Scheduling AI Agent

Text and voice assistant for booking, rescheduling, and canceling demo appointments.

## Slide 2: Problem

Patients need a calm scheduling experience that can handle incomplete information, frustration, and voice input.

The system must be safe because scheduling changes affect real-world commitments.

## Slide 3: Solution

Build a small custom agent:

- OpenAI for LLM, STT, and TTS
- FastAPI for API and browser UI
- Pydantic for schemas and validation
- Deterministic scheduling tools for state changes
- In-memory demo store for interview simplicity

## Slide 4: Core Principle

The LLM talks. Tools mutate.

The model can ask questions, reason, and request tools. It cannot directly book, cancel, or reschedule.

## Slide 5: Architecture

```text
User text or audio
-> Browser UI
-> OpenAI STT if voice
-> Orchestrator
-> GPT-5.5 tool calling
-> Scheduling tools
-> Store
-> Sanitized response
-> Streaming UI
-> OpenAI TTS
```

## Slide 6: Safety

- Explicit confirmation before booking
- Explicit confirmation before cancellation
- Explicit confirmation before rescheduling
- Emergency handling before model call
- No medical advice
- English-only responses and STT language setting

## Slide 7: Voice Experience

- Hold-to-talk microphone input
- Audio file sent to OpenAI transcription
- Assistant response shown in chat
- TTS generated with OpenAI speech
- Interrupt button stops playback
- Voice upload retries once after transient fetch failure

## Slide 8: Conversation State

Per-session state tracks:

- Message history
- Pending action
- Held slot
- Pending booking
- Last offered slots
- Tool calls
- Emergency status

## Slide 9: Logging And Debugging

- Session events written as JSONL
- Tool calls visible in UI debug mode
- Tests mock OpenAI
- Deterministic tools can be tested independently

## Slide 10: Coding Interview Framing

How I would communicate:

- Clarify requirements first
- State assumptions
- Keep implementation small and readable
- Explain tradeoffs
- Test critical invariants
- Debug from narrow, observable signals

## Slide 11: System Design Framing

How I would scale this:

- Replace in-memory store with scheduling backend
- Add authentication
- Add audit logging
- Add observability
- Add human handoff
- Add streaming voice transport
- Add retry and timeout policies

## Slide 12: Demo Walkthrough

Demo path:

1. Open browser UI
2. Ask for an appointment
3. Search slots
4. Hold selected slot
5. Confirm patient details
6. Book appointment
7. Show tool trace
8. Test emergency response

## Slide 13: Challenges

- Preventing unsafe model actions
- Handling partial patient information
- Keeping voice responses TTS-friendly
- Recovering from transient browser audio failures
- Balancing demo simplicity with production realism

## Slide 14: Improvements

Next steps:

- Real scheduling integration
- HIPAA and security review
- Persistent sessions
- Streaming STT and TTS
- Evaluation harness
- Calendar and provider availability integration

## Slide 15: What Interviewers Should Notice

- Technical depth
- Clear ownership
- Product thinking
- Safety-oriented design
- Testability
- Practical tradeoff decisions
- Ability to explain the system end to end

