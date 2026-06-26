#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.orchestrator import AppointmentOrchestrator  # noqa: E402


def main() -> None:
    """Run a text-only local conversation loop against the orchestrator."""
    parser = argparse.ArgumentParser(description="Text CLI for the appointment scheduling assistant.")
    parser.add_argument("--session-id", default="cli", help="Conversation session ID.")
    parser.add_argument("--debug", action="store_true", help="Show tool calls and state summary.")
    args = parser.parse_args()

    agent = AppointmentOrchestrator()
    print("Appointment Agent CLI. Type 'exit' to quit.")
    while True:
        user_text = input("\nYou: ").strip()
        if user_text.lower() in {"exit", "quit"}:
            break
        if not user_text:
            continue
        try:
            response = agent.handle_message(user_text, session_id=args.session_id)
        except Exception as exc:
            print(f"Agent error: {exc}")
            continue
        print(f"Agent: {response.message}")
        if args.debug:
            print("\nDebug:")
            print(json.dumps(response.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
