import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_openai import ChatOpenAI
import socketio  # <--- IMPORTANTE, ANTES DE USARLO

load_dotenv()

# Crea el servidor socketio
sio = socketio.AsyncServer(cors_allowed_origins="*")
app = FastAPI()
llm = ChatOpenAI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monta SocketIO en FastAPI
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
    print(f"Recibido mensaje: {data}")
    response = llm.predict(data)
    await sio.emit("bot-message", response, to=sid)
