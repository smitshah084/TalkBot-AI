from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio

clients = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    print("🚀 FastAPI server is starting...")
    yield
    # Shutdown logic
    print("🛑 FastAPI server is shutting down...")
    for ws in clients:
        try:
            await ws.close()
        except:
            pass
    print("✅ Cleaned up WebSocket clients.")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get():
    with open("static/index.html") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    print("Client connected")
    try:
        while True:
            data = await websocket.receive_bytes()
            
            # Check if this is the end signal
            if data.startswith(b"_END_") or data == b"_END_":
                print("End of stream received")
                break
                
            print("Received PCM16 chunk of", len(data), "bytes")
            await asyncio.sleep(0.1)  # Simulate processing
            await websocket.send_text("Transcribed: ...")
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        clients.discard(websocket)
        try:
            await websocket.close()
        except:
            pass  # Already closed
        print("Client connection closed")