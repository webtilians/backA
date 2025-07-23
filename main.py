import os
import json
import uuid
import datetime
import logging
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import socketio
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage, HumanMessage, AIMessage

try:
    from langgraph.prebuilt import create_react_agent
    LANGGRAPH_AVAILABLE = True
except ImportError:
    try:
        from langchain.agents import create_react_agent, AgentExecutor
        from langchain.agents.format_scratchpad import format_to_openai_function_messages
        from langchain.agents.output_parsers import OpenAIFunctionsAgentOutputParser
        from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
        LANGGRAPH_AVAILABLE = False
        print("Usando langchain agents en lugar de langgraph")
    except ImportError:
        print("No se pudo importar ningún sistema de agentes")
        LANGGRAPH_AVAILABLE = False

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verificar API Key de OpenAI
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    logger.error("OPENAI_API_KEY no está configurada en el archivo .env")
    raise ValueError("OPENAI_API_KEY es requerida. Por favor configúrala en el archivo .env")

# --- CONFIGURACIÓN FastAPI & Socket.IO ---
app = FastAPI(
    title="API Aselvia + LangGraph (REACT AGENT)",
    description="API para gestión de reservas de hotel con IA",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sio = socketio.AsyncServer(
    async_mode='asgi', 
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True
)

# --- FUNCIONES AUXILIARES ---
def cargar_hotel_data() -> Dict:
    """Carga los datos del hotel desde el archivo JSON"""
    try:
        if not os.path.exists("hotel_data.json"):
            logger.error("hotel_data.json no existe")
            return {"habitaciones": []}
        
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Error cargando hotel_data.json: {str(e)}")
        return {"habitaciones": []}

def cargar_reservas() -> List[Dict]:
    """Carga las reservas desde el archivo JSON"""
    try:
        if not os.path.exists("reservas.json"):
            return []
        
        with open("reservas.json", "r", encoding="utf-8") as f:
            reservas = json.load(f)
        return reservas
    except Exception as e:
        logger.error(f"Error cargando reservas.json: {str(e)}")
        return []

def guardar_reservas(reservas: List[Dict]) -> bool:
    """Guarda las reservas en el archivo JSON"""
    try:
        with open("reservas.json", "w", encoding="utf-8") as f:
            json.dump(reservas, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error guardando reservas.json: {str(e)}")
        return False
# --- TOOLS DEL HOTEL ---
@tool
def crear_reserva(
    nombre: str, 
    tipo_habitacion: str, 
    fecha: str, 
    email: str = "", 
    telefono: str = "", 
    personas: int = 1
) -> Dict:
    """Crea una reserva y actualiza disponibilidad"""
    try:
        logger.info(f"Creando reserva para {nombre}, habitación {tipo_habitacion}, fecha {fecha}")
        
        reservas = cargar_reservas()
        data = cargar_hotel_data()
        
        # Buscar el tipo de habitación
        total = None
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                total = hab.get("total", 1)
                break
        
        if total is None:
            return {
                "ok": False, 
                "mensaje": f"No se reconoce el tipo de habitación '{tipo_habitacion}'."
            }
        
        # Contar reservas existentes para esa fecha y tipo
        reservas_count = sum(
            1 for r in reservas 
            if r["tipo_habitacion"].lower() == tipo_habitacion.lower() 
            and r["fecha"] == fecha
        )
        
        if total - reservas_count <= 0:
            return {
                "ok": False, 
                "mensaje": f"No quedan habitaciones '{tipo_habitacion}' para la fecha {fecha}."
            }
        
        # Crear nueva reserva
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
        
        if guardar_reservas(reservas):
            logger.info(f"Reserva creada exitosamente: {reserva['id']}")
            return {
                "ok": True, 
                "mensaje": "Reserva realizada correctamente", 
                "reserva": reserva
            }
        else:
            return {
                "ok": False, 
                "mensaje": "Error al guardar la reserva"
            }
            
    except Exception as e:
        logger.error(f"Error creando reserva: {str(e)}")
        return {
            "ok": False, 
            "mensaje": f"Error al crear reserva: {str(e)}"
        }

@tool
def consultar_disponibilidad(tipo_habitacion: str, fecha: str) -> Dict:
    """Devuelve habitaciones libres para una fecha y tipo"""
    try:
        logger.info(f"Consultando disponibilidad para {tipo_habitacion} en {fecha}")
        
        data = cargar_hotel_data()
        
        # Buscar información de la habitación
        total, desc, precio, moneda = None, "", "", ""
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                total = hab.get("total", 1)
                desc = hab.get("descripcion", "")
                precio = hab.get("precio", "")
                moneda = hab.get("moneda", "")
                break
        
        if total is None:
            return {
                "ok": False, 
                "mensaje": f"No se reconoce el tipo de habitación '{tipo_habitacion}'."
            }
        
        # Contar reservas para esa fecha
        reservas = cargar_reservas()
        reservas_count = sum(
            1 for r in reservas 
            if r["tipo_habitacion"].lower() == tipo_habitacion.lower() 
            and r["fecha"] == fecha
        )
        
        disponibles = total - reservas_count
        
        return {
            "ok": True,
            "tipo": tipo_habitacion,
            "descripcion": desc,
            "precio": precio,
            "moneda": moneda,
            "fecha": fecha,
            "total": total,
            "reservadas": reservas_count,
            "disponibles": max(0, disponibles)
        }
        
    except Exception as e:
        logger.error(f"Error consultando disponibilidad: {str(e)}")
        return {
            "ok": False, 
            "mensaje": f"Error consultando disponibilidad: {str(e)}"
        }

@tool
def listar_tipos_habitaciones() -> List[Dict]:
    """Devuelve la lista de tipos de habitaciones"""
    try:
        logger.info("Listando tipos de habitaciones")
        
        data = cargar_hotel_data()
        tipos = []
        
        for hab in data.get("habitaciones", []):
            tipos.append({
                "tipo": hab.get("tipo", ""),
                "descripcion": hab.get("descripcion", ""),
                "precio": hab.get("precio", ""),
                "moneda": hab.get("moneda", ""),
                "total": hab.get("total", 1)
            })
        
        return tipos
        
    except Exception as e:
        logger.error(f"Error listando tipos de habitaciones: {str(e)}")
        return [{"error": f"Error leyendo la base de datos: {str(e)}"}]

@tool
def listar_reservas() -> List[Dict]:
    """Devuelve la lista de todas las reservas hechas en el hotel AselvIA"""
    try:
        logger.info("Listando todas las reservas")
        reservas = cargar_reservas()
        return reservas
        
    except Exception as e:
        logger.error(f"Error listando reservas: {str(e)}")
        return [{"error": f"Error leyendo reservas: {str(e)}"}]

# Lista de herramientas disponibles
hotel_tools = [consultar_disponibilidad, listar_tipos_habitaciones, crear_reserva, listar_reservas]

# --- MEMORIA POR SESIÓN ---
conversaciones: Dict[str, ConversationBufferMemory] = {}

def get_memory(sid: str) -> ConversationBufferMemory:
    """Obtiene o crea la memoria de conversación para una sesión"""
    if sid not in conversaciones:
        memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        
        # System prompt como primer mensaje del historial
        system_message = SystemMessage(content=
            "Eres el asistente digital del hotel AselvIA. Solo gestionas reservas, tarifas y disponibilidad de este hotel. "
            "Responde siempre en español de manera amigable y profesional. "
            "Informa al usuario de cada acción que vas a realizar (por ejemplo: 'Consultando disponibilidad...'). "
            "Nunca muestres el JSON crudo, solo resume la información de manera clara y legible. "
            "Si falta información para una reserva, pide cortésmente nombre completo, email y teléfono. "
            "Cuando devuelvas tarifas, usa un formato claro: 'La tarifa para [habitación] el [fecha] es de [precio] euros'. "
            "Si hay errores, explícalos de manera comprensible para el usuario."
        )
        
        memory.chat_memory.add_message(system_message)
        conversaciones[sid] = memory
        logger.info(f"Nueva memoria creada para sesión: {sid}")
    
    return conversaciones[sid]

# --- CONFIGURACIÓN DEL AGENTE ---
def inicializar_agente():
    """Inicializa el agente con manejo de errores"""
    try:
        llm = ChatOpenAI(
            model="gpt-4-turbo", 
            temperature=0, 
            streaming=False,
            api_key=openai_api_key
        )
        
        # Crear un agente simple personalizado
        class SimpleHotelAgent:
            def __init__(self, llm, tools):
                self.llm = llm
                self.tools = {tool.name: tool for tool in tools}
                
            def run(self, input_text):
                try:
                    # Analizar la consulta y determinar qué herramienta usar
                    if "disponibilidad" in input_text.lower() or "disponible" in input_text.lower():
                        return self._handle_availability_query(input_text)
                    elif "reserva" in input_text.lower() and ("crear" in input_text.lower() or "hacer" in input_text.lower()):
                        return self._handle_reservation_request(input_text)
                    elif "tipos" in input_text.lower() or "habitaciones" in input_text.lower() or "precios" in input_text.lower():
                        return self._handle_room_types_query()
                    elif "lista" in input_text.lower() and "reservas" in input_text.lower():
                        return self._handle_list_reservations()
                    else:
                        return self._handle_general_query(input_text)
                    
                except Exception as e:
                    logger.error(f"Error en SimpleHotelAgent: {str(e)}")
                    return "Lo siento, ocurrió un error al procesar tu solicitud."
            
            def _handle_availability_query(self, input_text):
                # Ejecutar listar_tipos_habitaciones para mostrar opciones
                tipos_result = self.tools["listar_tipos_habitaciones"].func()
                
                response = "🏨 **Disponibilidad en Hotel AselvIA**\n\n"
                response += "Estos son nuestros tipos de habitaciones disponibles:\n\n"
                
                for hab in tipos_result:
                    if "error" not in hab:
                        response += f"🛏️ **{hab['tipo']}**\n"
                        response += f"   📝 {hab['descripcion']}\n"
                        response += f"   💰 {hab['precio']} {hab['moneda']} por noche\n"
                        response += f"   🏠 Total disponibles: {hab['total']}\n\n"
                
                response += "Para consultar disponibilidad específica, por favor indícame:\n"
                response += "- ¿Qué tipo de habitación te interesa?\n"
                response += "- ¿Para qué fecha?\n"
                
                return response
            
            def _handle_room_types_query(self):
                tipos_result = self.tools["listar_tipos_habitaciones"].func()
                
                response = "🏨 **Tipos de Habitaciones - Hotel AselvIA**\n\n"
                
                for hab in tipos_result:
                    if "error" not in hab:
                        response += f"🛏️ **{hab['tipo']}**\n"
                        response += f"   📝 {hab['descripcion']}\n"
                        response += f"   💰 {hab['precio']} {hab['moneda']} por noche\n"
                        response += f"   🏠 Habitaciones totales: {hab['total']}\n\n"
                
                return response
            
            def _handle_list_reservations(self):
                reservas_result = self.tools["listar_reservas"].func()
                
                if not reservas_result:
                    return "📋 No hay reservas registradas en el hotel en este momento."
                
                response = "📋 **Reservas Actuales - Hotel AselvIA**\n\n"
                
                for reserva in reservas_result:
                    if "error" not in reserva:
                        response += f"🎫 **Reserva {reserva['id']}**\n"
                        response += f"   👤 Cliente: {reserva['nombre']}\n"
                        response += f"   🛏️ Habitación: {reserva['tipo_habitacion']}\n"
                        response += f"   📅 Fecha: {reserva['fecha']}\n"
                        response += f"   👥 Personas: {reserva['personas']}\n"
                        if reserva.get('email'):
                            response += f"   📧 Email: {reserva['email']}\n"
                        if reserva.get('telefono'):
                            response += f"   📞 Teléfono: {reserva['telefono']}\n"
                        response += "\n"
                
                return response
            
            def _handle_reservation_request(self, input_text):
                return ("Para crear una reserva necesito la siguiente información:\n\n"
                       "🎫 **Datos requeridos:**\n"
                       "- 👤 Nombre completo\n"
                       "- 🛏️ Tipo de habitación (Doble Estándar o Suite Junior)\n"
                       "- 📅 Fecha de la reserva\n"
                       "- 📧 Email de contacto\n"
                       "- 📞 Teléfono\n"
                       "- 👥 Número de personas\n\n"
                       "Por favor proporciona estos datos y procederé a crear tu reserva.")
            
            def _handle_general_query(self, input_text):
                prompt = f"""
Eres el asistente digital del hotel AselvIA. El usuario te pregunta: {input_text}

Responde de manera amigable y profesional en español. Ofrece ayuda con:
- Consultar disponibilidad de habitaciones
- Ver tipos de habitaciones y precios
- Crear reservas
- Listar reservas existentes

Si la consulta no está relacionada con el hotel, recuerda amablemente que solo puedes ayudar con temas del hotel AselvIA.
"""
                
                response = self.llm.invoke(prompt)
                return response.content
        
        agent = SimpleHotelAgent(llm, hotel_tools)
        logger.info("Agente simple inicializado correctamente")
        return agent
        
    except Exception as e:
        logger.error(f"Error inicializando agente: {str(e)}")
        return None

# Inicializar el agente
agent = inicializar_agente()

# --- FastAPI ENDPOINTS ---
@app.get("/")
def read_root():
    """Endpoint de prueba"""
    return {
        "message": "API LangGraph AselvIA funcionando correctamente",
        "version": "1.0.1",
        "status": "ok",
        "agent_disponible": agent is not None
    }

@app.get("/health")
def health_check():
    """Endpoint de health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "openai_configured": bool(openai_api_key),
        "agent_ready": agent is not None
    }

@app.get("/habitaciones")
def get_habitaciones():
    """Endpoint para obtener tipos de habitaciones"""
    try:
        data = cargar_hotel_data()
        return {"habitaciones": data.get("habitaciones", [])}
    except Exception as e:
        logger.error(f"Error en endpoint habitaciones: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/reservas")
def get_reservas():
    """Endpoint para obtener todas las reservas"""
    try:
        reservas = cargar_reservas()
        return {"reservas": reservas}
    except Exception as e:
        logger.error(f"Error en endpoint reservas: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Socket.IO EVENTOS ---
@sio.event
async def connect(sid, environ):
    """Evento de conexión de cliente"""
    logger.info(f"Cliente conectado: {sid}")
    await sio.emit("connection_status", {"status": "connected", "sid": sid}, to=sid)

@sio.event
async def disconnect(sid):
    """Evento de desconexión de cliente"""
    logger.info(f"Cliente desconectado: {sid}")
    
    # Limpiar memoria de la sesión
    if sid in conversaciones:
        del conversaciones[sid]
        logger.info(f"Memoria limpiada para sesión: {sid}")

@sio.event
async def user_message(sid, data):
    """Maneja mensajes del usuario"""
    try:
        # Extraer mensaje del usuario
        user_input = data.get("mensaje") if isinstance(data, dict) else str(data)
        
        if not user_input or user_input.strip() == "":
            await sio.emit("bot-message", "Por favor, envía un mensaje válido.", to=sid)
            return
        
        logger.info(f"Mensaje recibido de {sid}: {user_input}")
        
        # Verificar que el agente esté disponible
        if agent is None:
            error_msg = "Lo siento, el asistente no está disponible en este momento. Por favor, verifica la configuración de OpenAI."
            await sio.emit("bot-message", error_msg, to=sid)
            return
        
        # Obtener memoria de la conversación
        memory = get_memory(sid)
        today = datetime.date.today().strftime("%Y-%m-%d")
        
        # Añadir mensaje del usuario a la memoria
        memory.chat_memory.add_user_message(user_input)
        
        # Preparar historial de chat
        chat_history = memory.chat_memory.messages
        
        # Asegurar que el primer mensaje sea SystemMessage
        if not chat_history or not isinstance(chat_history[0], SystemMessage):
            system_msg = SystemMessage(content=
                "Eres el asistente digital del hotel AselvIA. Solo gestionas reservas, tarifas y disponibilidad de este hotel. "
                "Responde siempre en español de manera amigable y profesional."
            )
            chat_history = [system_msg] + chat_history
        
        # Enviar mensaje de "escribiendo..."
        await sio.emit("bot-typing", {"typing": True}, to=sid)
        
        # Preparar el input para el agente
        input_text = f"""
Fecha actual: {today}

Historial de conversación:
{chr(10).join([f"Usuario: {msg.content}" if hasattr(msg, 'content') and msg.type == 'human' else f"Asistente: {msg.content}" if hasattr(msg, 'content') and msg.type == 'ai' else "" for msg in chat_history[-6:] if hasattr(msg, 'content')])}

Consulta actual del usuario: {user_input}

Eres el asistente digital del hotel AselvIA. Responde en español de manera amigable y profesional.
"""
        
        # Invocar el agente
        try:
            result = agent.run(input_text)
            final_msg = result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.error(f"Error ejecutando agente: {str(e)}")
            final_msg = "Lo siento, ocurrió un error al procesar tu solicitud. ¿Podrías reformular tu pregunta?"
        
        # Añadir respuesta del bot a la memoria
        memory.chat_memory.add_ai_message(final_msg)
        
        # Enviar respuesta al cliente
        await sio.emit("bot-typing", {"typing": False}, to=sid)
        await sio.emit("bot-message", final_msg, to=sid)
        
        logger.info(f"Respuesta enviada a {sid}")
        
    except Exception as e:
        logger.error(f"Error procesando mensaje de {sid}: {str(e)}")
        error_msg = "Lo siento, ocurrió un error al procesar tu mensaje. Por favor, inténtalo de nuevo."
        
        await sio.emit("bot-typing", {"typing": False}, to=sid)
        await sio.emit("bot-message", error_msg, to=sid)

@sio.event
async def ping(sid):
    """Evento ping para mantener conexión activa"""
    await sio.emit("pong", {"timestamp": datetime.datetime.now().isoformat()}, to=sid)


# --- CONFIGURACIÓN ASGI ---
try:
    asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)
    logger.info("Aplicación ASGI configurada correctamente")
except Exception as e:
    logger.error(f"Error configurando ASGI: {str(e)}")
    asgi_app = app

# --- FUNCIÓN MAIN PARA DESARROLLO ---
if __name__ == "__main__":
    import uvicorn
    
    # Configuración desde variables de entorno
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"Iniciando servidor en {host}:{port}")
    logger.info(f"Modo debug: {debug}")
    logger.info(f"OpenAI API Key configurada: {'Sí' if openai_api_key else 'No'}")
    logger.info(f"Agente disponible: {'Sí' if agent else 'No'}")
    
    uvicorn.run(
        "main:asgi_app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if debug else "warning"
    )
