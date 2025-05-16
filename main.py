import os
import json
import asyncio
import logging
import signal
from typing import List, Dict, Any
import base64

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from STT import STT

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="logs/main.log",
    filemode="a"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI()

# Setup templates
templates = Jinja2Templates(directory=".")

# Active WebSocket connections
active_connections: List[WebSocket] = []
# STT instances for each connection
stt_instances: Dict[str, STT] = {}

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Serve the index.html page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    """WebSocket endpoint for audio streaming and transcript receiving"""
    # Accept connection
    await websocket.accept()
    connection_id = str(id(websocket))
    active_connections.append(websocket)
    
    try:
        # Create STT instance for this connection
        logger.info(f"Creating STT instance for connection {connection_id}")
        stt = STT(log_file=f"logs/stt_{connection_id}.log")
        stt_instances[connection_id] = stt
        
        # Start STT with external audio
        delta_stream, full_stream = stt.start(use_external_audio=True)
        
        # Start tasks for sending transcripts
        delta_task = asyncio.create_task(send_delta_transcripts(websocket, delta_stream, connection_id))
        full_task = asyncio.create_task(send_full_transcripts(websocket, full_stream, connection_id))
        
        # Send status message
        await websocket.send_text(json.dumps({
            "type": "status",
            "message": "STT service started. You can begin speaking."
        }))
        
        # Receive audio data from client
        while True:
            # Receive binary data (PCM16 audio)
            data = await websocket.receive_bytes()
            
            # Feed data to STT
            if not stt.feed_audio(data):
                break
            
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "status",
                "message": f"Error: {str(e)}"
            }))
        except Exception as e:
            logger.error('error caught in line 87', e)
    finally:
        # Clean up
        if connection_id in stt_instances:
            stt_instances[connection_id].stop()
            del stt_instances[connection_id]
        
        if websocket in active_connections:
            active_connections.remove(websocket)
            
        try:
            delta_task.cancel()
            full_task.cancel()
        except:
            pass

async def send_delta_transcripts(websocket: WebSocket, delta_stream, connection_id: str):
    """Send delta transcripts to the client"""
    try:
        for delta in delta_stream:
            if websocket.client_state.CONNECTED:
                await websocket.send_text(json.dumps({
                    "type": "delta",
                    "text": delta
                }))
    except asyncio.CancelledError:
        logger.info(f"Delta transcript task cancelled for {connection_id}")
    except Exception as e:
        logger.error(f"Error sending delta transcripts: {e}")

async def send_full_transcripts(websocket: WebSocket, full_stream, connection_id: str):
    """Send full transcripts to the client"""
    try:
        for transcript in full_stream:
            if websocket.client_state.CONNECTED:
                await websocket.send_text(json.dumps({
                    "type": "full",
                    "text": transcript
                }))
    except asyncio.CancelledError:
        logger.info(f"Full transcript task cancelled for {connection_id}")
    except Exception as e:
        logger.error(f"Error sending full transcripts: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    for connection_id, stt in stt_instances.items():
        logger.info(f"Stopping STT instance for connection {connection_id}")
        stt.stop()
    stt_instances.clear()

# Add signal handlers
def handle_shutdown(signum, frame):
    logger.info("Received shutdown signal. Cleaning up...")
    for connection_id, stt in stt_instances.items():
        stt.stop()
    stt_instances.clear()

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

if __name__ == "__main__":
    if not os.path.exists("logs"):
        os.makedirs("logs")
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        logger.info("Server stopped by keyboard interrupt")
    finally:
        handle_shutdown(None, None)