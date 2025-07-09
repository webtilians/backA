import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from langchain_openai import ChatOpenAI

# Cargar variables de entorno
load_dotenv()

# Crear instancia de Socket.IO server ASGI
sio = socketio.AsyncServer(cors_allowed_origins="*")
app = FastAPI()
llm = ChatOpenAI()

# Añadir CORS a FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar Socket.IO sobre FastAPI
sio_app = socketio.ASGIApp(sio, app)

@app.get("/")
def read_root():
    return {"message": "Hola Mundo desde FastAPI!"}

# Eventos de Socket.IO

@sio_app.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")

@sio_app.event
async def disconnect(sid):
    print(f"Cliente desconectado: {sid}")

@sio_app.event
async def user_message(sid, data):
    print(f"Recibido mensaje: {data}")
    # Llama al modelo OpenAI y responde al usuario
    try:
        response = llm.predict(data)
        await sio.emit("bot-message", response, to=sid)
    except Exception as e:
        error_msg = f"Error al procesar mensaje: {e}"
        print(error_msg)
        await sio.emit("bot-message", error_msg, to=sid)
