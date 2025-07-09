import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from langchain_openai import ChatOpenAI

load_dotenv()

# Instancias
sio = socketio.AsyncServer(cors_allowed_origins="*")
app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatOpenAI()

# Móntalo sobre ASGI
sio_app = socketio.ASGIApp(sio, app)

@app.get("/")
def read_root():
    return {"message": "Hola Mundo desde FastAPI!"}

# ------ Socket.IO Handlers ------
@sio.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Cliente desconectado: {sid}")

@sio.event
async def user_message(sid, data):
    print(f"Recibido mensaje: {data}")
    response = llm.predict(data)
    await sio.emit("bot-message", response, to=sid)
