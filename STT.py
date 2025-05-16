import os
import json
import websocket
import base64
import pyaudio
import time
import threading
import queue
import requests
import logging
from typing import Optional, Tuple, Generator


class STT:
    """Speech-to-Text class using OpenAI's realtime transcription API"""
    
    def __init__(self, api_key: Optional[str] = None, log_level=logging.INFO):
        """Initialize the STT class
        
        Args:
            api_key: OpenAI API key. If None, will try to get from OPENAI_API_KEY env var
            log_level: Logging level
        """
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        if not self.logger.handlers:
            # Create logs directory if it doesn't exist
            os.makedirs('logs', exist_ok=True)
            
            # Setup file handler with a rotating file handler
            log_file = os.path.join('logs', 'stt.log')
            handler = logging.FileHandler(log_file)
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
            # Prevent logs from propagating to the root logger (console)
            self.logger.propagate = False
                
        # API configuration
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            self.logger.error("No OpenAI API key provided")
            raise ValueError("OpenAI API key is required. Provide it as an argument or set OPENAI_API_KEY environment variable.")
        
        # Audio configuration
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        
        # State variables
        self.session_created = False
        self.speech_started = None
        self.speech_stopped = None
        self.keep_running = False
        
        # Stream queues
        self.audio_queue = queue.Queue()
        self.delta_transcript_queue = queue.Queue()
        self.full_transcript_queue = queue.Queue()
        
        # WebSocket and threads
        self.ws = None
        self.ws_thread = None
        self.audio_thread = None
        self.transmit_thread = None
        
    def get_ephemeral_token(self):
        """Get an ephemeral token from OpenAI for the realtime API"""
        url = "https://api.openai.com/v1/realtime/transcription_sessions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "openai-beta": "realtime=v1"  # Required header
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

        self.logger.info("Requesting ephemeral token")
        response = requests.post(url, headers=headers, json=body)
        
        if response.status_code == 200:
            self.logger.info("Successfully obtained ephemeral token")
            return response.json()["client_secret"]["value"]
        else:
            self.logger.error(f"Failed to fetch ephemeral token: {response.text}")
            return None

    def on_open(self, ws):
        """WebSocket open callback"""
        self.logger.info("Connected to OpenAI realtime API")

    def on_message(self, ws, message):
        """WebSocket message callback"""
        data = json.loads(message)
        type_ = data.get('type')
        
        if type_ == 'transcription_session.created':
            self.session_created = True
            self.logger.info("Transcription session created")
        
        elif type_ == 'input_audio_buffer.speech_started':
            self.speech_started = data.get('audio_start_ms')
            self.logger.info(f'Speech started at {self.speech_started} ms')
            
        elif type_ == 'input_audio_buffer.speech_stopped':
            self.speech_stopped = data.get('audio_end_ms')
            self.logger.info(f'Speech ended at {self.speech_stopped} ms')
            
        elif type_ == 'input_audio_buffer.committed':
            self.logger.debug("Audio buffer committed")
            
        elif type_ == 'conversation.item.input_audio_transcription.delta':
            delta = data.get('delta')
            self.logger.debug(f"Transcription delta: {delta}")
            self.delta_transcript_queue.put(delta)
            
        elif type_ == 'conversation.item.input_audio_transcription.completed':
            transcript = data.get('transcript')
            self.logger.info(f"Full transcript: {transcript}")
            self.full_transcript_queue.put(transcript)
        
        elif type_ == 'conversation.item.created':
            self.logger.debug("Conversation item created")
        
        else:
            self.logger.debug(f"Received unknown event: {json.dumps(data, indent=2)}")

    def on_error(self, ws, error):
        """WebSocket error callback"""
        self.logger.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket close callback"""
        self.logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
        self.keep_running = False

    def record_audio(self):
        """Record audio from microphone and put chunks in queue"""
        self.logger.info("Starting audio recording")
        audio = pyaudio.PyAudio()
        stream = audio.open(format=self.FORMAT, channels=self.CHANNELS,
                        rate=self.RATE, input=True, frames_per_buffer=self.CHUNK)
        
        try:
            while self.keep_running:
                audio_chunk = stream.read(self.CHUNK, exception_on_overflow=False)
                self.audio_queue.put(audio_chunk)
        except Exception as e:
            self.logger.error(f"Error recording audio: {e}")
        finally:
            self.logger.info("Stopping audio recording")
            stream.stop_stream()
            stream.close()
            audio.terminate()
            self.audio_queue.put(None)  # Send sentinel value

    def transmit_audio(self):
        """Transmit audio chunks from queue to websocket"""
        self.logger.info("Starting audio transmission")
        try:
            while self.keep_running:
                audio_chunk = self.audio_queue.get(timeout=1)
                if audio_chunk is None:
                    break  # Stop if sentinel received
                    
                audio_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                audio_payload = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_base64
                }
                try:
                    self.ws.send(json.dumps(audio_payload))
                except websocket.WebSocketConnectionClosedException:
                    self.logger.error("WebSocket closed. Stopping transmission.")
                    break
                except Exception as e:
                    self.logger.error(f"Error transmitting audio: {e}")
                    break
        except queue.Empty:
            pass  # Timeout on queue.get, continue loop
        except Exception as e:
            self.logger.error(f"Unexpected error in transmit_audio: {e}")
        finally:
            self.logger.info("Audio transmission stopped")

    def delta_stream(self):
        """Generator for delta transcription stream"""
        while self.keep_running:
            try:
                delta = self.delta_transcript_queue.get(timeout=0.5)
                yield delta
            except queue.Empty:
                continue  # No new delta, continue loop

    def full_transcript_stream(self):
        """Generator for full transcript stream"""
        while self.keep_running:
            try:
                transcript = self.full_transcript_queue.get(timeout=0.5)
                yield transcript
            except queue.Empty:
                continue  # No new transcript, continue loop

    def start(self) -> Tuple[Generator, Generator]:
        """Start the STT service
        
        Returns:
            Tuple of (delta_stream, full_transcript_stream) generators
        """
        self.logger.info("Starting STT service")
        
        # Get token for websocket
        token = self.get_ephemeral_token()
        if not token:
            self.logger.error("Failed to obtain token. Cannot start STT.")
            raise RuntimeError("Failed to obtain ephemeral token from OpenAI")
        
        # Set running flag
        self.keep_running = True
        self.session_created = False
        
        # Initialize WebSocket
        url = "wss://api.openai.com/v1/realtime?intent=transcription"
        headers = [
            f"Authorization: Bearer {token}",
            "OpenAI-Beta: realtime=v1"
        ]
        
        self.ws = websocket.WebSocketApp(
            url,
            header=headers,
            on_open=lambda ws: self.on_open(ws),
            on_message=lambda ws, msg: self.on_message(ws, msg),
            on_error=lambda ws, err: self.on_error(ws, err),
            on_close=lambda ws, status, msg: self.on_close(ws, status, msg)
        )
        
        # Start WebSocket thread
        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()
        
        # Wait for session to be created
        start_time = time.time()
        while not self.session_created and time.time() - start_time < 10:
            time.sleep(0.1)
        
        if not self.session_created:
            self.logger.error("Timed out waiting for session creation")
            self.stop()
            raise RuntimeError("Timed out waiting for session creation")
        
        # Start audio recording and transmission threads
        self.audio_thread = threading.Thread(target=self.record_audio)
        self.audio_thread.daemon = True
        self.audio_thread.start()
        
        self.transmit_thread = threading.Thread(target=self.transmit_audio)
        self.transmit_thread.daemon = True
        self.transmit_thread.start()
        
        # Return stream generators
        return self.delta_stream(), self.full_transcript_stream()
    
    def stop(self):
        """Stop the STT service"""
        self.logger.info("Stopping STT service")
        self.keep_running = False
        
        if self.ws:
            self.ws.close()
        
        # Wait for threads to finish
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)
        
        if self.transmit_thread and self.transmit_thread.is_alive():
            self.transmit_thread.join(timeout=2)
        
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2)
            
        self.logger.info("STT service stopped")


if __name__ == "__main__":
    stt = STT(log_level=logging.INFO)
    
    try:
        # Start STT and get stream generators
        delta_stream, full_transcript_stream = stt.start()
        
        # Print deltas as they come
        delta_thread = threading.Thread(target=lambda: [print(d, end='', flush=True) for d in delta_stream])
        delta_thread.daemon = True
        delta_thread.start()
        
        # Print full transcripts as they come
        full_thread = threading.Thread(target=lambda: [print(f"\nFULL: {t}", flush=True) for t in full_transcript_stream])
        full_thread.daemon = True
        full_thread.start()
        
        # Keep running until user interrupts
        print("Recording... Press Ctrl+C to stop.")
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stt.stop()