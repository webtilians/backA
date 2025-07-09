import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from langchain_openai import ChatOpenAI
from langchain.tools import tool

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

# --- TOOLS para LangChain ---

@tool
def consultar_disponibilidad(propertyId: int, startDate: str, endDate: str, roomTypeId: int = None) -> list:
    """
    Simula una consulta de disponibilidad para un hotel.
    Devuelve una lista de días con habitaciones disponibles, usando la estructura real de la API ChannelRush.
    """
    return [
        {
            "date": "2025-07-20",
            "roomTypeId": roomTypeId or 67890,
            "availableRooms": 5,
            "totalRooms": 10
        },
        {
            "date": "2025-07-21",
            "roomTypeId": roomTypeId or 67890,
            "availableRooms": 4,
            "totalRooms": 10
        },
        {
            "date": "2025-07-22",
            "roomTypeId": roomTypeId or 67890,
            "availableRooms": 3,
            "totalRooms": 10
        }
        # Puedes ampliar esta lista o generarla en bucle según las fechas...
    ]

# Puedes añadir más tools aquí siguiendo el mismo patrón.

# --- Lista de tools para el agente ---
hotel_tools = [consultar_disponibilidad]

# --- Socket.IO ---
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")

# --- Eventos de Socket.IO ---
@sio.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Cliente desconectado: {sid}")

@sio.event
async def user_message(sid, data):
    print(f"Mensaje recibido de {sid}: {data}")

    # --- LangChain Agent con tools ---
    from langchain.agents import create_openai_functions_agent, AgentExecutor
    from langchain.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Eres el asistente de gestión hotelera Aselvia. Usa las tools para responder sobre reservas y disponibilidad."),
        ("user", "{input}"),
    ])

    agent = create_openai_functions_agent(llm, hotel_tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=hotel_tools, verbose=True)

    response = await agent_executor.ainvoke({"input": data})
    await sio.emit("bot-message", response["output"], to=sid)

# --- Montaje de la Aplicación ASGI ---
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)

# Para ejecutar: uvicorn main:asgi_app --host 0.0.0.0 --port $PORT
