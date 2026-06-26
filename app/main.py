from app.orchestrator import AppointmentOrchestrator


def create_agent() -> AppointmentOrchestrator:
    return AppointmentOrchestrator()


if __name__ == "__main__":
    agent = create_agent()
    print(agent.handle_message("I need an appointment.").message)
