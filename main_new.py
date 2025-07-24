import os
import json
import uuid
import datetime
import logging
import re
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import socketio
from dotenv import load_dotenv
import uvicorn

from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage, HumanMessage, AIMessage

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
    title="API Aselvia Hotel con IA",
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
        logger.info(f"🎫 HERRAMIENTA crear_reserva INICIADA: {nombre}, {tipo_habitacion}, {fecha}")
        
        reservas = cargar_reservas()
        data = cargar_hotel_data()
        
        # Buscar el tipo de habitación
        total = None
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                total = hab["total"]
                break
        
        if total is None:
            return {
                "ok": False, 
                "mensaje": f"Tipo de habitación '{tipo_habitacion}' no encontrado"
            }
        
        # Contar reservas existentes para esa fecha y tipo
        reservas_count = sum(
            1 for r in reservas 
            if r["tipo_habitacion"].lower() == tipo_habitacion.lower() 
            and r["fecha"] == fecha
        )
        
        logger.info(f"📊 Disponibilidad: {total} total, {reservas_count} reservadas, {total - reservas_count} disponibles")
        
        if total - reservas_count <= 0:
            return {
                "ok": False, 
                "mensaje": f"No hay habitaciones {tipo_habitacion} disponibles para {fecha}"
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
            logger.info(f"✅ RESERVA CREADA: {reserva['id']}")
            return {
                "ok": True, 
                "mensaje": f"Reserva creada exitosamente con ID {reserva['id']}", 
                "reserva": reserva
            }
        else:
            return {
                "ok": False, 
                "mensaje": "Error guardando la reserva"
            }
            
    except Exception as e:
        logger.error(f"❌ ERROR CRÍTICO en crear_reserva: {str(e)}")
        return {
            "ok": False, 
            "mensaje": f"Error al crear reserva: {str(e)}"
        }

@tool
def consultar_disponibilidad(tipo_habitacion: str, fecha: str) -> Dict:
    """Devuelve habitaciones libres para una fecha y tipo"""
    try:
        logger.info(f"🔍 HERRAMIENTA consultar_disponibilidad INICIADA: {tipo_habitacion} en {fecha}")
        
        data = cargar_hotel_data()
        
        # Buscar información de la habitación
        total = None
        desc = ""
        precio = 0
        moneda = "EUR"
        
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                total = hab["total"]
                desc = hab.get("descripcion", "")
                precio = hab.get("precio", 0)
                moneda = hab.get("moneda", "EUR")
                break
        
        if total is None:
            return {
                "ok": False, 
                "mensaje": f"Tipo de habitación '{tipo_habitacion}' no encontrado"
            }
        
        # Contar reservas para esa fecha
        reservas = cargar_reservas()
        reservas_count = sum(
            1 for r in reservas 
            if r["tipo_habitacion"].lower() == tipo_habitacion.lower() 
            and r["fecha"] == fecha
        )
        
        disponibles = total - reservas_count
        
        logger.info(f"📊 RESULTADO: {disponibles} de {total} habitaciones {tipo_habitacion} disponibles para {fecha}")
        
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
        logger.error(f"❌ ERROR en consultar_disponibilidad: {str(e)}")
        return {
            "ok": False, 
            "mensaje": f"Error consultando disponibilidad: {str(e)}"
        }

@tool
def listar_tipos_habitaciones() -> List[Dict]:
    """Devuelve la lista de tipos de habitaciones"""
    try:
        logger.info("📋 HERRAMIENTA listar_tipos_habitaciones INICIADA")
        
        data = cargar_hotel_data()
        tipos = []
        
        for hab in data.get("habitaciones", []):
            tipos.append({
                "tipo": hab["tipo"],
                "descripcion": hab.get("descripcion", ""),
                "precio": hab.get("precio", 0),
                "moneda": hab.get("moneda", "EUR"),
                "total": hab["total"]
            })
        
        logger.info(f"✅ TIPOS LISTADOS: {len(tipos)} tipos de habitaciones encontrados")
        return tipos
        
    except Exception as e:
        logger.error(f"❌ ERROR en listar_tipos_habitaciones: {str(e)}")
        return [{"error": f"Error leyendo la base de datos: {str(e)}"}]

@tool
def listar_reservas() -> List[Dict]:
    """Devuelve la lista de todas las reservas hechas en el hotel AselvIA"""
    try:
        logger.info("📝 HERRAMIENTA listar_reservas INICIADA")
        reservas = cargar_reservas()
        logger.info(f"✅ RESERVAS LISTADAS: {len(reservas)} reservas encontradas")
        return reservas
        
    except Exception as e:
        logger.error(f"❌ ERROR en listar_reservas: {str(e)}")
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
        logger.info(f"💭 Nueva memoria creada para sesión: {sid}")
    
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
        
        # Crear un agente inteligente que usa herramientas y reporta su uso
        class IntelligentHotelAgent:
            def __init__(self, llm, tools):
                self.llm = llm
                self.tools = {tool.name: tool for tool in tools}
                self.current_sid = None
                
            def set_session(self, sid):
                self.current_sid = sid
                
            async def emit_tool_usage(self, tool_name, input_data=None):
                if self.current_sid:
                    await sio.emit("tool_usage", {
                        "tool": tool_name,
                        "input": input_data,
                        "timestamp": datetime.datetime.now().isoformat()
                    }, to=self.current_sid)
                
            async def emit_tool_finished(self):
                if self.current_sid:
                    await sio.emit("tool_finished", {
                        "timestamp": datetime.datetime.now().isoformat()
                    }, to=self.current_sid)
                
            async def run(self, input_text, chat_history=None):
                try:
                    # Analizar la intención del usuario
                    intent_result = await self._analyze_intent(input_text, chat_history)
                    
                    if intent_result["type"] == "reservation":
                        return await self._handle_reservation_request(intent_result, input_text, chat_history)
                    elif intent_result["type"] == "availability_specific":
                        return await self._handle_specific_availability(intent_result)
                    elif intent_result["type"] == "availability_general":
                        return await self._handle_general_availability()
                    elif intent_result["type"] == "room_types":
                        return await self._handle_room_types_query()
                    elif intent_result["type"] == "list_reservations":
                        return await self._handle_list_reservations()
                    else:
                        return await self._handle_general_query(input_text, chat_history)
                        
                except Exception as e:
                    logger.error(f"❌ Error en agente: {str(e)}")
                    return f"Disculpa, ha ocurrido un error: {str(e)}"
            
            async def _analyze_intent(self, input_text, chat_history=None):
                """Analiza la intención del usuario usando el LLM"""
                
                # Construir el contexto de la conversación
                context = ""
                if chat_history:
                    # Obtener los últimos mensajes del historial
                    recent_messages = chat_history[-6:] if len(chat_history) > 6 else chat_history
                    for msg in recent_messages:
                        if hasattr(msg, 'content'):
                            if isinstance(msg, HumanMessage):
                                context += f"Usuario: {msg.content}\n"
                            elif isinstance(msg, AIMessage):
                                context += f"Asistente: {msg.content}\n"

                prompt = f"""
                Analiza la siguiente conversación y el mensaje actual del usuario para determinar su intención:

                Contexto de conversación previa:
                {context}

                Mensaje actual: "{input_text}"

                Extrae información específica basándote en TODO el contexto:
                1. Si es una solicitud de reserva, extrae: nombre, email, teléfono, tipo habitación, fecha, personas
                2. Si consulta disponibilidad específica, extrae: tipo habitación y fecha
                3. Si es consulta general, determínalo

                Responde SOLO con un JSON válido con esta estructura:
                {{
                    "type": "reservation|availability_specific|availability_general|room_types|list_reservations|general",
                    "extracted_data": {{
                        "nombre": "extraído o null",
                        "email": "extraído o null", 
                        "telefono": "extraído o null",
                        "tipo_habitacion": "extraído o null",
                        "fecha": "YYYY-MM-DD o null",
                        "personas": número o null
                    }}
                }}
                """
                
                try:
                    response = await self.llm.ainvoke([HumanMessage(content=prompt)])
                    
                    # Limpiar la respuesta y extraer JSON
                    content = response.content.strip()
                    if content.startswith("```json"):
                        content = content[7:-3]
                    elif content.startswith("```"):
                        content = content[3:-3]
                    
                    result = json.loads(content)
                    logger.info(f"🎯 Intención analizada: {result['type']}")
                    return result
                    
                except Exception as e:
                    logger.error(f"❌ Error analizando intención: {str(e)}")
                    return {"type": "general", "extracted_data": {}}

            async def _handle_general_query(self, input_text, chat_history=None):
                """Maneja consultas generales usando el LLM"""
                
                # Construir contexto
                messages = []
                if chat_history:
                    for msg in chat_history[-10:]:  # Limitar a últimos 10 mensajes
                        messages.append(msg)
                
                messages.append(HumanMessage(content=input_text))
                
                try:
                    response = await self.llm.ainvoke(messages)
                    return response.content
                except Exception as e:
                    logger.error(f"❌ Error en consulta general: {str(e)}")
                    return "Disculpa, no pude procesar tu consulta. ¿Podrías reformularla?"
            
            async def _handle_specific_availability(self, intent_result):
                """Maneja consultas de disponibilidad específica"""
                data = intent_result["extracted_data"]
                tipo = data.get("tipo_habitacion")
                fecha = data.get("fecha")
                
                if not tipo or not fecha:
                    return "Para consultar disponibilidad necesito el tipo de habitación y la fecha. ¿Podrías especificarlos?"
                
                await self.emit_tool_usage("consultar_disponibilidad", {"tipo": tipo, "fecha": fecha})
                
                try:
                    result = self.tools["consultar_disponibilidad"].func(tipo, fecha)
                    await self.emit_tool_finished()
                    
                    if result["ok"]:
                        return f"📊 Para {fecha}:\n\n🛏️ **{result['tipo']}**\n💰 {result['precio']} {result['moneda']} por noche\n🏠 Disponibles: {result['disponibles']} de {result['total']} habitaciones\n\n¿Te gustaría hacer una reserva?"
                    else:
                        return f"❌ {result['mensaje']}"
                        
                except Exception as e:
                    await self.emit_tool_finished()
                    return f"Error consultando disponibilidad: {str(e)}"
            
            async def _handle_general_availability(self):
                """Maneja consultas generales de disponibilidad"""
                await self.emit_tool_usage("listar_tipos_habitaciones")
                
                try:
                    result = self.tools["listar_tipos_habitaciones"].func()
                    await self.emit_tool_finished()
                    
                    if result and len(result) > 0 and "error" not in result[0]:
                        response = "🏨 **Habitaciones Disponibles - Hotel AselvIA**\n\n"
                        
                        for hab in result:
                            response += f"🛏️ **{hab['tipo']}**\n"
                            response += f"📝 {hab['descripcion']}\n"
                            response += f"💰 {hab['precio']} {hab['moneda']} por noche\n"
                            response += f"🏠 Habitaciones totales: {hab['total']}\n\n"
                        
                        response += "¿Te gustaría consultar disponibilidad para alguna fecha o tipo de habitación? Si quieres reservar, dime los datos y lo gestiono."
                        return response
                    else:
                        return "❌ Error obteniendo información de habitaciones"
                        
                except Exception as e:
                    await self.emit_tool_finished()
                    return f"Error obteniendo tipos de habitaciones: {str(e)}"
            
            async def _handle_room_types_query(self):
                """Maneja consultas sobre tipos de habitaciones"""
                return await self._handle_general_availability()
            
            async def _handle_list_reservations(self):
                """Maneja consultas de listado de reservas"""
                await self.emit_tool_usage("listar_reservas")
                
                try:
                    result = self.tools["listar_reservas"].func()
                    await self.emit_tool_finished()
                    
                    if result and len(result) > 0 and "error" not in result[0]:
                        response = f"📝 **Reservas Actuales ({len(result)} total)**\n\n"
                        
                        for reserva in result:
                            response += f"🎫 **{reserva['id']}**\n"
                            response += f"👤 {reserva['nombre']}\n"
                            response += f"🛏️ {reserva['tipo_habitacion']}\n"
                            response += f"📅 {reserva['fecha']}\n"
                            response += f"👥 {reserva['personas']} persona(s)\n\n"
                        
                        return response
                    else:
                        return "📝 No hay reservas registradas actualmente."
                        
                except Exception as e:
                    await self.emit_tool_finished()
                    return f"Error obteniendo reservas: {str(e)}"

            async def _handle_reservation_request(self, intent_result, input_text, chat_history=None):
                """Maneja solicitudes de reserva"""
                data = intent_result["extracted_data"]
                
                # Si no tenemos datos suficientes, extraer del historial de conversación
                if not data.get("nombre") or not data.get("tipo_habitacion") or not data.get("fecha"):
                    # Buscar información en el historial usando regex
                    historial_texto = ""
                    if chat_history:
                        for msg in chat_history:
                            if hasattr(msg, 'content'):
                                historial_texto += msg.content + " "
                    
                    historial_texto += input_text
                    
                    # Extraer nombre si no lo tenemos
                    if not data.get("nombre"):
                        nombres = re.findall(r'(?:soy|me llamo|mi nombre es)\s+([A-Za-zÀ-ÿ\s]+?)(?:\s+y\s|\s*[,.]|\s*$)', historial_texto, re.IGNORECASE)
                        if nombres:
                            data["nombre"] = nombres[-1].strip()
                    
                    # Extraer email si no lo tenemos
                    if not data.get("email"):
                        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', historial_texto)
                        if emails:
                            data["email"] = emails[-1]
                    
                    # Extraer tipo de habitación
                    if not data.get("tipo_habitacion"):
                        if "doble" in historial_texto.lower() and "estándar" in historial_texto.lower():
                            data["tipo_habitacion"] = "Doble Estándar"
                        elif "suite" in historial_texto.lower() and "junior" in historial_texto.lower():
                            data["tipo_habitacion"] = "Suite Junior"
                    
                    # Extraer fecha (hoy, mañana, etc.)
                    if not data.get("fecha"):
                        hoy = datetime.datetime.now().date()
                        if "hoy" in historial_texto.lower():
                            data["fecha"] = hoy.strftime("%Y-%m-%d")
                        elif "mañana" in historial_texto.lower():
                            data["fecha"] = (hoy + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

                # Validar datos requeridos
                required_fields = ["nombre", "tipo_habitacion", "fecha"]
                missing_fields = [field for field in required_fields if not data.get(field)]
                
                if missing_fields:
                    return f"Para crear tu reserva necesito algunos datos más:\n" + \
                           "\n".join([f"• {field.replace('_', ' ').title()}" for field in missing_fields]) + \
                           "\n\n¿Podrías proporcionármelos?"
                
                # Crear la reserva
                await self.emit_tool_usage("crear_reserva", data)
                
                try:
                    result = self.tools["crear_reserva"].func(
                        nombre=data["nombre"],
                        tipo_habitacion=data["tipo_habitacion"],
                        fecha=data["fecha"],
                        email=data.get("email", ""),
                        telefono=data.get("telefono", ""),
                        personas=data.get("personas", 1)
                    )
                    await self.emit_tool_finished()
                    
                    if result["ok"]:
                        reserva = result["reserva"]
                        response = f"✅ **¡Reserva Confirmada!**\n\n"
                        response += f"🎫 **ID:** {reserva['id']}\n"
                        response += f"👤 **Cliente:** {reserva['nombre']}\n"
                        response += f"🛏️ **Habitación:** {reserva['tipo_habitacion']}\n"
                        response += f"📅 **Fecha:** {reserva['fecha']}\n"
                        response += f"👥 **Personas:** {reserva['personas']}\n"
                        if reserva['email']:
                            response += f"📧 **Email:** {reserva['email']}\n"
                        response += f"\n¡Gracias por elegir Hotel AselvIA! 🏨"
                        return response
                    else:
                        return f"❌ {result['mensaje']}"
                        
                except Exception as e:
                    await self.emit_tool_finished()
                    return f"Error creando reserva: {str(e)}"
            
            def _parse_date(self, date_str):
                """Convierte texto de fecha a formato YYYY-MM-DD"""
                try:
                    hoy = datetime.datetime.now().date()
                    
                    if "hoy" in date_str.lower():
                        return hoy.strftime("%Y-%m-%d")
                    elif "mañana" in date_str.lower():
                        return (hoy + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                    else:
                        # Intentar parsear otros formatos
                        return date_str
                except:
                    return date_str
        
        agent = IntelligentHotelAgent(llm, hotel_tools)
        logger.info("🤖 Agente inteligente inicializado correctamente")
        return agent
        
    except Exception as e:
        logger.error(f"❌ Error inicializando agente: {str(e)}")
        return None

# Inicializar el agente
agent = inicializar_agente()

# --- FastAPI ENDPOINTS ---
@app.get("/")
def read_root():
    """Endpoint de prueba"""
    return {
        "message": "API Hotel AselvIA funcionando correctamente",
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
        logger.error(f"❌ Error en endpoint habitaciones: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/reservas")
def get_reservas():
    """Endpoint para obtener todas las reservas"""
    try:
        reservas = cargar_reservas()
        return {"reservas": reservas}
    except Exception as e:
        logger.error(f"❌ Error en endpoint reservas: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Servir archivos estáticos
try:
    @app.get("/test_client.html")
    def get_test_client():
        return FileResponse("test_client.html")
except:
    logger.warning("⚠️ test_client.html no encontrado")

# --- Socket.IO EVENTOS ---
@sio.event
async def connect(sid, environ):
    """Evento de conexión de cliente"""
    logger.info(f"🔌 CLIENTE CONECTADO: {sid}")
    await sio.emit("connection_status", {"status": "connected", "sid": sid}, to=sid)

@sio.event
async def disconnect(sid):
    """Evento de desconexión de cliente"""
    logger.info(f"🔌 CLIENTE DESCONECTADO: {sid}")
    
    # Limpiar memoria de la sesión
    if sid in conversaciones:
        del conversaciones[sid]
        logger.info(f"🧹 Memoria limpiada para sesión: {sid}")

@sio.event
async def user_message(sid, data):
    """Maneja mensajes del usuario"""
    try:
        message = data.get("message", "").strip()
        if not message:
            await sio.emit("bot_response", {"response": "No recibí ningún mensaje."}, to=sid)
            return

        logger.info(f"💬 MENSAJE DE {sid}: {message}")

        if not agent:
            await sio.emit("bot_response", {"response": "El agente no está disponible."}, to=sid)
            return

        # Configurar la sesión del agente
        agent.set_session(sid)

        # Obtener memoria de la conversación
        memory = get_memory(sid)
        
        # Agregar mensaje del usuario a la memoria
        memory.chat_memory.add_user_message(message)
        
        # Obtener historial para el agente
        chat_history = memory.chat_memory.messages

        # Procesar mensaje con el agente
        response = await agent.run(message, chat_history)

        # Agregar respuesta del bot a la memoria
        memory.chat_memory.add_ai_message(response)

        # Enviar respuesta al cliente
        await sio.emit("bot_response", {"response": response}, to=sid)
        
        logger.info(f"🤖 RESPUESTA ENVIADA A {sid}: {response[:100]}...")

    except Exception as e:
        logger.error(f"❌ ERROR procesando mensaje de {sid}: {str(e)}")
        await sio.emit("bot_response", {
            "response": f"Disculpa, ha ocurrido un error: {str(e)}"
        }, to=sid)

@sio.event
async def ping(sid):
    """Evento ping para mantener conexión activa"""
    await sio.emit("pong", {"timestamp": datetime.datetime.now().isoformat()}, to=sid)

# --- CONFIGURACIÓN ASGI ---
try:
    asgi_app = socketio.ASGIApp(sio, other_asgi_app=app)
    logger.info("🚀 Aplicación ASGI configurada correctamente")
except Exception as e:
    logger.error(f"❌ Error configurando ASGI: {str(e)}")
    asgi_app = app

# --- FUNCIÓN MAIN PARA DESARROLLO ---
if __name__ == "__main__":
    import uvicorn
    
    # Configuración desde variables de entorno
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"🌟 Iniciando servidor en {host}:{port}")
    logger.info(f"🔧 Modo debug: {debug}")
    logger.info(f"🔑 OpenAI API Key configurada: {'Sí' if openai_api_key else 'No'}")
    logger.info(f"🤖 Agente disponible: {'Sí' if agent else 'No'}")
    
    uvicorn.run(
        "main_new:asgi_app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if debug else "warning"
    )
