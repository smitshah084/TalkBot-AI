import json
import os
import websocket
import threading
import asyncio
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") 
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", OPENAI_API_KEY)

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Make sure it's set in your environment or .env file.")

# WebSocket URL and headers
url = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17"
headers = [
    f"Authorization: Bearer {OPENAI_API_KEY}",
    "OpenAI-Beta: realtime=v1"
]

class ChatSystem:
    def __init__(self):
        self.ws = None
        self.session_ready = False
        self.response_in_progress = False
        self.current_response = ""
        self.current_delta = ""
        self.delta_buffer = []  # Buffer to collect deltas
        self.interrupted = False
        self.connection_event = threading.Event()

    async def ensure_connection(self):
        """Ensure WebSocket is connected and session is ready"""
        if not self.ws or not self.ws.sock or not self.ws.sock.connected:
            self.connection_event.clear()
            self.start()
            
            # Wait for connection with timeout
            timeout = 10  # 10 seconds timeout
            start_time = time.time()
            while not self.session_ready and time.time() - start_time < timeout:
                await asyncio.sleep(0.1)
            
            if not self.session_ready:
                raise RuntimeError("Failed to establish WebSocket connection")

    def send_event(self, event_data):
        """Send an event to the WebSocket server"""
        if not self.ws or not self.ws.sock or not self.ws.sock.connected:
            raise RuntimeError("WebSocket not connected")
        try:
            self.ws.send(json.dumps(event_data))
        except Exception as e:
            print(f"Error sending event: {e}")
            raise

    async def send_user_message(self, message):
        """Send a user message asynchronously"""
        await self.ensure_connection()
        
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": message,
                    }
                ]
            }
        }
        self.send_event(event)

    async def request_response(self):
        """Request a response asynchronously"""
        await self.ensure_connection()
        
        self.response_in_progress = True
        self.current_response = ""
        
        event = {
            "type": "response.create",
            "response": {
                "modalities": ["text"]
            }
        }
        self.send_event(event)

    def update_session_instructions(self, instructions):
        event = {
            "type": "session.update",
            "session": {
                "instructions": instructions
            }
        }
        self.send_event(event)

    def on_open(self, ws):
        print("✓ Connected to OpenAI Realtime API")

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if "type" in data:
                event_type = data["type"]

                if event_type == "session.created":
                    self.session_ready = True
                    self.connection_event.set()

                elif event_type == "response.text.delta":
                    if not self.interrupted:
                        text_delta = data.get("delta", "")
                        if text_delta:
                            self.current_delta = text_delta
                            self.delta_buffer.append(text_delta)  # Add to buffer
                            self.current_response += text_delta

                elif event_type == "response.done":
                    if len(self.delta_buffer) > 0:
                        # Join all deltas into one final delta before marking as complete
                        self.current_delta = "".join(self.delta_buffer)
                        self.delta_buffer = []  # Clear buffer
                    self.response_in_progress = False
                    self.interrupted = False

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
        except Exception as e:
            print(f"Error processing message: {e}")

    def on_error(self, ws, error):
        print(f"Error: {error}")
        self.connection_event.set()  # Unblock waiting threads

    def on_close(self, ws, close_status_code, close_msg):
        print(f"Connection closed: {close_status_code} - {close_msg}")
        self.session_ready = False
        self.connection_event.set()  # Unblock waiting threads

    def interrupt_response(self):
        if self.response_in_progress:
            self.interrupted = True
            self.response_in_progress = False
            return True
        return False

    async def handle_voice_input(self, text):
        if self.response_in_progress:
            self.interrupt_response()
        await self.send_user_message(text)
        await self.request_response()

    def start(self):
        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(
            url,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
        
        return wst

    def stop(self):
        if self.ws:
            self.ws.close()
            self.session_ready = False

def main():
    chat_system = ChatSystem()
    
    try:
        # Start the chat system
        wst = chat_system.start()
        
        # Wait for threads to complete
        try:
            while wst.is_alive():
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nInterrupted by user, shutting down...")
            chat_system.stop()
    finally:
        # Always restore terminal settings when exiting
        chat_system.stop()

if __name__ == "__main__":
    print("Starting OpenAI Realtime Chat...")
    print("Connecting to OpenAI Realtime API...")
    main()