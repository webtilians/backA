import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from langchain_openai import ChatOpenAI

# --- Carga de Variables de Entorno (Buena Práctica) ---
# from dotenv import load_dotenv
# load_dotenv()

# --- Instancias Principales ---
llm = ChatOpenAI(model="gpt-4-turbo", temperature=0)

# 1. FastAPI app
app = FastAPI(title="API del Chatbot de aselvia")

# 2. Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Endpoints HTTP (FastAPI) ---
@app.get("/")
def read_root():
    """Endpoint de prueba para verificar que el servidor FastAPI está funcionando."""
    return {"message": "Hola Mundo desde FastAPI + Socket.IO!"}

# Puedes agregar aquí otros endpoints si los necesitas...

# --- Socket.IO ---
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")

# --- Eventos de Socket.IO ---
@sio.event
async def connect(sid, environ):
    """Se ejecuta cuando un nuevo cliente se conecta."""
    print(f"Cliente conectado: {sid}")

@sio.event
async def disconnect(sid):
    """Se ejecuta cuando un cliente se desconecta."""
    print(f"Cliente desconectado: {sid}")

@sio.event
async def user_message(sid, data):
    """
    Escucha el evento 'user_message' enviado desde el cliente.
    Procesa el mensaje con LangChain y devuelve la respuesta.
    """
    print(f"Mensaje recibido de {sid}: {data}")
    response_message = await llm.ainvoke(data)
    await sio.emit("bot-message", response_message.content, to=sid)

# --- Montaje de la Aplicación ASGI ---
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)

# Para Railway o uvicorn, usa:
# uvicorn main:asgi_app
