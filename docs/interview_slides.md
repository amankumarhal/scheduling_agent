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

## Slide 5: Current Architecture

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

## Slide 6: Full Agent Process

1. Receive text or audio input
2. Transcribe audio to English if needed
3. Check emergency rules before the LLM
4. Load session state and conversation history
5. Call the LLM with tool schemas
6. Validate and execute requested tool calls
7. Update appointment state only inside tools
8. Sanitize response for TTS
9. Log user, assistant, and tool events
10. Stream response to UI and optionally play TTS

## Slide 7: Agent Best Practices

- Keep deterministic business logic outside the LLM
- Use typed schemas for all tool inputs and outputs
- Require explicit confirmation for state-changing actions
- Keep prompts short, specific, and testable
- Add rule-based safety gates before model calls
- Keep tool traces readable for debugging
- Log session events for audit and evaluation

## Slide 8: Conversation State

Per-session state tracks:

- Message history
- Pending action
- Held slot
- Pending booking
- Last offered slots
- Tool calls
- Emergency status

Production storage should move from process memory to Redis or a database.

## Slide 9: Scheduling Safety

- Search only returns available slots
- Hold prevents racing users from choosing the same slot
- Book validates patient fields and confirmation
- Cancel validates booking and confirmation
- Reschedule validates existing booking, new slot, and confirmation
- Double booking is blocked by backend constraints

## Slide 10: Voice Experience

- Hold-to-talk microphone input
- Audio sent to OpenAI transcription with English language setting
- Assistant response shown in chat
- OpenAI speech output
- Interrupt button stops playback
- Voice upload retries once after transient fetch failure

## Slide 11: Current Streaming Design

The browser uses `POST /chat/stream` to render assistant text progressively.

Current implementation streams the completed assistant response after tool execution. This keeps tool mutation deterministic and easy to explain.

Production upgrade: token streaming with explicit phases for thinking, tool execution, and final answer.

## Slide 12: Production Target Architecture

```text
Client apps
-> API gateway
-> Auth and rate limits
-> Chat service
-> Orchestrator workers
-> Tool execution service
-> Scheduling/EHR integration
-> Session store
-> Audit log
-> Observability stack
```

Audio services can be split into STT and TTS workers for better latency isolation.

## Slide 13: Multi-User Scaling

- Make API servers stateless
- Store sessions in Redis or Postgres
- Run multiple API replicas behind a load balancer
- Use worker queues for slow STT, TTS, and external scheduling calls
- Use connection pools for databases and EHR APIs
- Partition logs by tenant, user, and session
- Autoscale on request rate, latency, and queue depth

## Slide 14: Handling Load

- Rate limit by user, tenant, and IP
- Apply request timeouts and cancellation
- Use retries with exponential backoff for transient provider errors
- Circuit break failing external services
- Cache low-risk reference data like specialties and provider metadata
- Queue long-running audio jobs
- Backpressure voice requests when queues are saturated

## Slide 15: Data Consistency

Appointment booking needs stronger consistency than chat.

Production approach:

- Use database transactions
- Add unique constraints on booked slot IDs
- Use short-lived holds with expiration
- Make booking operations idempotent with request IDs
- Record all state changes in an audit log
- Reconcile with the source scheduling system

## Slide 16: Reliability And Failure Modes

Plan for:

- OpenAI latency or outage
- STT or TTS failure
- Scheduling backend timeout
- Duplicate requests
- User refreshes or reconnects
- Partial tool execution
- Browser microphone permission failure

Fallbacks:

- Preserve text chat if voice fails
- Show clear retryable errors
- Hand off to human support when needed

## Slide 17: Security And Compliance

Healthcare-adjacent production systems need:

- Authentication and authorization
- Tenant isolation
- Secrets management
- Encryption in transit and at rest
- Least-privilege access
- PHI minimization
- Retention and deletion policies
- HIPAA and security review
- Human handoff and escalation policies

## Slide 18: Observability

Track:

- Request latency by endpoint
- LLM latency and tool-call counts
- STT and TTS latency
- Tool success and error rates
- Booking, cancel, and reschedule conversion
- Emergency detection events
- User interruption events
- Cost per conversation

Use traces to connect user request, model call, tool call, and scheduling backend call.

## Slide 19: Evaluation And Quality

Evaluate:

- Tool-call correctness
- Confirmation compliance
- Emergency routing
- Hallucination rate
- TTS readability
- Latency
- Conversation completion rate
- User satisfaction

Use offline test sets plus live monitoring with privacy-safe review.

## Slide 20: Production Readiness Checklist

- Real scheduling backend
- Durable session store
- Durable audit log
- Auth and user identity
- Monitoring and alerting
- Retry, timeout, and circuit breaker policies
- Load testing
- Security review
- Prompt and tool-call evals
- Human handoff process
- Runbooks for incidents

## Slide 21: Coding Interview Framing

How I would communicate:

- Clarify requirements first
- State assumptions
- Keep implementation small and readable
- Explain tradeoffs
- Test critical invariants
- Debug from narrow, observable signals

## Slide 22: System Design Framing

How I would discuss scaling:

- Start with requirements and success metrics
- Separate chat, orchestration, tools, and scheduling backend
- Make API services stateless
- Move state to durable stores
- Protect state-changing operations with transactions
- Add observability, retries, and human handoff

## Slide 23: Demo Walkthrough

Demo path:

1. Open browser UI
2. Ask for an appointment
3. Search slots
4. Hold selected slot
5. Confirm patient details
6. Book appointment
7. Show tool trace
8. Test emergency response

## Slide 24: Challenges

- Preventing unsafe model actions
- Handling partial patient information
- Keeping voice responses TTS-friendly
- Recovering from transient browser audio failures
- Balancing demo simplicity with production realism
- Explaining production gaps honestly

## Slide 25: What Interviewers Should Notice

- Technical depth
- Clear ownership
- Product thinking
- Safety-oriented design
- Testability
- Practical tradeoff decisions
- Ability to explain the system end to end

