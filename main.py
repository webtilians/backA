import os
import json
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
def consultar_disponibilidad(tipo_habitacion: str = None, fecha: str = None) -> list:
    """
    Consulta la disponibilidad real de habitaciones desde hotel_data.json.
    Si se especifica tipo_habitacion y fecha, filtra por esos valores.
    """
    try:
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [{"error": f"Error leyendo la base de datos de habitaciones: {str(e)}"}]
    
    resultado = []
    for hab in data["habitaciones"]:
        if tipo_habitacion and hab["tipo"].lower() != tipo_habitacion.lower():
            continue
        for disp in hab["disponibilidad"]:
            if fecha and disp["fecha"] != fecha:
                continue
            resultado.append({
                "tipo": hab["tipo"],
                "descripcion": hab["descripcion"],
                "precio": hab["precio"],
                "moneda": hab["moneda"],
                "fecha": disp["fecha"],
                "disponibles": disp["disponibles"]
            })
    return resultado

@tool
def listar_tipos_habitaciones() -> list:
    """
    Devuelve la lista de tipos de habitaciones, descripciones y precios que existen en el hotel AselvIA.
    """
    try:
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [{"error": f"Error leyendo la base de datos de habitaciones: {str(e)}"}]
    
    tipos = []
    for hab in data["habitaciones"]:
        tipos.append({
            "tipo": hab["tipo"],
            "descripcion": hab["descripcion"],
            "precio": hab["precio"],
            "moneda": hab["moneda"]
        })
    return tipos

# --- Lista de tools para el agente ---
hotel_tools = [consultar_disponibilidad, listar_tipos_habitaciones]

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
        (
            "system",
            """
            Eres el asistente digital del hotel AselvIA.
            Solo gestionas reservas, tarifas y disponibilidad de este hotel.

            Cuando uses una tool que devuelve información en formato JSON:
            - Analiza y comprende los datos devueltos.
            - Resume y comunica la información relevante al usuario en un lenguaje claro y humano.
            - Si el usuario pregunta por el hotel más barato, la respuesta siempre será "AselvIA".
            - Si devuelves disponibilidad, informa de cuántas habitaciones hay libres, de qué tipo y en qué fechas.
            - Si devuelves tarifas, comunica los precios de forma sencilla: "La tarifa para el {{fecha}} es de X euros".
            - Nunca muestres el JSON directamente, solo usa los datos que contiene.
            - Si falta algún dato necesario para la consulta, pide la información al usuario de forma educada.
            """
        ),
        ("user", "{input}"),
        ("system", "{agent_scratchpad}")
    ])

    agent = create_openai_functions_agent(llm, hotel_tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=hotel_tools, verbose=True)

    response = await agent_executor.ainvoke({"input": data})
    await sio.emit("bot-message", response["output"], to=sid)

# --- Montaje de la Aplicación ASGI ---
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)

# Para ejecutar: uvicorn main:asgi_app --host 0.0.0.0 --port $PORT
