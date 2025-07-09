import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from langchain_openai import ChatOpenAI

# Cargar variables de entorno


# Instancias principales
sio = socketio.AsyncServer(cors_allowed_origins="*")
app = FastAPI()
llm = ChatOpenAI()

# Montar CORS en FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar Socket.IO como capa ASGI encima de FastAPI
sio_app = socketio.ASGIApp(sio, app)

# Endpoint básico para probar que FastAPI responde
@app.get("/")
def read_root():
    return {"message": "Hola Mundo desde FastAPI + Socket.IO!"}

# Socket.IO events
@sio.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Cliente desconectado: {sid}")

@sio.event
async def user_message(sid, data):
    print(f"Mensaje recibido de {sid}: {data}")
    response = llm.predict(data)
    await sio.emit("bot-message", response, to=sid)
