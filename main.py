import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from langchain_openai import ChatOpenAI

# --- Carga de Variables de Entorno (Buena Práctica) ---
# Descomenta las siguientes líneas si usas un archivo .env para tus claves de API
# from dotenv import load_dotenv
# load_dotenv()

# --- Instancias Principales ---
# 1. Servidor Socket.IO en modo asíncrono ASGI
#    cors_allowed_origins="*" permite conexiones desde cualquier origen.
#    Para producción, es mejor restringirlo a tu dominio de frontend.
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")

# 2. Aplicación FastAPI
app = FastAPI()

# 3. Modelo de Lenguaje de LangChain
llm = ChatOpenAI()

# --- Middlewares ---
# Se añade el middleware de CORS a FastAPI para manejar las peticiones HTTP
# y la negociación inicial de Socket.IO.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Orígenes permitidos
    allow_credentials=True,  # Permite cookies y cabeceras de autorización
    allow_methods=["*"],  # Métodos HTTP permitidos (GET, POST, etc.)
    allow_headers=["*"],  # Cabeceras HTTP permitidas
)

# --- Montaje de la Aplicación ASGI ---
# Se combina el servidor de Socket.IO con la aplicación FastAPI.
# La aplicación resultante se reasigna a la variable 'app'.
# Esto simplifica la ejecución, permitiendo usar 'uvicorn main:app'.
app = socketio.ASGIApp(sio, other_asgi_app=app)


# --- Endpoints HTTP (FastAPI) ---
@app.get("/")
def read_root():
    """Endpoint de prueba para verificar que el servidor FastAPI está funcionando."""
    return {"message": "Hola Mundo desde FastAPI + Socket.IO!"}


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
    
    # ¡IMPORTANTE! Se usa 'ainvoke' para la llamada asíncrona al modelo.
    # Esto evita bloquear el servidor y permite atender a múltiples clientes
    # de forma concurrente.
    response_message = await llm.ainvoke(data)
    
    # El resultado de 'ainvoke' es un objeto (ej. AIMessage).
    # Se extrae el contenido de texto para enviarlo de vuelta.
    await sio.emit("bot-message", response_message.content, to=sid)

