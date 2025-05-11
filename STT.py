import os
import base64
import json
import threading
import time
import requests
import pyaudio
import websocket
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key
API_KEY = os.getenv("OPENAI_API_KEY")

# Audio configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

# Get ephemeral token
def get_ephemeral_token():
    url = "https://api.openai.com/v1/realtime/transcription_sessions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "openai-beta": "realtime=v1"  # ✅ Required header
    }
    body = {
        "input_audio_format": "pcm16",
        "input_audio_transcription": {
            "model": "gpt-4o-transcribe"
        },
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500
        },
        "input_audio_noise_reduction": {
            "type": "near_field"
        },
        "include": ["item.input_audio_transcription.logprobs"]
    }

    response = requests.post(url, headers=headers, json=body)
    
    if response.status_code == 200:
        print("GOT TOKEN")
        return response.json()["client_secret"]["value"]
    else:
        print("DID NOT GET TOKEN")
        print("Failed to fetch ephemeral token:", response.text)
        return None

# WebSocket event handlers
def on_message(ws, message):
    try:
        data = json.loads(message).get('transcript')
        # type(data), data.keys(),data,
        if data:
            print("Received:", data)
    except Exception as e:
        print("Error parsing message:", e)

def on_error(ws, error):
    print("WebSocket Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def on_open(ws):
    def run():
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS,
                            rate=RATE, input=True, frames_per_buffer=CHUNK)
        print("Recording... Press Ctrl+C to stop.")
        try:
            while ws.keep_running:
                audio_chunk = stream.read(CHUNK)
                audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                audio_payload = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_base64
                }
                try:
                    ws.send(json.dumps(audio_payload))
                except websocket.WebSocketConnectionClosedException:
                    print("WebSocket closed. Stopping recording.")
                    break
        except KeyboardInterrupt:
            print("Interrupted by user.")
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()
            ws.close()
    threading.Thread(target=run).start()

class SpeechToText:
    def __init__(self, on_transcription=None):
        self.on_transcription = on_transcription
        self.ws = None
        
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if 'type' in data:
                if data['type'] == 'speech.started':
                    print("\n[Voice input detected...]")
                elif data['type'] == 'speech.stopped':
                    print("[Voice input stopped]")
                
            transcript = data.get('transcript')
            if transcript and self.on_transcription:
                self.on_transcription(transcript)
        except Exception as e:
            print("Error parsing message:", e)

    def start(self):
        token = get_ephemeral_token()
        if not token:
            return False

        ws_url = "wss://api.openai.com/v1/realtime?intent=transcription"
        headers = {
            "Authorization": f"Bearer {token}",
            "openai-beta": "realtime=v1"
        }

        self.ws = websocket.WebSocketApp(
            ws_url,
            header=headers,
            on_open=on_open,
            on_message=self.on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
        return True

    def stop(self):
        if self.ws:
            self.ws.close()
