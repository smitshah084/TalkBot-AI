from openai import OpenAI
from dotenv import load_dotenv
import os
import base64

# Load environment variables
load_dotenv()

# Get API key from environment variables
API_KEY = os.getenv("OPENAI_API_KEY") 
API_KEY = os.environ.get("OPENAI_API_KEY", API_KEY)

import websocket
import threading
import pyaudio
import json
import time

# Replace with your OpenAI API key
# API_KEY = 'your-api-key'

# Audio configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

def on_message(ws, message):
    data = json.loads(message)
    if 'text' in data:
        print("Transcription:", data['text'])

def on_error(ws, error):
    print("Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def on_open(ws):
    def run():
        # Send session initialization message
        session_message = {
            "type": "session.create",
            "model": "whisper-1",
            "modalities": ["audio"]
        }
        ws.send(json.dumps(session_message))

        # Start audio streaming
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)
        print("Recording...")
        try:
            while True:
                data = stream.read(CHUNK)
                audio_message = {
                    "type": "audio",
                    "data": base64.b64encode(data).decode('utf-8')
                }
                ws.send(json.dumps(audio_message))
        except KeyboardInterrupt:
            stream.stop_stream()
            stream.close()
            audio.terminate()
            ws.close()
        except websocket.WebSocketConnectionClosedException as e:
            print("WebSocket connection closed:", e)
            stream.stop_stream()
            stream.close()
            audio.terminate()
    threading.Thread(target=run).start()

if __name__ == "__main__":
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    ws = websocket.WebSocketApp("wss://api.openai.com/v1/realtime?intent=transcription",
                                header=headers,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()
