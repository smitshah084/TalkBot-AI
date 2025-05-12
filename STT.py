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

# WebSocket event handlers
def on_error(ws, error):
    print("WebSocket Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

class SpeechToText:
    def __init__(self, on_transcription=None):
        self.on_transcription = on_transcription
        self.ws = None
        self.token = None
        
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

    def get_ephemeral_token(self):
        url = "https://api.openai.com/v1/realtime/transcription_sessions"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "openai-beta": "realtime=v1"
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
            self.token = response.json()["client_secret"]["value"]
            return True
        else:
            print("Failed to fetch ephemeral token:", response.text)
            return False

    def start(self):
        if not self.get_ephemeral_token():
            return False

        ws_url = "wss://api.openai.com/v1/realtime?intent=transcription"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "openai-beta": "realtime=v1"
        }

        self.ws = websocket.WebSocketApp(
            ws_url,
            header=headers,
            on_message=self.on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
        return True

    def process_audio(self, audio_data):
        """Process incoming audio data from WebSocket"""
        if self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                audio_payload = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_base64
                }
                self.ws.send(json.dumps(audio_payload))
                return True
            except Exception as e:
                print(f"Error processing audio: {e}")
                return False
        return False

    def stop(self):
        if self.ws:
            self.ws.close()
