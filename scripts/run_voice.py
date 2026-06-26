#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.orchestrator import AppointmentOrchestrator  # noqa: E402
from app.stt_client import transcribe_audio  # noqa: E402
from app.tts_client import synthesize_speech  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Audio-file runner for the appointment scheduling assistant.")
    parser.add_argument("--audio", required=True, help="Path to an input audio file.")
    parser.add_argument("--out", default="response.mp3", help="Path for generated speech output.")
    parser.add_argument("--session-id", default="voice", help="Conversation session ID.")
    args = parser.parse_args()

    transcription = transcribe_audio(args.audio)
    print(f"Transcription: {transcription}")

    agent = AppointmentOrchestrator()
    response = agent.handle_message(transcription, session_id=args.session_id)
    print(f"Agent: {response.message}")

    output_path = synthesize_speech(response.message, args.out)
    print(f"TTS output: {output_path}")


if __name__ == "__main__":
    main()
