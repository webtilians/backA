import os
import json
import uuid
import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.schema import HumanMessage, AIMessage

from langgraph.prebuilt import create_react_agent
from langchain.memory import ConversationBufferMemory

# --- Configuración FastAPI & Socket.IO ---
app = FastAPI(title="API Aselvia + LangGraph (REACT AGENT)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")

# --- Tools del hotel ---
@tool
def crear_reserva(nombre: str, tipo_habitacion: str, fecha: str, email: str = "", telefono: str = "", personas: int = 1) -> dict:
    """Crea una reserva y actualiza disponibilidad"""
    try:
        if os.path.exists("reservas.json"):
            with open("reservas.json", "r", encoding="utf-8") as f:
                reservas = json.load(f)
        else:
            reservas = []
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        total = None
        for hab in data["habitaciones"]:
            if hab["tipo"].lower() == tipo_habitacion.lower():
                total = hab.get("total", 1)
                break
        if total is None:
            return {"ok": False, "mensaje": f"No se reconoce el tipo de habitación '{tipo_habitacion}'."}
        reservas_count = sum(
            1 for r in reservas if r["tipo_habitacion"].lower() == tipo_habitacion.lower() and r["fecha"] == fecha
        )
        if total - reservas_count <= 0:
            return {"ok": False, "mensaje": f"No quedan habitaciones '{tipo_habitacion}' para la fecha {fecha}."}
        reserva = {
            "id": f"RES{str(uuid.uuid4())[:8]}",
            "nombre": nombre, "tipo_habitacion": tipo_habitacion, "fecha": fecha,
            "email": email, "telefono": telefono, "personas": personas,
            "timestamp": datetime.datetime.now().isoformat()
        }
        reservas.append(reserva)
        with open("reservas.json", "w", encoding="utf-8") as f:
            json.dump(reservas, f, indent=2, ensure_ascii=False)
        return {"ok": True, "mensaje": "Reserva realizada correctamente", "reserva": reserva}
    except Exception as e:
        return {"ok": False, "mensaje": f"Error al crear reserva: {str(e)}"}

@tool
def consultar_disponibilidad(tipo_habitacion: str, fecha: str) -> dict:
    """Devuelve habitaciones libres para una fecha y tipo"""
    try:
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"Error leyendo la base de datos: {str(e)}"}
    total, desc, precio, moneda = None, "", "", ""
    for hab in data["habitaciones"]:
        if hab["tipo"].lower() == tipo_habitacion.lower():
            total = hab.get("total", 1)
            desc = hab.get("descripcion", "")
            precio = hab.get("precio", "")
            moneda = hab.get("moneda", "")
            break
    if total is None:
        return {"ok": False, "mensaje": f"No se reconoce el tipo de habitación '{tipo_habitacion}'."}
    reservas_count = 0
    if os.path.exists("reservas.json"):
        with open("reservas.json", "r", encoding="utf-8") as f:
            reservas = json.load(f)
        reservas_count = sum(
            1 for r in reservas if r["tipo_habitacion"].lower() == tipo_habitacion.lower() and r["fecha"] == fecha
        )
    disponibles = total - reservas_count
    return {
        "ok": True, "tipo": tipo_habitacion, "descripcion": desc,
        "precio": precio, "moneda": moneda, "fecha": fecha,
        "total": total, "reservadas": reservas_count, "disponibles": max(0, disponibles)
    }

@tool
def listar_tipos_habitaciones() -> list:
    """Devuelve la lista de tipos de habitaciones"""
    try:
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [{"error": f"Error leyendo la base de datos: {str(e)}"}]
    tipos = []
    for hab in data["habitaciones"]:
        tipos.append({
            "tipo": hab["tipo"], "descripcion": hab["descripcion"],
            "precio": hab.get("precio", ""), "moneda": hab.get("moneda", ""),
            "total": hab.get("total", 1)
        })
    return tipos

@tool
def listar_reservas() -> list:
    """Devuelve la lista de todas las reservas hechas en el hotel AselvIA"""
    if not os.path.exists("reservas.json"):
        return []
    try:
        with open("reservas.json", "r", encoding="utf-8") as f:
            reservas = json.load(f)
        return reservas
    except Exception as e:
        return [{"error": f"Error leyendo reservas: {str(e)}"}]

hotel_tools = [consultar_disponibilidad, listar_tipos_habitaciones, crear_reserva, listar_reservas]

# --- Memoria por sesión ---
conversaciones = {}  # clave: sid, valor: ConversationBufferMemory

def get_memory(sid):
    if sid not in conversaciones:
        conversaciones[sid] = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    return conversaciones[sid]

# --- Prompt del agente ---
PROMPT = (
    "Eres el asistente digital del hotel AselvIA.\n"
    "Gestionas reservas, tarifas y disponibilidad SOLO de este hotel.\n"
    "La fecha de hoy es {today}.\n"
    "Cuando uses una herramienta, indícalo antes al usuario (por ejemplo: 'Consultando disponibilidad...').\n"
    "Nunca muestres el JSON, solo resume la información.\n"
    "Si falta información para una reserva, pide nombre completo, email y teléfono.\n"
    "Cuando devuelvas tarifas, usa: 'La tarifa para el {{fecha}} es de X euros'."
)

# --- Inicialización del agente LangGraph REACT ---
llm = ChatOpenAI(model="gpt-4-turbo", temperature=0, streaming=True)
graph = create_react_agent(
    llm=llm,
    tools=hotel_tools,
    prompt=PROMPT,
    memory_key="chat_history",
    input_key="input"
)

# --- FastAPI endpoint (opcional) ---
@app.get("/")
def read_root():
    return {"message": "API LangGraph AselvIA funcionando (REACT AGENT)"}

# --- Socket.IO eventos asíncronos ---
@sio.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Cliente desconectado: {sid}")
    if sid in conversaciones:
        del conversaciones[sid]

@sio.event
async def user_message(sid, data):
    # data = { "mensaje": str, "historial": [{sender, text}] }
    user_input = data.get("mensaje") if isinstance(data, dict) else data
    memory = get_memory(sid)
    today = datetime.date.today().strftime("%Y-%m-%d")
    memory.chat_memory.add_user_message(user_input)
    # Ejecuta el REACT agent en modo streaming
    async for step in graph.astream(
        {"input": user_input, "chat_history": memory.chat_memory.messages, "today": today}
    ):
        # Cuando va a ejecutar una tool, avisa al front
        if "agent_action" in step:
            await sio.emit("tool-used", {
                "tool": step["agent_action"].tool,
                "input": step["agent_action"].tool_input,
            }, to=sid)
        # Cuando hay respuesta final, mándala y termina
        if "output" in step:
            final_msg = step["output"]
            memory.chat_memory.add_ai_message(final_msg)
            await sio.emit("bot-message", final_msg, to=sid)
            await sio.emit("tool-used", {"tool": None}, to=sid)
            break

# --- Montaje ASGI ---
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)

# Para ejecutar: uvicorn main:asgi_app --host 0.0.0.0 --port $PORT
