from fastapi import APIRouter, Response, WebSocket, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from twilio.twiml.voice_response import VoiceResponse
from typing import Dict
import asyncio
import json
from LLM import ChatSystem
from STT import SpeechToText

router = APIRouter()
chat_system = ChatSystem()
stt_system = SpeechToText()

@router.get("/answer")
def read_root():
    resp = VoiceResponse()
    resp.say("Thank you for calling! Have a great day.", voice='Polly.Amy')
    return Response(content=str(resp), media_type="application/xml")

@router.post("/chat/text")
async def send_message(message: Dict[str, str]):
    if not message.get("text"):
        raise HTTPException(status_code=400, detail="Message text is required")
    
    async def event_generator():
        try:
            # Send message and get response
            await chat_system.send_user_message(message["text"])
            await chat_system.request_response()
            
            last_sent = ""
            while chat_system.response_in_progress:
                if chat_system.current_delta and chat_system.current_delta != last_sent:
                    yield f"data: {json.dumps({'delta': chat_system.current_delta})}\n\n"
                    last_sent = chat_system.current_delta
                await asyncio.sleep(0.1)
            
            # If there's any remaining content in the buffer, send it
            if chat_system.current_delta and chat_system.current_delta != last_sent:
                yield f"data: {json.dumps({'delta': chat_system.current_delta})}\n\n"
            
            # Send end message with complete response
            yield f"data: {json.dumps({'done': True, 'full_response': chat_system.current_response})}\n\n"
        except RuntimeError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.websocket("/chat/voice")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Initialize STT with callback that sends to chat
    async def voice_callback(transcript):
        if transcript:
            await chat_system.handle_voice_input(transcript)
            # Stream the response back
            last_sent = ""
            while chat_system.response_in_progress:
                if chat_system.current_delta and chat_system.current_delta != last_sent:
                    await websocket.send_text(json.dumps({
                        'type': 'response_delta',
                        'delta': chat_system.current_delta
                    }))
                    last_sent = chat_system.current_delta
                await asyncio.sleep(0.1)
            
            # If there's any remaining content in the buffer, send it
            if chat_system.current_delta and chat_system.current_delta != last_sent:
                await websocket.send_text(json.dumps({
                    'type': 'response_delta',
                    'delta': chat_system.current_delta
                }))
            
            # Send complete response
            await websocket.send_text(json.dumps({
                'type': 'response_complete',
                'response': chat_system.current_response
            }))
    
    stt_system.on_transcription = voice_callback
    
    if not stt_system.start():
        await websocket.close(code=1001, reason="Failed to start STT system")
        return
    
    try:
        while True:
            data = await websocket.receive_bytes()
            # Process audio data through STT system
            stt_system.process_audio(data)
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        stt_system.stop()

@router.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_config():
    """Handle Chrome DevTools protocol configuration requests"""
    return JSONResponse(content={
        "version": "1.1",
        "server": "TalkBot-AI"
    })