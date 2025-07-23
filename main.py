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
        logger.info(f"🎫 HERRAMIENTA crear_reserva INICIADA: {nombre}, {tipo_habitacion}, {fecha}")
        
        reservas = cargar_reservas()
        data = cargar_hotel_data()
        
        # Buscar el tipo de habitación
        total = None
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                total = hab.get("total", 1)
                break
        
        if total is None:
            logger.warning(f"⚠️ Tipo de habitación no reconocido: {tipo_habitacion}")
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
        
        logger.info(f"📊 Disponibilidad: {total} total, {reservas_count} reservadas, {total - reservas_count} disponibles")
        
        if total - reservas_count <= 0:
            logger.warning(f"❌ Sin habitaciones disponibles para {tipo_habitacion} en {fecha}")
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
            logger.info(f"✅ RESERVA CREADA EXITOSAMENTE: {reserva['id']} para {nombre}")
            return {
                "ok": True, 
                "mensaje": "Reserva realizada correctamente", 
                "reserva": reserva
            }
        else:
            logger.error(f"❌ Error guardando reserva para {nombre}")
            return {
                "ok": False, 
                "mensaje": "Error al guardar la reserva"
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
        total, desc, precio, moneda = None, "", "", ""
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                total = hab.get("total", 1)
                desc = hab.get("descripcion", "")
                precio = hab.get("precio", "")
                moneda = hab.get("moneda", "")
                break
        
        if total is None:
            logger.warning(f"⚠️ Tipo de habitación no encontrado: {tipo_habitacion}")
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
                "tipo": hab.get("tipo", ""),
                "descripcion": hab.get("descripcion", ""),
                "precio": hab.get("precio", ""),
                "moneda": hab.get("moneda", ""),
                "total": hab.get("total", 1)
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
        
        # Crear un agente inteligente que usa herramientas y reporta su uso
        class IntelligentHotelAgent:
            def __init__(self, llm, tools):
                self.llm = llm
                self.tools = {tool.name: tool for tool in tools}
                self.current_tool = None
                self.sid = None
                
            def set_session(self, sid):
                """Establece la sesión actual para reportar herramientas"""
                self.sid = sid
                
            async def emit_tool_usage(self, tool_name, input_data=None):
                """Emite evento de uso de herramienta al frontend y logs del backend"""
                logger.info(f"🔧 HERRAMIENTA USADA: {tool_name} | Entrada: {input_data}")
                if self.sid:
                    await sio.emit("tool-used", {
                        "tool": tool_name,
                        "input": input_data
                    }, to=self.sid)
                
            async def emit_tool_finished(self):
                """Emite evento de herramienta terminada"""
                logger.info(f"✅ HERRAMIENTA TERMINADA")
                if self.sid:
                    await sio.emit("tool-used", {"tool": None}, to=self.sid)
                
            async def run(self, input_text, chat_history=None):
                try:
                    logger.info(f"🤖 PROCESANDO: {input_text}")
                    
                    # Usar GPT-4 para determinar la intención del usuario con contexto del historial
                    intent_result = await self._analyze_intent(input_text, chat_history)
                    
                    logger.info(f"🧠 INTENCIÓN DETECTADA: {intent_result.get('action', 'general')}")
                    
                    if intent_result["action"] == "consultar_disponibilidad_especifica":
                        return await self._handle_specific_availability(intent_result)
                    elif intent_result["action"] == "consultar_disponibilidad_general":
                        return await self._handle_general_availability()
                    elif intent_result["action"] == "crear_reserva":
                        return await self._handle_reservation_request(intent_result, input_text, chat_history)
                    elif intent_result["action"] == "listar_tipos":
                        return await self._handle_room_types_query()
                    elif intent_result["action"] == "listar_reservas":
                        return await self._handle_list_reservations()
                    else:
                        return await self._handle_general_query(input_text, chat_history)
                    
                except Exception as e:
                    logger.error(f"❌ ERROR en IntelligentHotelAgent: {str(e)}")
                    return "Lo siento, ocurrió un error al procesar tu solicitud."
            
            async def _analyze_intent(self, input_text, chat_history=None):
                # Construir contexto del historial
                context = ""
                if chat_history:
                    recent_messages = []
                    for msg in chat_history[-6:]:  # Últimos 6 mensajes para contexto
                        if hasattr(msg, 'content'):
                            if isinstance(msg, HumanMessage):
                                recent_messages.append(f"Usuario: {msg.content}")
                            elif isinstance(msg, AIMessage):
                                recent_messages.append(f"Asistente: {msg.content}")
                            elif hasattr(msg, 'type'):
                                if msg.type == 'human':
                                    recent_messages.append(f"Usuario: {msg.content}")
                                elif msg.type == 'ai':
                                    recent_messages.append(f"Asistente: {msg.content}")
                    
                    if recent_messages:
                        context = f"\nContexto de conversación reciente:\n" + "\n".join(recent_messages) + "\n"

                prompt = f"""
Analiza el siguiente mensaje del usuario considerando el contexto de la conversación:

{context}
Mensaje actual: "{input_text}"

Responde SOLO con un JSON válido que contenga:
- "action": una de estas opciones:
  * "consultar_disponibilidad_especifica" - si menciona un tipo específico de habitación Y/O fecha
  * "consultar_disponibilidad_general" - si pregunta por disponibilidad sin especificar tipo o fecha
  * "crear_reserva" - si quiere hacer una reserva o proporciona datos para reserva
  * "listar_tipos" - si pregunta por tipos de habitaciones o precios
  * "listar_reservas" - si quiere ver reservas existentes
  * "general" - para cualquier otra consulta
- "tipo_habitacion": extraer si menciona "doble", "suite", etc. (null si no especifica)
- "fecha": extraer si menciona una fecha específica (null si no especifica)
- "datos_reserva": objeto con nombre, email, teléfono, personas si los proporciona

Ejemplos:
- "¿hay disponibilidad para doble estándar el 25 de julio?" → {{"action": "consultar_disponibilidad_especifica", "tipo_habitacion": "Doble Estándar", "fecha": "2025-07-25"}}
- "si, quiero reservar" (después de consultar disponibilidad) → {{"action": "crear_reserva"}}
- "mi nombre es Juan, email juan@email.com" → {{"action": "crear_reserva", "datos_reserva": {{"nombre": "Juan", "email": "juan@email.com"}}}}
"""
                
                try:
                    response = self.llm.invoke(prompt)
                    import json
                    result = json.loads(response.content.strip())
                    logger.info(f"🧠 ANÁLISIS: {result}")
                    return result
                except Exception as e:
                    logger.error(f"❌ Error analizando intención: {str(e)}")
                    return {"action": "general"}

            async def _handle_general_query(self, input_text, chat_history=None):
                # Maneja consultas generales SOLO usando datos reales y herramientas, nunca inventa.
                logger.info("🔍 _handle_general_query: forzando uso de herramientas reales")
                # Siempre mostrar catálogo real
                await self.emit_tool_usage("listar_tipos_habitaciones")
                tipos_result = self.tools["listar_tipos_habitaciones"].func()
                await self.emit_tool_finished()
                response = "🏨 **Catálogo de Habitaciones - Hotel AselvIA**\n\n"
                for hab in tipos_result:
                    if "error" not in hab:
                        response += f"🛏️ {hab['tipo']}\n📝 {hab['descripcion']}\n💰 {hab['precio']} {hab['moneda']} por noche\n🏠 Habitaciones totales: {hab['total']}\n\n"
                response += "¿Te gustaría consultar disponibilidad para alguna fecha o tipo de habitación? Si quieres reservar, dime los datos y lo gestiono."
                return response
                
                try:
                    response = self.llm.invoke(prompt)
                    import json
                    result = json.loads(response.content.strip())
                    logger.info(f"🧠 ANÁLISIS: {result}")
                    return result
                except Exception as e:
                    logger.error(f"❌ Error analizando intención: {str(e)}")
                    return {"action": "general"}
            
            async def _handle_specific_availability(self, intent_result):
                tipo = intent_result.get("tipo_habitacion")
                fecha = intent_result.get("fecha")
                
                if not tipo:
                    # Si no especifica tipo, mostrar opciones
                    await self.emit_tool_usage("listar_tipos_habitaciones")
                    tipos_result = self.tools["listar_tipos_habitaciones"].func()
                    await self.emit_tool_finished()
                    
                    response = "🏨 **Tipos de habitaciones disponibles:**\n\n"
                    for hab in tipos_result:
                        if "error" not in hab:
                            response += f"🛏️ **{hab['tipo']}** - {hab['precio']} {hab['moneda']}/noche\n"
                            response += f"   📝 {hab['descripcion']}\n\n"
                    
                    response += "Por favor, especifica qué tipo de habitación te interesa y para qué fecha."
                    return response
                
                if not fecha:
                    response = f"Para consultar disponibilidad de **{tipo}**, por favor especifica para qué fecha necesitas la habitación."
                    return response
                
                # Consultar disponibilidad específica
                await self.emit_tool_usage("consultar_disponibilidad", {
                    "tipo_habitacion": tipo,
                    "fecha": fecha
                })
                
                result = self.tools["consultar_disponibilidad"].func(tipo, fecha)
                await self.emit_tool_finished()
                
                if result.get("ok"):
                    if result["disponibles"] > 0:
                        response = f"✅ **Disponibilidad confirmada**\n\n"
                        response += f"🛏️ **{result['tipo']}**\n"
                        response += f"📅 Fecha: {result['fecha']}\n"
                        response += f"💰 Precio: {result['precio']} {result['moneda']} por noche\n"
                        response += f"🏠 Habitaciones disponibles: **{result['disponibles']}** de {result['total']}\n\n"
                        response += f"📝 {result['descripcion']}\n\n"
                        response += "¿Te gustaría hacer una reserva?"
                    else:
                        response = f"❌ **No hay disponibilidad**\n\n"
                        response += f"Lo siento, no quedan habitaciones **{result['tipo']}** disponibles para el {result['fecha']}.\n\n"
                        response += "¿Te interesa consultar otros tipos de habitaciones o fechas?"
                else:
                    response = f"❌ {result.get('mensaje', 'Error consultando disponibilidad')}"
                
                return response
            
            async def _handle_general_availability(self):
                await self.emit_tool_usage("listar_tipos_habitaciones")
                tipos_result = self.tools["listar_tipos_habitaciones"].func()
                await self.emit_tool_finished()
                
                response = "🏨 **Disponibilidad General - Hotel AselvIA**\n\n"
                
                for hab in tipos_result:
                    if "error" not in hab:
                        response += f"🛏️ **{hab['tipo']}**\n"
                        response += f"   📝 {hab['descripcion']}\n"
                        response += f"   💰 {hab['precio']} {hab['moneda']} por noche\n"
                        response += f"   🏠 Total disponibles: {hab['total']}\n\n"
                
                response += "Para consultar disponibilidad específica, indícame:\n"
                response += "- ¿Qué tipo de habitación te interesa?\n"
                response += "- ¿Para qué fecha?"
                
                return response
            
            async def _handle_room_types_query(self):
                await self.emit_tool_usage("listar_tipos_habitaciones")
                tipos_result = self.tools["listar_tipos_habitaciones"].func()
                await self.emit_tool_finished()
                
                response = "🏨 **Catálogo de Habitaciones - Hotel AselvIA**\n\n"
                
                for hab in tipos_result:
                    if "error" not in hab:
                        response += f"🛏️ **{hab['tipo']}**\n"
                        response += f"   📝 {hab['descripcion']}\n"
                        response += f"   💰 {hab['precio']} {hab['moneda']} por noche\n"
                        response += f"   🏠 Habitaciones totales: {hab['total']}\n\n"
                
                return response
            
            async def _handle_list_reservations(self):
                await self.emit_tool_usage("listar_reservas")
                reservas_result = self.tools["listar_reservas"].func()
                await self.emit_tool_finished()
                
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

            async def _handle_reservation_request(self, intent_result, input_text, chat_history=None):
                logger.info(f"🎫 PROCESANDO RESERVA: {intent_result}")
                import re
                # Extraer datos de reserva del intent o del historial
                datos_reserva = intent_result.get("datos_reserva", {})
                if not datos_reserva:
                    datos_reserva = {}
                tipo_habitacion = intent_result.get("tipo_habitacion")
                fecha = intent_result.get("fecha")
                # Buscar datos adicionales en el historial de conversación
                if chat_history:
                    for msg in chat_history[-10:]:
                        if hasattr(msg, 'content') and isinstance(msg, HumanMessage):
                            content = msg.content.lower()
                            # Extraer nombre
                            if not datos_reserva.get("nombre"):
                                name_patterns = [
                                    r"mi nombre es ([a-záéíóúñü\s]+)",
                                    r"me llamo ([a-záéíóúñü\s]+)",
                                    r"soy ([a-záéíóúñü\s]+)"
                                ]
                                for pattern in name_patterns:
                                    match = re.search(pattern, content)
                                    if match:
                                        datos_reserva["nombre"] = match.group(1).strip().title()
                                        break
                            # Extraer email
                            if not datos_reserva.get("email"):
                                email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', msg.content)
                                if email_match:
                                    datos_reserva["email"] = email_match.group()
                            # Extraer teléfono
                            if not datos_reserva.get("telefono"):
                                tel_match = re.search(r'\b\d{9,}\b', msg.content)
                                if tel_match:
                                    datos_reserva["telefono"] = tel_match.group()
                            # Extraer tipo de habitación
                            if not tipo_habitacion:
                                if "doble" in content and "estándar" in content:
                                    tipo_habitacion = "Doble Estándar"
                                elif "suite" in content:
                                    tipo_habitacion = "Suite Junior"
                            # Extraer fecha
                            if not fecha:
                                date_patterns = [
                                    r"(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)",
                                    r"(\d{4}-\d{2}-\d{2})",
                                    r"(\d{1,2}/\d{1,2}/\d{4})"
                                ]
                                for pattern in date_patterns:
                                    match = re.search(pattern, content)
                                    if match:
                                        fecha = self._parse_date(match.group())
                                        break
                logger.info(f"📋 DATOS RECOPILADOS: nombre={datos_reserva.get('nombre')}, tipo={tipo_habitacion}, fecha={fecha}, email={datos_reserva.get('email')}, tel={datos_reserva.get('telefono')}")
                # Verificar qué datos faltan
                required_fields = {
                    "nombre": datos_reserva.get("nombre"),
                    "tipo_habitacion": tipo_habitacion,
                    "fecha": fecha,
                    "email": datos_reserva.get("email"),
                    "telefono": datos_reserva.get("telefono")
                }
                missing_fields = [field for field, value in required_fields.items() if not value]
                if missing_fields:
                    response = "🎫 **Crear Nueva Reserva**\n\n"
                    response += "Para completar tu reserva necesito los siguientes datos:\n\n"
                    if "nombre" in missing_fields:
                        response += "- 👤 **Nombre completo**\n"
                    if "tipo_habitacion" in missing_fields:
                        response += "- 🛏️ **Tipo de habitación** (Doble Estándar o Suite Junior)\n"
                    if "fecha" in missing_fields:
                        response += "- 📅 **Fecha de la reserva**\n"
                    if "email" in missing_fields:
                        response += "- 📧 **Email de contacto**\n"
                    if "telefono" in missing_fields:
                        response += "- 📞 **Teléfono**\n"
                    response += "\nPor favor proporciona la información que falta."
                    logger.info(f"❗ Faltan datos para reserva: {missing_fields}")
                    return response
                # Crear la reserva
                personas = datos_reserva.get("personas", 1)
                await self.emit_tool_usage("crear_reserva", {
                    "nombre": datos_reserva["nombre"],
                    "tipo_habitacion": tipo_habitacion,
                    "fecha": fecha,
                    "email": datos_reserva["email"],
                    "telefono": datos_reserva["telefono"],
                    "personas": personas
                })
                result = self.tools["crear_reserva"].func(
                    nombre=datos_reserva["nombre"],
                    tipo_habitacion=tipo_habitacion,
                    fecha=fecha,
                    email=datos_reserva["email"],
                    telefono=datos_reserva["telefono"],
                    personas=personas
                )
                await self.emit_tool_finished()
                logger.info(f"Resultado crear_reserva: {result}")
                if result.get("ok"):
                    reserva = result.get("reserva", {})
                    response = f"✅ **¡Reserva Confirmada!**\n\n"
                    response += f"🎫 **ID de Reserva:** {reserva.get('id')}\n"
                    response += f"👤 **Cliente:** {reserva.get('nombre')}\n"
                    response += f"🛏️ **Habitación:** {reserva.get('tipo_habitacion')}\n"
                    response += f"📅 **Fecha:** {reserva.get('fecha')}\n"
                    response += f"👥 **Personas:** {reserva.get('personas')}\n"
                    response += f"📧 **Email:** {reserva.get('email')}\n"
                    response += f"📞 **Teléfono:** {reserva.get('telefono')}\n\n"
                    response += "🎉 **¡Tu reserva ha sido procesada exitosamente!**\n"
                    response += "Recibirás un email de confirmación en breve."
                else:
                    response = f"❌ **Error al crear reserva**\n\n{result.get('mensaje', 'Error desconocido')}"
                return response
            
            def _parse_date(self, date_str):
                """Convierte diferentes formatos de fecha a YYYY-MM-DD"""
                try:
                    import re
                    from datetime import datetime
                    
                    # Mapeo de meses en español
                    meses = {
                        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
                        "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
                        "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
                    }
                    
                    # Formato: "25 de julio"
                    match = re.search(r"(\d{1,2})\s+de\s+(\w+)", date_str.lower())
                    if match:
                        day = match.group(1).zfill(2)
                        month_name = match.group(2)
                        if month_name in meses:
                            return f"2025-{meses[month_name]}-{day}"
                    
                    # Formato: "2025-07-25"
                    if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
                        return date_str
                    
                    # Formato: "25/07/2025"
                    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
                    if match:
                        day, month, year = match.groups()
                        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    
                    return date_str
                except:
                    return date_str
        
        agent = IntelligentHotelAgent(llm, hotel_tools)
        logger.info("Agente inteligente inicializado correctamente")
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
    else:
        logger.info(f"⚠️ No había memoria para la sesión: {sid}")

@sio.event
async def user_message(sid, data):
    """Maneja mensajes del usuario"""
    try:
        # Extraer mensaje del usuario
        user_input = data.get("mensaje") if isinstance(data, dict) else str(data)
        
        if not user_input or user_input.strip() == "":
            await sio.emit("bot-message", "Por favor, envía un mensaje válido.", to=sid)
            return
        
        logger.info(f"📨 Mensaje recibido de {sid}: '{user_input}'")
        
        # Verificar que el agente esté disponible
        if agent is None:
            error_msg = "Lo siento, el asistente no está disponible en este momento. Por favor, verifica la configuración de OpenAI."
            logger.error(f"❌ Agente no disponible para {sid}")
            await sio.emit("bot-message", error_msg, to=sid)
            return
        
        # Obtener memoria de la conversación
        memory = get_memory(sid)
        today = datetime.date.today().strftime("%Y-%m-%d")
        
        logger.info(f"💭 Memoria cargada para {sid}, mensajes en historial: {len(memory.chat_memory.messages)}")
        
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
        
        # Configurar la sesión del agente para reportar herramientas
        agent.set_session(sid)
        
        # Enviar mensaje de "escribiendo..."
        await sio.emit("bot-typing", {"typing": True}, to=sid)
        
        logger.info(f"⚡ Invocando agente para {sid}...")
        
        # Invocar el agente asíncrono con historial
        try:
            final_msg = await agent.run(user_input, chat_history)
        except Exception as e:
            logger.error(f"❌ Error ejecutando agente: {str(e)}")
            final_msg = "Lo siento, ocurrió un error al procesar tu solicitud. ¿Podrías reformular tu pregunta?"
        
        # Añadir respuesta del bot a la memoria
        memory.chat_memory.add_ai_message(final_msg)
        
        logger.info(f"🤖 Respuesta generada para {sid}: '{final_msg[:100]}...'")
        
        # Enviar respuesta al cliente
        await sio.emit("bot-typing", {"typing": False}, to=sid)
        await sio.emit("bot-message", final_msg, to=sid)
        
        logger.info(f"✅ Respuesta enviada a {sid}, memoria actualizada con {len(memory.chat_memory.messages)} mensajes")
        
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
