import json
import os
import websocket
import threading
import time
import readline  # For better command line input handling
import sys
import select
import tty
import termios
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
user_input_buffer = ""
interrupted = False
original_terminal_settings = None

def save_terminal_settings():
    """Save the terminal settings to restore later."""
    global original_terminal_settings
    if sys.stdin.isatty():
        original_terminal_settings = termios.tcgetattr(sys.stdin)

def set_raw_input_mode():
    """Set the terminal to raw mode to capture keystrokes without requiring Enter."""
    if sys.stdin.isatty():
        tty.setraw(sys.stdin.fileno(), termios.TCSANOW)

def restore_terminal_settings():
    """Restore the original terminal settings."""
    global original_terminal_settings
    if sys.stdin.isatty() and original_terminal_settings:
        termios.tcsetattr(sys.stdin, termios.TCSANOW, original_terminal_settings)

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
    global session_ready, response_in_progress, current_response, debug_mode, interrupted

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
                # Only print the delta if not interrupted
                if not interrupted:
                    text_delta = data.get("delta", "")
                    if text_delta:
                        print(text_delta, end="", flush=True)
                        current_response += text_delta

            elif event_type == "response.done":
                response_in_progress = False
                if not interrupted:
                    print("\n\n--- Response complete ---\n")
                interrupted = False

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

def interrupt_response():
    """Interrupt the current response generation."""
    global response_in_progress, interrupted
    
    if response_in_progress:
        # Mark as interrupted to stop processing further deltas
        interrupted = True
        response_in_progress = False
        print("\n\n--- Response interrupted ---\n")
        return True
    return False

def key_watcher_thread():
    """Thread function to watch for keypresses during response generation."""
    global user_input_buffer, response_in_progress, interrupted
    
    while True:
        try:
            # Only check for keystrokes if we're in response mode
            if response_in_progress and sys.stdin.isatty():
                # Check if there's data ready to be read
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    char = sys.stdin.read(1)
                    
                    # If any key is pressed while the model is responding
                    if char:
                        # Interrupt the current response
                        if interrupt_response():
                            # Store this character as the beginning of the next input
                            user_input_buffer = char
                            # Reset terminal to normal mode to collect the rest of the input
                            restore_terminal_settings()
                            # Print a new line for user input
                            print("You: " + char, end="", flush=True)
                            # Wait a bit for the terminal to normalize
                            time.sleep(0.1)
                            break
            
            # Sleep to avoid high CPU usage
            time.sleep(0.1)
                
        except Exception as e:
            print(f"Error in key watcher: {e}")
            time.sleep(1)  # Sleep on error to avoid spinning

def input_thread_function():
    """Thread function to handle user input."""
    global ws, session_ready, debug_mode, user_input_buffer, response_in_progress
    
    while True:
        # Wait for session to be ready before accepting input
        if not session_ready:
            time.sleep(0.5)
            continue
            
        # Wait if a response is currently being generated
        if response_in_progress:
            # Start a key watcher thread when in response mode
            key_thread = threading.Thread(target=key_watcher_thread)
            key_thread.daemon = True
            key_thread.start()
            
            # Wait for the key watcher to finish or response to complete
            while response_in_progress and key_thread.is_alive():
                time.sleep(0.1)
            
            # If we've been interrupted, collect the rest of the input
            if user_input_buffer:
                # Get the rest of the input after the first character
                rest_of_input = input("")
                user_input = user_input_buffer + rest_of_input
                user_input_buffer = ""
            else:
                continue
        else:
            try:
                # Set terminal to normal mode for regular input
                restore_terminal_settings()
                user_input = input("\nYou: ")
            except EOFError:
                print("\nExiting due to EOF...")
                ws.close()
                break
            
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
        
        # Set terminal to raw mode to capture keypresses during response
        set_raw_input_mode()

def main():
    global ws
    
    try:
        # Save original terminal settings
        save_terminal_settings()
        
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
            print("\nInterrupted by user, shutting down...")
            ws.close()
    finally:
        # Always restore terminal settings when exiting
        restore_terminal_settings()

if __name__ == "__main__":
    print("Starting OpenAI Realtime Chat...")
    print("Connecting to OpenAI Realtime API...")
    main()