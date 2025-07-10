import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from langchain_openai import ChatOpenAI
from langchain.tools import tool
import uuid
import datetime

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
    return {"message": "Hola Mundo desde FastAPI + Socket.IO!"}

# --- TOOLS para LangChain ---

@tool
def crear_reserva(nombre: str, tipo_habitacion: str, fecha: str, email: str = "", telefono: str = "", personas: int = 1) -> dict:
    """
    Crea una reserva para el hotel AselvIA, guardando los datos en reservas.json.
    Actualiza la disponibilidad automáticamente.
    """
    try:
        # Leer reservas actuales
        if os.path.exists("reservas.json"):
            with open("reservas.json", "r", encoding="utf-8") as f:
                reservas = json.load(f)
        else:
            reservas = []

        # Leer info habitaciones (stock)
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        # Calcular stock total de ese tipo
        total = None
        for hab in data["habitaciones"]:
            if hab["tipo"].lower() == tipo_habitacion.lower():
                total = hab.get("total", 1)  # Por defecto 1 si no está
                break
        if total is None:
            return {"ok": False, "mensaje": f"No se reconoce el tipo de habitación '{tipo_habitacion}'."}

        # Contar reservas ya existentes para esa fecha y tipo
        reservas_count = 0
        for r in reservas:
            if (r["tipo_habitacion"].lower() == tipo_habitacion.lower()) and (r["fecha"] == fecha):
                reservas_count += 1
        disponibles = total - reservas_count
        if disponibles <= 0:
            return {"ok": False, "mensaje": f"No quedan habitaciones '{tipo_habitacion}' para la fecha {fecha}."}

        # Guardar reserva
        reserva = {
            "id": f"RES{str(uuid.uuid4())[:8]}",
            "nombre": nombre,
            "tipo_habitacion": tipo_habitacion,
            "fecha": fecha,
            "email": email,
            "telefono": telefono,
            "personas": personas,
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
    """
    Devuelve cuántas habitaciones libres hay para una fecha y tipo, calculando dinámicamente.
    """
    try:
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"Error leyendo la base de datos de habitaciones: {str(e)}"}
    total = None
    descripcion = ""
    precio = ""
    moneda = ""
    for hab in data["habitaciones"]:
        if hab["tipo"].lower() == tipo_habitacion.lower():
            total = hab.get("total", 1)
            descripcion = hab.get("descripcion", "")
            precio = hab.get("precio", "")
            moneda = hab.get("moneda", "")
            break
    if total is None:
        return {"ok": False, "mensaje": f"No se reconoce el tipo de habitación '{tipo_habitacion}'."}

    # Contar reservas existentes
    reservas_count = 0
    if os.path.exists("reservas.json"):
        with open("reservas.json", "r", encoding="utf-8") as f:
            reservas = json.load(f)
        for r in reservas:
            if (r["tipo_habitacion"].lower() == tipo_habitacion.lower()) and (r["fecha"] == fecha):
                reservas_count += 1

    disponibles = total - reservas_count
    return {
        "ok": True,
        "tipo": tipo_habitacion,
        "descripcion": descripcion,
        "precio": precio,
        "moneda": moneda,
        "fecha": fecha,
        "total": total,
        "reservadas": reservas_count,
        "disponibles": max(0, disponibles)
    }

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
            "precio": hab.get("precio", ""),
            "moneda": hab.get("moneda", ""),
            "total": hab.get("total", 1)
        })
    return tipos
@tool
def listar_reservas() -> list:
    """
    Devuelve la lista de todas las reservas hechas en el hotel AselvIA.
    """
    if not os.path.exists("reservas.json"):
        return []
    try:
        with open("reservas.json", "r", encoding="utf-8") as f:
            reservas = json.load(f)
        return reservas
    except Exception as e:
        return [{"error": f"Error leyendo reservas: {str(e)}"}]

# --- Lista de tools para el agente ---
hotel_tools = [consultar_disponibilidad, listar_tipos_habitaciones, crear_reserva, listar_reservas]

# --- Socket.IO ---
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins="*")

# --- HISTORIAL DE CHAT (por SID de usuario) ---
def guardar_historial(sid, remitente, mensaje):
    """
    Guarda cada mensaje enviado o recibido en historial_chat.json agrupado por SID.
    """
    historial = {}
    if os.path.exists("historial_chat.json"):
        with open("historial_chat.json", "r", encoding="utf-8") as f:
            try:
                historial = json.load(f)
            except Exception:
                historial = {}
    if sid not in historial:
        historial[sid] = []
    historial[sid].append({
        "remitente": remitente,
        "mensaje": mensaje,
        "timestamp": datetime.datetime.now().isoformat()
    })
    with open("historial_chat.json", "w", encoding="utf-8") as f:
        json.dump(historial, f, indent=2, ensure_ascii=False)

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
    guardar_historial(sid, "usuario", data)  # Guardar mensaje del usuario

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
            -Si el usuario pregunta que reservas hay hechas usa la tool de listar reservas y muestra la informacion de forma clara
            - Si vas a realizar una reserva, siempre pide el nombre completo, email y teléfono antes de confirmarla.
            """
        ),
        ("user", "{input}"),
        ("system", "{agent_scratchpad}")
    ])

    agent = create_openai_functions_agent(llm, hotel_tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=hotel_tools, verbose=True)

    response = await agent_executor.ainvoke({"input": data})
    guardar_historial(sid, "bot", response["output"])  # Guardar respuesta del bot
    await sio.emit("bot-message", response["output"], to=sid)

# --- Montaje de la Aplicación ASGI ---
asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)

# Para ejecutar: uvicorn main:asgi_app --host 0.0.0.0 --port $PORT
