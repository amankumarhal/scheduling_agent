from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

from app.orchestrator import AppointmentOrchestrator
from app.stt_client import transcribe_audio
from app.tts_client import (
    cartesia_streaming_enabled,
    speech_media_type,
    stream_cartesia_sse_events,
    synthesize_speech,
    synthesize_speech_bytes,
)

app = FastAPI(title="Appointment Scheduling AI Agent")
agent = AppointmentOrchestrator()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class SpeakRequest(BaseModel):
    text: str


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Appointment Scheduling AI Agent</title>
        <style>
          :root {
            color-scheme: light;
            --bg: #f7f8fb;
            --panel: #ffffff;
            --ink: #172033;
            --muted: #667085;
            --line: #d9e0ea;
            --accent: #0f766e;
            --accent-strong: #115e59;
            --danger: #b42318;
            --user: #e7f5f2;
            --assistant: #f2f4f7;
          }
          * { box-sizing: border-box; }
          body {
            margin: 0;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--ink);
            background: var(--bg);
          }
          .shell {
            min-height: 100vh;
            display: grid;
            grid-template-rows: auto 1fr auto;
          }
          header {
            padding: 18px 24px;
            border-bottom: 1px solid var(--line);
            background: var(--panel);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
          }
          h1 {
            font-size: 20px;
            margin: 0;
          }
          .sub {
            color: var(--muted);
            font-size: 13px;
            margin-top: 3px;
          }
          .status {
            color: var(--muted);
            font-size: 13px;
            text-align: right;
          }
          main {
            width: min(980px, 100%);
            margin: 0 auto;
            padding: 18px;
            display: grid;
            grid-template-rows: 1fr auto;
            gap: 14px;
          }
          #messages {
            min-height: 360px;
            max-height: calc(100vh - 220px);
            overflow: auto;
            padding: 8px 2px;
          }
          .msg {
            width: fit-content;
            max-width: min(720px, 92%);
            padding: 12px 14px;
            margin: 10px 0;
            border: 1px solid var(--line);
            border-radius: 8px;
            line-height: 1.45;
            white-space: pre-wrap;
          }
          .msg.user {
            margin-left: auto;
            background: var(--user);
            border-color: #b6e2da;
          }
          .msg.assistant {
            background: var(--assistant);
          }
          .msg.system {
            margin-left: auto;
            margin-right: auto;
            background: #fff8e6;
            color: #7a4d00;
          }
          details {
            margin: 6px 0 14px;
            color: var(--muted);
            font-size: 12px;
          }
          pre {
            overflow: auto;
            padding: 10px;
            border: 1px solid var(--line);
            background: #ffffff;
            border-radius: 8px;
          }
          .composer {
            border: 1px solid var(--line);
            background: var(--panel);
            border-radius: 8px;
            padding: 12px;
          }
          .row {
            display: flex;
            align-items: center;
            gap: 10px;
          }
          textarea {
            width: 100%;
            min-height: 48px;
            max-height: 120px;
            resize: vertical;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px;
            font: inherit;
          }
          button {
            border: 1px solid var(--line);
            background: #ffffff;
            color: var(--ink);
            border-radius: 8px;
            min-height: 42px;
            padding: 0 14px;
            font: inherit;
            font-weight: 650;
            cursor: pointer;
          }
          button:hover { border-color: var(--accent); }
          button:disabled {
            cursor: not-allowed;
            opacity: 0.55;
          }
          .primary {
            background: var(--accent);
            border-color: var(--accent);
            color: #ffffff;
          }
          .primary:hover {
            background: var(--accent-strong);
          }
          .danger {
            color: var(--danger);
          }
          #micButton.recording {
            background: #fee4e2;
            border-color: #fda29b;
            color: var(--danger);
          }
          .controls {
            justify-content: space-between;
            margin-top: 10px;
            flex-wrap: wrap;
          }
          .left-controls,
          .right-controls {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
          }
          label {
            color: var(--muted);
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
          }
          @media (max-width: 640px) {
            header {
              align-items: flex-start;
              flex-direction: column;
            }
            .status {
              text-align: left;
            }
            main {
              padding: 12px;
            }
            .row,
            .left-controls,
            .right-controls {
              align-items: stretch;
            }
            .right-controls,
            .left-controls,
            button {
              width: 100%;
            }
          }
        </style>
      </head>
      <body>
        <div class="shell">
          <header>
            <div>
              <h1>Appointment Scheduling AI Agent</h1>
              <div class="sub">Schedule, reschedule, or cancel appointments with typed chat or voice.</div>
            </div>
            <div class="status" id="status">Ready</div>
          </header>

          <main>
            <section id="messages" aria-live="polite"></section>

            <section class="composer" aria-label="Chat composer">
              <textarea id="messageInput" placeholder="Type a message, for example: I need a cardiology appointment next Tuesday morning"></textarea>
              <div class="row controls">
                <div class="left-controls">
                  <button id="micButton" type="button" title="Hold to talk">Hold to talk</button>
                  <button id="interruptButton" type="button" class="danger" title="Stop current speech">Interrupt</button>
                  <label><input id="autoSpeak" type="checkbox" checked /> Speak replies</label>
                  <label><input id="debugToggle" type="checkbox" /> Show tool trace</label>
                </div>
                <div class="right-controls">
                  <button id="clearButton" type="button">Clear</button>
                  <button id="sendButton" type="button" class="primary">Send</button>
                </div>
              </div>
            </section>
          </main>
        </div>

        <script>
          const sessionId = crypto.randomUUID();
          const messages = document.getElementById("messages");
          const input = document.getElementById("messageInput");
          const sendButton = document.getElementById("sendButton");
          const micButton = document.getElementById("micButton");
          const interruptButton = document.getElementById("interruptButton");
          const clearButton = document.getElementById("clearButton");
          const statusEl = document.getElementById("status");
          const autoSpeak = document.getElementById("autoSpeak");
          const debugToggle = document.getElementById("debugToggle");

          let currentAudio = null;
          let currentAudioContext = null;
          let currentAudioSources = [];
          let nextAudioStartTime = 0;
          let speechController = null;
          let mediaRecorder = null;
          let mediaStream = null;
          let audioChunks = [];
          let busy = false;
          let voiceRequestInFlight = false;
          let lastAssistantText = "";
          let lastAssistantAt = 0;

          function setStatus(text) {
            statusEl.textContent = text;
          }

          function addMessage(role, text) {
            const bubble = document.createElement("div");
            bubble.className = `msg ${role}`;
            bubble.textContent = text;
            messages.appendChild(bubble);
            messages.scrollTop = messages.scrollHeight;
            return bubble;
          }

          function addToolTrace(toolCalls) {
            if (!debugToggle.checked || !toolCalls || toolCalls.length === 0) return;
            const details = document.createElement("details");
            details.open = true;
            const summary = document.createElement("summary");
            summary.textContent = `Tool trace (${toolCalls.length})`;
            const pre = document.createElement("pre");
            pre.textContent = JSON.stringify(toolCalls, null, 2);
            details.appendChild(summary);
            details.appendChild(pre);
            messages.appendChild(details);
            messages.scrollTop = messages.scrollHeight;
          }

          function shouldSkipDuplicateAssistant(text) {
            const normalized = (text || "").trim();
            const now = Date.now();
            if (normalized && normalized === lastAssistantText && now - lastAssistantAt < 8000) {
              return true;
            }
            lastAssistantText = normalized;
            lastAssistantAt = now;
            return false;
          }

          function setBusy(value) {
            busy = value;
            sendButton.disabled = value;
            input.disabled = value;
          }

          function interruptSpeech() {
            if (speechController) {
              speechController.abort();
              speechController = null;
            }
            if (currentAudio) {
              currentAudio.pause();
              currentAudio.currentTime = 0;
              currentAudio = null;
            }
            currentAudioSources.forEach((source) => {
              try {
                source.stop();
              } catch (error) {}
            });
            currentAudioSources = [];
            if (currentAudioContext) {
              currentAudioContext.close();
              currentAudioContext = null;
            }
            nextAudioStartTime = 0;
            setStatus("Ready");
          }

          function base64ToArrayBuffer(base64) {
            const binary = atob(base64);
            const bytes = new Uint8Array(binary.length);
            for (let index = 0; index < binary.length; index += 1) {
              bytes[index] = binary.charCodeAt(index);
            }
            return bytes.buffer;
          }

          function pcmF32ToSamples(arrayBuffer) {
            const view = new DataView(arrayBuffer);
            const sampleCount = Math.floor(view.byteLength / 4);
            const samples = new Float32Array(sampleCount);
            for (let index = 0; index < sampleCount; index += 1) {
              samples[index] = view.getFloat32(index * 4, true);
            }
            return samples;
          }

          async function playPcmChunk(chunk) {
            if (!currentAudioContext) {
              currentAudioContext = new AudioContext({ sampleRate: chunk.sample_rate || 44100 });
              nextAudioStartTime = currentAudioContext.currentTime + 0.04;
            }
            if (currentAudioContext.state === "suspended") {
              await currentAudioContext.resume();
            }
            const samples = pcmF32ToSamples(base64ToArrayBuffer(chunk.data));
            if (!samples.length) return;
            const buffer = currentAudioContext.createBuffer(1, samples.length, chunk.sample_rate || 44100);
            buffer.copyToChannel(samples, 0);
            const source = currentAudioContext.createBufferSource();
            source.buffer = buffer;
            source.connect(currentAudioContext.destination);
            const startAt = Math.max(nextAudioStartTime, currentAudioContext.currentTime + 0.01);
            source.start(startAt);
            nextAudioStartTime = startAt + buffer.duration;
            currentAudioSources.push(source);
            source.onended = () => {
              currentAudioSources = currentAudioSources.filter((item) => item !== source);
              if (currentAudioSources.length === 0) setStatus("Ready");
            };
          }

          async function speakWithStream(text) {
            const response = await fetch("/speak/stream", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text }),
              signal: speechController.signal
            });
            if (!response.ok || !response.body) return false;
            setStatus("Speaking...");
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            while (true) {
              const { value, done } = await reader.read();
              if (done) break;
              buffer += decoder.decode(value, { stream: true });
              const events = buffer.split("\\n\\n");
              buffer = events.pop() || "";
              for (const event of events) {
                const lines = event.split("\\n");
                const eventType = (lines.find((line) => line.startsWith("event:")) || "event: message").slice(6).trim();
                const dataLine = lines.find((line) => line.startsWith("data:"));
                if (!dataLine) continue;
                const data = JSON.parse(dataLine.slice(5));
                if (eventType === "chunk") await playPcmChunk(data);
                if (eventType === "error") throw new Error(data.message || "Streaming speech failed.");
              }
            }
            return true;
          }

          async function speakWithBlob(text) {
            const response = await fetch("/speak", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text }),
              signal: speechController.signal
            });
            if (!response.ok) return false;
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            currentAudio = new Audio(url);
            currentAudio.onplay = () => setStatus("Speaking...");
            currentAudio.onended = () => {
              URL.revokeObjectURL(url);
              currentAudio = null;
              setStatus("Ready");
            };
            currentAudio.onerror = () => {
              URL.revokeObjectURL(url);
              currentAudio = null;
              setStatus("Ready");
            };
            await currentAudio.play();
            return true;
          }

          async function speak(text) {
            if (!autoSpeak.checked || !text) return;
            interruptSpeech();
            speechController = new AbortController();
            setStatus("Generating speech...");
            try {
              const streamed = await speakWithStream(text);
              if (!streamed) await speakWithBlob(text);
            } catch (error) {
              if (error.name !== "AbortError") {
                addMessage("system", "Speech playback was unavailable, but the text response is shown above.");
              }
              setStatus("Ready");
            } finally {
              speechController = null;
            }
          }

          async function handleAgentResponse(payload) {
            if (shouldSkipDuplicateAssistant(payload.message)) return;
            addMessage("assistant", payload.message);
            addToolTrace(payload.tool_calls);
            await speak(payload.message);
          }

          async function showGreeting(options = { spoken: false }) {
            const greeting = "Hi, I can help schedule, reschedule, or cancel an appointment. What would you like to do?";
            addMessage("assistant", greeting);
            if (options.spoken) {
              await speak(greeting);
            }
          }

          async function handleStreamingChat(text) {
            const assistantBubble = addMessage("assistant", "");
            let finalPayload = null;
            const response = await fetch("/chat/stream", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ message: text, session_id: sessionId })
            });
            if (!response.ok || !response.body) throw new Error(await response.text());

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
              const { value, done } = await reader.read();
              if (done) break;
              buffer += decoder.decode(value, { stream: true });
              const events = buffer.split("\\n\\n");
              buffer = events.pop() || "";

              for (const event of events) {
                const lines = event.split("\\n");
                const eventType = (lines.find((line) => line.startsWith("event:")) || "event: message").slice(6).trim();
                const dataLine = lines.find((line) => line.startsWith("data:"));
                if (!dataLine) continue;
                const data = JSON.parse(dataLine.slice(5));
                if (eventType === "delta") {
                  assistantBubble.textContent += data.text;
                  messages.scrollTop = messages.scrollHeight;
                }
                if (eventType === "final") {
                  finalPayload = data;
                }
              }
            }

            if (finalPayload) {
              assistantBubble.textContent = finalPayload.message;
              shouldSkipDuplicateAssistant(finalPayload.message);
              addToolTrace(finalPayload.tool_calls);
              await speak(finalPayload.message);
            }
          }

          async function sendText() {
            const text = input.value.trim();
            if (!text || busy) return;
            input.value = "";
            interruptSpeech();
            addMessage("user", text);
            setBusy(true);
            setStatus("Thinking...");
            try {
              await handleStreamingChat(text);
            } catch (error) {
              addMessage("system", `Request failed: ${error.message}`);
            } finally {
              setBusy(false);
              setStatus("Ready");
              input.focus();
            }
          }

          async function sendVoice(blob) {
            if (voiceRequestInFlight) return;
            voiceRequestInFlight = true;
            interruptSpeech();
            setBusy(true);
            setStatus("Transcribing...");
            try {
              const data = new FormData();
              data.append("session_id", sessionId);
              data.append("audio", blob, "voice.webm");
              let response;
              try {
                response = await fetch("/voice", { method: "POST", body: data });
              } catch (error) {
                setStatus("Retrying voice...");
                response = await fetch("/voice", { method: "POST", body: data });
              }
              if (!response.ok) throw new Error(await response.text());
              const payload = await response.json();
              addMessage("user", payload.transcription || "[voice message]");
              await handleAgentResponse(payload.response);
            } catch (error) {
              addMessage("system", `Voice request failed: ${error.message}`);
            } finally {
              voiceRequestInFlight = false;
              setBusy(false);
              setStatus("Ready");
              input.focus();
            }
          }

          async function startRecording(event) {
            event.preventDefault();
            if (busy || mediaRecorder) return;
            interruptSpeech();
            try {
              mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
              audioChunks = [];
              mediaRecorder = new MediaRecorder(mediaStream);
              mediaRecorder.ondataavailable = (evt) => {
                if (evt.data.size > 0) audioChunks.push(evt.data);
              };
              mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: "audio/webm" });
                mediaStream.getTracks().forEach((track) => track.stop());
                mediaRecorder = null;
                mediaStream = null;
                micButton.classList.remove("recording");
                micButton.textContent = "Hold to talk";
                if (blob.size > 0) sendVoice(blob);
              };
              mediaRecorder.start();
              micButton.classList.add("recording");
              micButton.textContent = "Release to send";
              setStatus("Listening...");
            } catch (error) {
              addMessage("system", `Microphone unavailable: ${error.message}`);
              setStatus("Ready");
            }
          }

          function stopRecording(event) {
            if (event) event.preventDefault();
            if (mediaRecorder && mediaRecorder.state !== "inactive") {
              mediaRecorder.stop();
            }
          }

          sendButton.addEventListener("click", sendText);
          input.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              sendText();
            }
          });
          interruptButton.addEventListener("click", interruptSpeech);
          clearButton.addEventListener("click", () => {
            interruptSpeech();
            messages.innerHTML = "";
            showGreeting({ spoken: false });
          });
          micButton.addEventListener("pointerdown", startRecording);
          micButton.addEventListener("pointerup", stopRecording);
          micButton.addEventListener("pointercancel", stopRecording);
          micButton.addEventListener("pointerleave", stopRecording);

          showGreeting({ spoken: true });
        </script>
      </body>
    </html>
    """


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    response = agent.handle_message(request.message, session_id=request.session_id)
    return response.model_dump(mode="json")


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    async def event_stream():
        response = agent.handle_message(request.message, session_id=request.session_id)
        words = response.message.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield f"event: delta\ndata: {json.dumps({'text': word + suffix})}\n\n"
            await asyncio.sleep(0.025)
        yield f"event: final\ndata: {response.model_dump_json()}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/speak")
def speak(request: SpeakRequest) -> Response:
    try:
        audio = synthesize_speech_bytes(request.text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=audio, media_type=speech_media_type())


@app.post("/speak/stream")
def speak_stream(request: SpeakRequest) -> StreamingResponse:
    if not cartesia_streaming_enabled():
        raise HTTPException(status_code=409, detail="Cartesia streaming TTS is not enabled.")

    def event_stream():
        try:
            for event in stream_cartesia_sse_events(request.text):
                yield f"event: chunk\ndata: {json.dumps(event)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except RuntimeError as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/voice")
async def voice(
    audio: UploadFile = File(...),
    session_id: str = Form(default="default"),
    tts_output_path: str | None = Form(default=None),
) -> dict:
    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
        temp_audio.write(await audio.read())
        temp_audio_path = temp_audio.name

    try:
        transcription = transcribe_audio(temp_audio_path)
        response = agent.handle_message(transcription, session_id=session_id)
        output_path = tts_output_path
        if output_path:
            synthesize_speech(response.message, output_path)
    finally:
        Path(temp_audio_path).unlink(missing_ok=True)

    return {
        "transcription": transcription,
        "response": response.model_dump(mode="json"),
        "tts_output_path": output_path,
    }
