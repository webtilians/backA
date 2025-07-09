import os
from dotenv import load_dotenv
from fastapi import FastAPI
import socketio
from langchain_openai import ChatOpenAI

load_dotenv()

# Crea el servidor socketio
sio = socketio.AsyncServer(cors_allowed_origins="*")
app = FastAPI()
llm = ChatOpenAI()

# Monta SocketIO en FastAPI
import socketio
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request

# Middlewares CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Socket.IO ASGI app
sio_app = socketio.ASGIApp(sio, app)

@app.get("/")
def read_root():
    return {"message": "Hola Mundo desde FastAPI!"}

@sio.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Cliente desconectado: {sid}")

@sio.event
async def user_message(sid, data):
    # Recibe mensaje del usuario
    print(f"Recibido mensaje: {data}")
    response = llm.predict(data)
    await sio.emit("bot-message", response, to=sid)

# ¡Recuerda arrancar el servidor con Uvicorn usando la app de SocketIO!
# uvicorn main:sio_app --host 0.0.0.0 --port 8000
