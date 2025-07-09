import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import socketio
from langchain_openai import ChatOpenAI

load_dotenv()

# Inicializa FastAPI y Socket.IO
app = FastAPI()
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
llm = ChatOpenAI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Monta Socket.IO sobre FastAPI
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
