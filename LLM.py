import json
import os
import websocket
import threading
import time
import readline
import sys
import select
import tty
import termios
from dotenv import load_dotenv
from typing import Optional, Iterator, Callable, Dict, Any, Tuple, List, Union


class OpenAIRealtimeChat:
    """A class to interact with OpenAI's Realtime API."""
    
    def __init__(self, model="gpt-4o-mini-realtime-preview-2024-12-17", debug_mode=False, 
                 input_mode="terminal", input_stream=None, input_callback=None):
        """Initialize the chat client.
        
        Args:
            model (str): The model to use for the conversation
            debug_mode (bool): Whether to enable debug mode
            input_mode (str): The input mode to use ('terminal', 'stream', or 'callback')
            input_stream (Iterator[str], optional): An iterator that yields input strings
            input_callback (Callable[[], str], optional): A function that returns input strings
        """
        # Load environment variables
        load_dotenv()
        
        # Get API key from environment variables
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_key = os.environ.get("OPENAI_API_KEY", self.api_key)
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found. Make sure it's set in your environment or .env file.")
        
        # WebSocket URL and headers
        self.url = f"wss://api.openai.com/v1/realtime?model={model}"
        self.headers = [
            f"Authorization: Bearer {self.api_key}",
            "OpenAI-Beta: realtime=v1"
        ]
        
        # Instance variables
        self.ws = None
        self.session_ready = False
        self.response_in_progress = False
        self.current_response = ""
        self.debug_mode = debug_mode
        self.user_input_buffer = ""
        self.interrupted = False
        self.original_terminal_settings = None
        
        # Input configuration
        self.input_mode = input_mode
        self.input_stream = input_stream
        self.input_callback = input_callback
        self.stream_thread = None
        self.stream_active = False
        self.input_queue = []
        self.input_queue_lock = threading.Lock()
        self.new_input_event = threading.Event()
        self.should_exit = threading.Event()
        
        # WebSocket event handlers
        self.ws_handlers = {
            "on_open": self.on_open,
            "on_message": self.on_message,
            "on_error": self.on_error,
            "on_close": self.on_close
        }
        
    def save_terminal_settings(self):
        """Save the terminal settings to restore later."""
        if sys.stdin.isatty():
            self.original_terminal_settings = termios.tcgetattr(sys.stdin)
            
    def add_input_to_queue(self, input_text: str) -> None:
        """Add input text to the processing queue.
        
        Args:
            input_text (str): The input text to add to the queue
        """
        if not input_text or not input_text.strip():
            return
            
        with self.input_queue_lock:
            self.input_queue.append(input_text.strip())
            self.new_input_event.set()
    
    def process_stream_input(self) -> None:
        """Process input from a stream source."""
        if self.input_stream is None:
            print("Error: No input stream provided")
            return
            
        self.stream_active = True
        try:
            for text in self.input_stream:
                if self.should_exit.is_set():
                    break
                
                # Only process non-empty text that has changed from the last input
                if text and text.strip():
                    self.add_input_to_queue(text)
                    
                time.sleep(0.1)  # Small delay to avoid spinning too fast
                
        except Exception as e:
            print(f"Error processing stream input: {e}")
        finally:
            self.stream_active = False
    
    def process_callback_input(self) -> None:
        """Process input from a callback function."""
        if self.input_callback is None:
            print("Error: No input callback provided")
            return
            
        self.stream_active = True
        try:
            while not self.should_exit.is_set():
                try:
                    text = self.input_callback()
                    if text is not None:
                        self.add_input_to_queue(text)
                except Exception as e:
                    print(f"Error getting input from callback: {e}")
                    
                time.sleep(0.1)  # Small delay to avoid spinning too fast
                
        finally:
            self.stream_active = False
    
    def set_raw_input_mode(self):
        """Set the terminal to raw mode to capture keystrokes without requiring Enter."""
        if sys.stdin.isatty():
            tty.setraw(sys.stdin.fileno(), termios.TCSANOW)
    
    def restore_terminal_settings(self):
        """Restore the original terminal settings."""
        if sys.stdin.isatty() and self.original_terminal_settings:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, self.original_terminal_settings)
    
    def send_event(self, event_data):
        """Send an event to the WebSocket server.
        
        Args:
            event_data (dict): The event data to send
        """
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self.ws.send(json.dumps(event_data))
        else:
            print("WebSocket not connected. Cannot send event.")
    
    def send_user_message(self, message):
        """Send a user message to the conversation.
        
        Args:
            message (str): The message to send
        """
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
        print("\nSending message to model...\n")
    
    def request_response(self):
        """Request a response from the model."""
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
        """Update the session instructions.
        
        Args:
            instructions (str): The new instructions
        """
        event = {
            "type": "session.update",
            "session": {
                "instructions": instructions
            }
        }
        self.send_event(event)
        print(f"Updating session instructions...")
    
    def on_open(self, ws):
        """Callback when WebSocket connection is established."""
        print("✓ Connected to OpenAI Realtime API")
        print("Enter your message (type '/exit' to quit, '/help' for commands):")
    
    def on_message(self, ws, message):
        """Callback when a message is received from the server."""
        try:
            data = json.loads(message)
            
            # Check the type of event
            if "type" in data:
                event_type = data["type"]
                
                if event_type == "session.created":
                    self.session_ready = True
                    print("✓ Session created and ready")
                
                elif event_type == "session.updated":
                    print("✓ Session instructions updated")
                
                elif event_type == "response.text.delta":
                    # Only print the delta if not interrupted
                    if not self.interrupted:
                        if self.current_response != '':
                            text_delta = 'MODEL: '
                        text_delta = data.get("delta", "")
                        if text_delta:
                            print(text_delta, end="", flush=True)
                            self.current_response += text_delta
                
                elif event_type == "response.done":
                    self.response_in_progress = False
                    if not self.interrupted:
                        print("\n\n--- Response complete ---\n")
                    self.interrupted = False
            
            if self.debug_mode:
                print(f"DEBUG: {data}")
                
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            print(f"Raw message: {message}")
        except Exception as e:
            print(f"Error processing message: {e}")
            print(f"Message that caused error: {message}")
    
    def on_error(self, ws, error):
        """Callback for WebSocket errors."""
        print(f"Error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Callback when WebSocket connection is closed."""
        print(f"Connection closed: {close_status_code} - {close_msg}")
    
    def interrupt_response(self):
        """Interrupt the current response generation."""
        if self.response_in_progress:
            # Mark as interrupted to stop processing further deltas
            self.interrupted = True
            self.response_in_progress = False
            print("\n\n--- Response interrupted ---\n")
            return True
        return False
    
    def key_watcher_thread(self):
        """Thread function to watch for keypresses during response generation."""
        while True:
            try:
                # Only check for keystrokes if we're in response mode
                if self.response_in_progress and sys.stdin.isatty():
                    # Check if there's data ready to be read
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        char = sys.stdin.read(1)
                        
                        # If any key is pressed while the model is responding
                        if char:
                            # Interrupt the current response
                            if self.interrupt_response():
                                # Store this character as the beginning of the next input
                                self.user_input_buffer = char
                                # Reset terminal to normal mode to collect the rest of the input
                                self.restore_terminal_settings()
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
    
    def input_thread_function(self):
        """Thread function to handle user input."""
        # Start the appropriate input processor based on the input_mode
        if self.input_mode == "stream" and self.input_stream is not None:
            self.stream_thread = threading.Thread(target=self.process_stream_input)
            self.stream_thread.daemon = True
            self.stream_thread.start()
        elif self.input_mode == "callback" and self.input_callback is not None:
            self.stream_thread = threading.Thread(target=self.process_callback_input)
            self.stream_thread.daemon = True
            self.stream_thread.start()
        
        while True:
            # Wait for session to be ready before accepting input
            if not self.session_ready:
                time.sleep(0.5)
                continue
            
            # Check if there's input in the queue from streams or callbacks
            input_from_queue = None
            if self.input_mode in ["stream", "callback"]:
                with self.input_queue_lock:
                    if self.input_queue:
                        input_from_queue = self.input_queue.pop(0)
                        if not self.input_queue:
                            self.new_input_event.clear()
            
            # Wait if a response is currently being generated
            if self.response_in_progress:
                # Start a key watcher thread when in response mode (only for terminal mode)
                if self.input_mode == "terminal":
                    key_thread = threading.Thread(target=self.key_watcher_thread)
                    key_thread.daemon = True
                    key_thread.start()
                    
                    # Wait for the key watcher to finish or response to complete
                    while self.response_in_progress and key_thread.is_alive():
                        time.sleep(0.1)
                    
                    # If we've been interrupted, collect the rest of the input
                    if self.user_input_buffer:
                        # Get the rest of the input after the first character
                        rest_of_input = input("")
                        user_input = self.user_input_buffer + rest_of_input
                        self.user_input_buffer = ""
                    else:
                        # If no input from terminal, check queue
                        if input_from_queue:
                            user_input = input_from_queue
                        else:
                            continue
                else:
                    # For non-terminal modes, just wait for the response to complete
                    while self.response_in_progress:
                        time.sleep(0.1)
                    
                    # After response, use queued input if available
                    if input_from_queue:
                        user_input = input_from_queue
                    else:
                        # Wait for the next input event with a timeout
                        self.new_input_event.wait(0.5)
                        continue
            else:
                # Not in response mode
                if self.input_mode == "terminal":
                    try:
                        # Set terminal to normal mode for regular input
                        self.restore_terminal_settings()
                        user_input = input("\nYou: ")
                    except EOFError:
                        print("\nExiting due to EOF...")
                        self.ws.close()
                        break
                else:
                    # For non-terminal modes, use queued input if available
                    if input_from_queue:
                        user_input = input_from_queue
                        print(f"\nYou: {user_input}")
                    else:
                        # Wait for the next input event with a timeout
                        self.new_input_event.wait(0.5)
                        continue
                
            # Check for commands
            if user_input.lower() == '/exit':
                print("Exiting...")
                self.should_exit.set()
                self.ws.close()
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
                self.update_session_instructions(instructions)
                continue
            elif user_input.lower() == '/debug':
                self.debug_mode = not self.debug_mode
                print(f"Debug mode {'enabled' if self.debug_mode else 'disabled'}")
                continue
            elif not user_input.strip():
                continue
                
            # Normal message flow
            self.send_user_message(user_input)
            self.request_response()
            
            # Set terminal to raw mode to capture keypresses during response (terminal mode only)
            if self.input_mode == "terminal":
                self.set_raw_input_mode()
    
    def run(self):
        """Run the chat client."""
        try:
            # Save original terminal settings (only for terminal mode)
            if self.input_mode == "terminal":
                self.save_terminal_settings()
            
            # Set up WebSocket connection
            websocket.enableTrace(self.debug_mode)
            self.ws = websocket.WebSocketApp(
                self.url,
                header=self.headers,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            # Start WebSocket connection in a separate thread
            wst = threading.Thread(target=self.ws.run_forever)
            wst.daemon = True
            wst.start()
            
            # Start input thread
            input_thread = threading.Thread(target=self.input_thread_function)
            input_thread.daemon = True
            input_thread.start()
            
            # Wait for threads to complete
            try:
                while wst.is_alive() and not self.should_exit.is_set():
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nInterrupted by user, shutting down...")
                self.should_exit.set()
                self.ws.close()
        finally:
            # Always restore terminal settings when exiting (only for terminal mode)
            if self.input_mode == "terminal":
                self.restore_terminal_settings()


if __name__ == "__main__":
    # chat_client = OpenAIRealtimeChat(input_mode="terminal")
    # chat_client.run()
    # import sys; sys.exit(0)   
     
    try:
        from STT import STT
        
        stt = STT()
        
        # Start STT and get the full transcript stream
        _, full_transcript_stream = stt.start()
        
        # Create and run the chat client with the stream
        chat_client = OpenAIRealtimeChat(
            input_mode="stream",
            input_stream=full_transcript_stream
        )
        chat_client.run()
        
    except ImportError:
        print("STT module not available. This is just an example.")
    except Exception as e:
        print(f"Error in STT example: {e}")