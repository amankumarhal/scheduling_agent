from app.orchestrator import AppointmentOrchestrator


def create_agent() -> AppointmentOrchestrator:
    """Construct an orchestrator for simple direct Python execution."""
    return AppointmentOrchestrator()


if __name__ == "__main__":
    agent = create_agent()
    print(agent.handle_message("I need an appointment.").message)
