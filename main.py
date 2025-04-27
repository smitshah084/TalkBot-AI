import json
import os
import websocket
import threading
import time
import readline  # For better command line input handling
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

# Global variables
ws = None
session_ready = False
response_in_progress = False
current_response = ""
debug_mode = False

def send_event(event_data):
    """Send an event to the WebSocket server."""
    if ws and ws.sock and ws.sock.connected:
        ws.send(json.dumps(event_data))
    else:
        print("WebSocket not connected. Cannot send event.")

def send_user_message(message):
    """Send a user message to the conversation."""
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
    send_event(event)
    print("\nSending message to model...\n")

def request_response():
    """Request a response from the model."""
    global response_in_progress, current_response
    response_in_progress = True
    current_response = ""
    
    event = {
        "type": "response.create",
        "response": {
            "modalities": ["text"]
        }
    }
    send_event(event)

def update_session_instructions(instructions):
    """Update the session instructions."""
    event = {
        "type": "session.update",
        "session": {
            "instructions": instructions
        }
    }
    send_event(event)
    print(f"Updating session instructions...")

def on_open(ws):
    """Callback when WebSocket connection is established."""
    print("✓ Connected to OpenAI Realtime API")
    print("Enter your message (type '/exit' to quit, '/help' for commands):")

def on_message(ws, message):
    """Callback when a message is received from the server."""
    global session_ready, response_in_progress, current_response, debug_mode

    try:
        data = json.loads(message)

        # Check the type of event
        if "type" in data:
            event_type = data["type"]

            if event_type == "session.created":
                session_ready = True
                print("✓ Session created and ready")

            elif event_type == "session.updated":
                print("✓ Session instructions updated")

            elif event_type == "response.text.delta":
                # Only print the delta (text chunk)
                text_delta = data.get("delta", "")
                if text_delta:
                    print(text_delta, end="", flush=True)  # <-- print immediately
                    current_response += text_delta

            elif event_type == "response.done":
                response_in_progress = False
                print("\n\n--- Response complete ---\n")

    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        print(f"Raw message: {message}")
    except Exception as e:
        print(f"Error processing message: {e}")
        print(f"Message that caused error: {message}")

def on_error(ws, error):
    """Callback for WebSocket errors."""
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    """Callback when WebSocket connection is closed."""
    print(f"Connection closed: {close_status_code} - {close_msg}")

def input_thread_function():
    """Thread function to handle user input."""
    global ws, session_ready, debug_mode
    
    while True:
        # Wait for session to be ready before accepting input
        if not session_ready:
            time.sleep(0.5)
            continue
            
        # Wait if a response is currently being generated
        if response_in_progress:
            time.sleep(0.5)
            continue
            
        try:
            user_input = input("\nYou: ")
            
            # Check for commands
            if user_input.lower() == '/exit':
                print("Exiting...")
                ws.close()
                break
            elif user_input.lower() == '/help':
                print("\nCommands:")
                print("  /exit - Exit the application")
                print("  /help - Show this help message")
                print("  /instructions <text> - Update session instructions")
                print("  /debug - Toggle debug mode")
                continue
            elif user_input.lower().startswith('/instructions '):
                instructions = user_input[14:].strip()
                update_session_instructions(instructions)
                continue
            elif user_input.lower() == '/debug':
                debug_mode = not debug_mode
                print(f"Debug mode {'enabled' if debug_mode else 'disabled'}")
                continue
            elif not user_input.strip():
                continue
                
            # Normal message flow
            send_user_message(user_input)
            request_response()
            
        except KeyboardInterrupt:
            print("\nExiting due to keyboard interrupt...")
            ws.close()
            break

def main():
    global ws
    
    # Set up WebSocket connection
    websocket.enableTrace(False)  # Set to True for debugging
    ws = websocket.WebSocketApp(
        url,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    # Start WebSocket connection in a separate thread
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()
    
    # Start input thread
    input_thread = threading.Thread(target=input_thread_function)
    input_thread.daemon = True
    input_thread.start()
    
    # Wait for threads to complete
    try:
        while wst.is_alive():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Interrupted by user, shutting down...")
        ws.close()

if __name__ == "__main__":
    print("Starting OpenAI Realtime Chat...")
    print("Connecting to OpenAI Realtime API...")
    main()