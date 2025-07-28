import os
import json
import uuid
import datetime
import logging
import re
from typing import Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.agents import create_openai_functions_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage
from langchain import hub
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

# Configuración
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Silenciar logs de uvicorn para health checks
uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.addFilter(lambda record: "/health" not in record.getMessage())

# Verificar API Key
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY es requerida")

# --- MODELOS PYDANTIC ---
class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    session_id: str

# --- FUNCIONES AUXILIARES ---
def cargar_hotel_data() -> Dict:
    """Carga datos del hotel"""
    try:
        with open("hotel_data.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando hotel_data.json: {e}")
        return {"habitaciones": []}

def cargar_reservas() -> List[Dict]:
    """Carga reservas existentes"""
    try:
        if os.path.exists("reservas.json"):
            with open("reservas.json", "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Error cargando reservas.json: {e}")
        return []

def guardar_reservas(reservas: List[Dict]) -> bool:
    """Guarda reservas en archivo"""
    try:
        with open("reservas.json", "w", encoding="utf-8") as f:
            json.dump(reservas, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error guardando reservas.json: {e}")
        return False

def normalizar_fecha(texto: str) -> str:
    """
    Normaliza fechas de diferentes formatos a YYYY-MM-DD
    Soporta: hoy, mañana, pasado mañana, próximo [día], dd/mm/yyyy, dd-mm-yyyy, etc.
    """
    try:
        texto = texto.lower().strip()
        hoy = datetime.datetime.now()
        
        # Debug logging
        logger.info(f"🔍 Normalizando fecha: '{texto}' (hoy es {hoy.strftime('%Y-%m-%d')})")
        
        # Días de la semana en español
        dias_semana = {
            'lunes': 0, 'martes': 1, 'miércoles': 2, 'miercoles': 2,
            'jueves': 3, 'viernes': 4, 'sábado': 5, 'sabado': 5, 'domingo': 6
        }
        
        # Meses en español
        meses = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
            'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }
        
        # 1. Fechas relativas básicas (prioridad alta)
        if 'hoy' in texto:
            fecha_resultado = hoy.strftime("%Y-%m-%d")
            logger.info(f"✅ Detectado 'hoy': {fecha_resultado}")
            return fecha_resultado
        
        if 'mañana' in texto and 'pasado' not in texto:
            fecha_resultado = (hoy + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            logger.info(f"✅ Detectado 'mañana': {fecha_resultado}")
            return fecha_resultado
        
        if any(palabra in texto for palabra in ['pasado mañana', 'pasado', 'después de mañana']):
            fecha_resultado = (hoy + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
            logger.info(f"✅ Detectado 'pasado mañana': {fecha_resultado}")
            return fecha_resultado
        
        # 2. Buscar patrones [FECHA_DETECTADA: YYYY-MM-DD] primero
        match = re.search(r'\[FECHA_DETECTADA:\s*(\d{4}-\d{2}-\d{2})\]', texto)
        if match:
            fecha_resultado = match.group(1)
            logger.info(f"✅ Detectado patrón FECHA_DETECTADA: {fecha_resultado}")
            return fecha_resultado
        
        # 3. Formato ISO YYYY-MM-DD (alta prioridad)
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', texto)
        if match:
            año, mes, dia = match.groups()
            fecha_resultado = f"{año}-{int(mes):02d}-{int(dia):02d}"
            logger.info(f"✅ Detectado formato ISO: {fecha_resultado}")
            return fecha_resultado
        
        # 4. Formatos de fecha DD/MM/YYYY o DD-MM-YYYY
        match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', texto)
        if match:
            dia, mes, año = match.groups()
            fecha_resultado = f"{año}-{int(mes):02d}-{int(dia):02d}"
            logger.info(f"✅ Detectado formato DD/MM/YYYY: {fecha_resultado}")
            return fecha_resultado
        
        # 5. Formatos DD/MM/YY
        match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2})', texto)
        if match:
            dia, mes, año = match.groups()
            año_completo = 2000 + int(año) if int(año) < 50 else 1900 + int(año)
            fecha_resultado = f"{año_completo}-{int(mes):02d}-{int(dia):02d}"
            logger.info(f"✅ Detectado formato DD/MM/YY: {fecha_resultado}")
            return fecha_resultado
        
        # 6. En X días
        match = re.search(r'en (\d+) día[s]?', texto)
        if match:
            dias = int(match.group(1))
            fecha_resultado = (hoy + datetime.timedelta(days=dias)).strftime("%Y-%m-%d")
            logger.info(f"✅ Detectado 'en X días': {fecha_resultado}")
            return fecha_resultado
        
        # 7. Dentro de X días
        match = re.search(r'dentro de (\d+) día[s]?', texto)
        if match:
            dias = int(match.group(1))
            fecha_resultado = (hoy + datetime.timedelta(days=dias)).strftime("%Y-%m-%d")
            logger.info(f"✅ Detectado 'dentro de X días': {fecha_resultado}")
            return fecha_resultado
        
        # 8. Esta semana / próxima semana
        if 'esta semana' in texto:
            # Buscar día específico en "esta semana"
            for dia, num_dia in dias_semana.items():
                if dia in texto:
                    dias_hasta = (num_dia - hoy.weekday()) % 7
                    if dias_hasta == 0:  # Si es hoy
                        dias_hasta = 0
                    fecha_resultado = (hoy + datetime.timedelta(days=dias_hasta)).strftime("%Y-%m-%d")
                    logger.info(f"✅ Detectado día esta semana: {fecha_resultado}")
                    return fecha_resultado
        
        if any(palabra in texto for palabra in ['próxima semana', 'proxima semana', 'la semana que viene']):
            # Buscar día específico en "próxima semana"
            for dia, num_dia in dias_semana.items():
                if dia in texto:
                    dias_hasta = (num_dia - hoy.weekday()) % 7 + 7
                    fecha_resultado = (hoy + datetime.timedelta(days=dias_hasta)).strftime("%Y-%m-%d")
                    logger.info(f"✅ Detectado día próxima semana: {fecha_resultado}")
                    return fecha_resultado
        
        # 9. Días específicos sin "próxima/esta"
        for dia, num_dia in dias_semana.items():
            if dia in texto and not any(palabra in texto for palabra in ['próxima', 'proxima', 'esta']):
                dias_hasta = (num_dia - hoy.weekday()) % 7
                if dias_hasta == 0:  # Si es hoy, asumir próxima semana
                    dias_hasta = 7
                fecha_resultado = (hoy + datetime.timedelta(days=dias_hasta)).strftime("%Y-%m-%d")
                logger.info(f"✅ Detectado día específico: {fecha_resultado}")
                return fecha_resultado
        
        # 10. Formato "25 de julio de 2025"
        match = re.search(r'(\d{1,2}) de (\w+) de (\d{4})', texto)
        if match:
            dia, mes_str, año = match.groups()
            if mes_str in meses:
                mes_num = meses[mes_str]
                fecha_resultado = f"{año}-{mes_num:02d}-{int(dia):02d}"
                logger.info(f"✅ Detectado formato completo: {fecha_resultado}")
                return fecha_resultado
        
        # 11. Formato "25 de julio" (año actual)
        match = re.search(r'(\d{1,2}) de (\w+)', texto)
        if match:
            dia, mes_str = match.groups()
            if mes_str in meses:
                mes_num = meses[mes_str]
                año = hoy.year
                # Si la fecha ya pasó este año, asumir año siguiente
                try:
                    fecha_objetivo = datetime.date(año, mes_num, int(dia))
                    if fecha_objetivo < hoy.date():
                        año += 1
                    fecha_resultado = f"{año}-{mes_num:02d}-{int(dia):02d}"
                    logger.info(f"✅ Detectado formato sin año: {fecha_resultado}")
                    return fecha_resultado
                except ValueError:
                    pass
        
        # 12. Solo número (asumir día del mes actual)
        match = re.search(r'\b(\d{1,2})\b', texto)
        if match and not any(char in texto for char in ['-', '/']):
            dia = int(match.group(1))
            if 1 <= dia <= 31:
                mes = hoy.month
                año = hoy.year
                # Si el día ya pasó este mes, usar mes siguiente
                try:
                    fecha_objetivo = datetime.date(año, mes, dia)
                    if fecha_objetivo < hoy.date():
                        if mes == 12:
                            mes = 1
                            año += 1
                        else:
                            mes += 1
                    fecha_resultado = f"{año}-{mes:02d}-{dia:02d}"
                    logger.info(f"✅ Detectado solo número: {fecha_resultado}")
                    return fecha_resultado
                except ValueError:
                    pass  # Día inválido para el mes
        
        logger.warning(f"❌ No se pudo normalizar la fecha: {texto}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error normalizando fecha '{texto}': {e}")
        return None

def extraer_y_normalizar_fechas(mensaje: str) -> tuple:
    """
    Extrae fechas del mensaje y devuelve el mensaje modificado con la fecha normalizada
    """
    fecha_normalizada = normalizar_fecha(mensaje)
    
    if fecha_normalizada:
        # Agregar la fecha normalizada al mensaje para que el agente la use
        mensaje_con_fecha = f"{mensaje} [FECHA_DETECTADA: {fecha_normalizada}]"
        return mensaje_con_fecha, fecha_normalizada
    
    return mensaje, None

# --- HERRAMIENTAS PARA EL AGENTE ---
@tool
def consultar_disponibilidad(tipo_habitacion: str, fecha: str) -> str:
    """Check room availability for a specific date"""
    logger.info(f"🔍 Consultando disponibilidad: {tipo_habitacion} para {fecha}")
    
    try:
        # Intentar normalizar la fecha si no está en formato correcto
        fecha_normalizada = normalizar_fecha(fecha)
        if fecha_normalizada:
            fecha = fecha_normalizada
        
        data = cargar_hotel_data()
        
        # Buscar información de la habitación
        habitacion_info = None
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                habitacion_info = hab
                break
        
        if not habitacion_info:
            available_types = ', '.join([h['tipo'] for h in data.get('habitaciones', [])])
            return f"I couldn't find the room type '{tipo_habitacion}'. Available types are: {available_types}"
        
        # Contar reservas para esa fecha
        reservas = cargar_reservas()
        reservas_count = sum(
            1 for r in reservas 
            if r["tipo_habitacion"].lower() == tipo_habitacion.lower() 
            and r["fecha"] == fecha
        )
        
        disponibles = habitacion_info["total"] - reservas_count
        
        # Formatear la fecha para mostrar
        try:
            fecha_obj = datetime.datetime.strptime(fecha, "%Y-%m-%d")
            fecha_formateada = fecha_obj.strftime("%d/%m/%Y")
        except:
            fecha_formateada = fecha
        
        resultado = f"📊 Availability for {fecha_formateada}:\n"
        resultado += f"🛏️ {habitacion_info['tipo']}\n"
        resultado += f"💰 {habitacion_info['precio']} {habitacion_info.get('moneda', 'EUR')} per night\n"
        resultado += f"🏠 Available: {max(0, disponibles)} out of {habitacion_info['total']} rooms\n"
        
        if disponibles > 0:
            resultado += f"✅ Rooms are available for booking"
        else:
            resultado += f"❌ No rooms available for this date"
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error en consultar_disponibilidad: {e}")
        return f"Error checking availability: {str(e)}"

@tool
def listar_tipos_habitaciones() -> str:
    """List all available room types in the hotel"""
    logger.info("📋 Listing room types")
    
    try:
        data = cargar_hotel_data()
        
        if not data.get("habitaciones"):
            return "No room information available"
        
        resultado = "🏨 **Available Rooms - Hotel AselvIA**\n\n"
        
        for hab in data["habitaciones"]:
            resultado += f"🛏️ **{hab['tipo']}**\n"
            resultado += f"📝 {hab.get('descripcion', 'No description available')}\n"
            resultado += f"💰 {hab['precio']} {hab.get('moneda', 'EUR')} per night\n"
            resultado += f"🏠 Total rooms: {hab['total']}\n\n"
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error en listar_tipos_habitaciones: {e}")
        return f"Error getting room types: {str(e)}"

@tool
def crear_reserva(nombre: str, tipo_habitacion: str, fecha: str, email: str = "", telefono: str = "", personas: int = 1) -> str:
    """Create a new hotel reservation"""
    logger.info(f"🎫 Creating reservation: {nombre}, {tipo_habitacion}, {fecha}")
    
    try:
        # Intentar normalizar la fecha si no está en formato correcto
        fecha_normalizada = normalizar_fecha(fecha)
        if fecha_normalizada:
            fecha = fecha_normalizada
        
        # Verificar disponibilidad primero
        data = cargar_hotel_data()
        habitacion_info = None
        
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                habitacion_info = hab
                break
        
        if not habitacion_info:
            available_types = ', '.join([h['tipo'] for h in data.get('habitaciones', [])])
            return f"❌ Error: Room type '{tipo_habitacion}' does not exist. Available types: {available_types}"
        
        # Verificar disponibilidad
        reservas = cargar_reservas()
        reservas_count = sum(
            1 for r in reservas 
            if r["tipo_habitacion"].lower() == tipo_habitacion.lower() 
            and r["fecha"] == fecha
        )
        
        if habitacion_info["total"] - reservas_count <= 0:
            return f"❌ No {tipo_habitacion} rooms available for {fecha}"
        
        # Crear la reserva
        nueva_reserva = {
            "id": f"RES{str(uuid.uuid4())[:8]}",
            "nombre": nombre,
            "tipo_habitacion": tipo_habitacion,
            "fecha": fecha,
            "email": email,
            "telefono": telefono,
            "personas": personas,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        reservas.append(nueva_reserva)
        
        if guardar_reservas(reservas):
            # Formatear la fecha para mostrar
            try:
                fecha_obj = datetime.datetime.strptime(fecha, "%Y-%m-%d")
                fecha_formateada = fecha_obj.strftime("%d/%m/%Y")
            except:
                fecha_formateada = fecha
                
            resultado = f"✅ **Reservation Confirmed!**\n\n"
            resultado += f"🎫 **ID:** {nueva_reserva['id']}\n"
            resultado += f"👤 **Guest:** {nueva_reserva['nombre']}\n"
            resultado += f"🛏️ **Room:** {nueva_reserva['tipo_habitacion']}\n"
            resultado += f"📅 **Date:** {fecha_formateada}\n"
            resultado += f"👥 **Guests:** {nueva_reserva['personas']}\n"
            if nueva_reserva['email']:
                resultado += f"📧 **Email:** {nueva_reserva['email']}\n"
            resultado += f"\nThank you for choosing Hotel AselvIA! 🏨"
            
            logger.info(f"✅ Reserva creada: {nueva_reserva['id']}")
            return resultado
        else:
            return "❌ Error saving the reservation"
            
    except Exception as e:
        logger.error(f"Error en crear_reserva: {e}")
        return f"❌ Error creating reservation: {str(e)}"

@tool
def listar_reservas() -> str:
    """List all existing reservations in the hotel"""
    logger.info("📝 Listing reservations")
    
    try:
        reservas = cargar_reservas()
        
        if not reservas:
            return "📝 No reservations currently registered."
        
        resultado = f"📝 **Current Reservations ({len(reservas)} total)**\n\n"
        
        for reserva in reservas:
            resultado += f"🎫 **{reserva['id']}**\n"
            resultado += f"👤 {reserva['nombre']}\n"  
            resultado += f"🛏️ {reserva['tipo_habitacion']}\n"
            resultado += f"📅 {reserva['fecha']}\n"
            resultado += f"👥 {reserva['personas']} guest(s)\n"
            if reserva.get('email'):
                resultado += f"📧 {reserva['email']}\n"
            resultado += "\n"
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error en listar_reservas: {e}")
        return f"Error getting reservations: {str(e)}"

# --- CONFIGURACIÓN DEL AGENTE ---
# Herramientas disponibles
tools = [consultar_disponibilidad, listar_tipos_habitaciones, crear_reserva, listar_reservas]

# Crear prompt personalizado FORZANDO inglés con instrucciones múltiples
prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "YOU ARE STRICTLY ENGLISH-ONLY ASSISTANT. NO SPANISH WORDS ALLOWED AT ALL.\n"
     "ABSOLUTE RULE: Every single word in your response MUST be in English.\n"
     "FORBIDDEN: Any Spanish words like: hola, soy, puedo, ayudarte, reserva, habitación, fecha, gracias, etc.\n"
     "MANDATORY: If you detect ANY Spanish word in your response, rewrite it completely in English.\n\n"
     "You are the English-speaking digital assistant for Hotel AselvIA.\n"
     "Your responsibilities:\n"
     "- Check room availability\n"
     "- Make hotel reservations\n" 
     "- Provide pricing information\n"
     "- Answer questions about the hotel\n"
     "- Show room types when customers ask about rooms or room types\n\n"
     "IMPORTANT: When users ask about room types, rooms available, or what kind of rooms you have,\n"
     "YOU MUST ALWAYS call the listar_tipos_habitaciones function to show them the complete list with prices.\n"
     "DO NOT just describe rooms - ALWAYS USE THE FUNCTION to get real data.\n\n"
     "TOOL USAGE RULES:\n"
     "- For room types/what rooms: CALL listar_tipos_habitaciones()\n"
     "- For availability: CALL consultar_disponibilidad()\n"
     "- For making reservations: CALL crear_reserva()\n"
     "- For viewing bookings: CALL listar_reservas()\n\n"
     "Current date: July 28th, 2025\n"
     "LANGUAGE RULE: ENGLISH ONLY - NO EXCEPTIONS\n"
     "GREETING: Start with 'Hello!' or 'Hi!' never 'Hola!'\n"
     "POLITENESS: Use 'Thank you' never 'Gracias'\n"
     "ASSISTANCE: Say 'I can help you' never 'Puedo ayudarte'\n\n"
     "CRITICAL: Before sending any response, verify EVERY word is English."
    ),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "RESPOND IN ENGLISH ONLY: {input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad")
])

# LLM con configuración optimizada para inglés
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.0,  # Temperatura 0 para máxima consistencia
    api_key=openai_api_key,
    model_kwargs={
        "top_p": 0.8,  # Más restrictivo
        "frequency_penalty": 0.2,  # Penalizar repeticiones
        "presence_penalty": 0.3,   # Penalizar palabras comunes (español)
        "max_tokens": 500,  # Limitar respuesta para control
    }
)

# Crear el agente
agent = create_openai_functions_agent(llm, tools, prompt)

# Memoria por sesión
memorias: Dict[str, ConversationBufferMemory] = {}

def get_agent_executor(session_id: str) -> AgentExecutor:
    """Obtiene o crea un executor de agente con memoria para la sesión"""
    if session_id not in memorias:
        # Crear memoria para la sesión
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        memorias[session_id] = memory
        logger.info(f"💭 Nueva memoria creada para sesión: {session_id}")
    
    # Crear executor con memoria
    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memorias[session_id],
        verbose=True,
        handle_parsing_errors=True
    )

# --- FASTAPI APP ---
app = FastAPI(
    title="Hotel AselvIA - API Simple",
    description="API simplificada para gestión de reservas con LangChain Agent",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS ---
@app.get("/")
def read_root():
    return {
        "mensaje": "Hotel AselvIA API funcionando",
        "version": "2.0.0",
        "agente": "LangChain Functions Agent",
        "herramientas": len(tools)
    }

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(message: ChatMessage):
    """Endpoint principal para chat con el agente - FORZANDO RESPUESTAS EN INGLÉS"""
    try:
        logger.info(f"💬 Mensaje de {message.session_id}: {message.message}")
        
        # Extraer y normalizar fechas del mensaje
        mensaje_procesado, fecha_detectada = extraer_y_normalizar_fechas(message.message)
        
        # MÚLTIPLES CAPAS DE FORZADO DE INGLÉS
        # 1. Prefijo más agresivo para forzar inglés
        mensaje_con_contexto = f"[STRICT ENGLISH RESPONSE REQUIRED - NO SPANISH WORDS ALLOWED] User message: {mensaje_procesado}"
        
        if fecha_detectada:
            logger.info(f"📅 Fecha detectada y normalizada: {fecha_detectada}")
            logger.info(f"📝 Mensaje procesado: {mensaje_procesado}")
        else:
            logger.info("⚠️ No se detectó ninguna fecha en el mensaje")
        
        # Obtener executor para la sesión
        executor = get_agent_executor(message.session_id)
        
        # Ejecutar el agente con el mensaje procesado
        result = executor.invoke({"input": mensaje_con_contexto})
        
        response_text = result["output"]
        
        # 2. VALIDACIÓN AGRESIVA DE RESPUESTA EN ESPAÑOL Y FORZADO A INGLÉS
        spanish_words = ['hola', 'soy', 'puedo', 'ayudarte', 'español', 'estoy', 'aquí', 'para', 
                        'con', 'reserva', 'habitación', 'disponible', 'precio', 'fecha', 'gracias',
                        'hotel', 'aselyia', 'asistente', 'digital', 'necesito', 'ayuda', 'hacer',
                        'consultar', 'información', 'disponibilidad', 'tipos', 'habitaciones',
                        'perfecto', 'detalles', 'podrías', 'decirme', 'tipo', 'gustaría', 'si',
                        'estás', 'seguro', 'mostrar', 'opciones', 'disponibles', 'encantado']
        
        # Solo aplicar respuestas predefinidas en caso de emergencia extrema (cuando el agente falle completamente)
        if any(word in response_text.lower() for word in spanish_words):
            logger.warning(f"⚠️ Detectada respuesta en español: {response_text[:100]}...")
            
            # Solo en casos extremos, usar respuesta predefinida simple
            if len(response_text.strip()) == 0 or "error" in response_text.lower():
                response_text = "Hello! I'm the Hotel AselvIA assistant. I can help you with room bookings, availability checks, and pricing. What can I do for you today?"
                logger.info(f"🚨 Applied emergency English response due to error")
            else:
                logger.info(f"⚠️ Spanish detected but letting agent handle it")
        
        # 3. VALIDACIÓN FINAL - Última verificación anti-español
        final_spanish_check = ['hola', 'soy', 'puedo', 'ayudarte', 'gracias']
        if any(word in response_text.lower() for word in final_spanish_check):
            response_text = "Hello! I'm the Hotel AselvIA assistant. I can help you with room bookings, availability checks, and pricing. What can I do for you today?"
            logger.info(f"🚨 Applied emergency English response")
        
        logger.info(f"🤖 Respuesta final: {response_text[:100]}...")
        
        return ChatResponse(
            response=response_text,
            session_id=message.session_id
        )
        
    except Exception as e:
        logger.error(f"❌ Error en chat: {str(e)}")
        return ChatResponse(
            response=f"I apologize, there was an error processing your request. Please try again.",
            session_id=message.session_id
        )

@app.get("/habitaciones")
def get_habitaciones():
    """Endpoint para obtener tipos de habitaciones"""
    try:
        data = cargar_hotel_data()
        return {"habitaciones": data.get("habitaciones", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/reservas")
def get_reservas():
    """Endpoint para obtener todas las reservas"""
    try:
        reservas = cargar_reservas()
        return {"reservas": reservas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", include_in_schema=False)
def health_check():
    # Silenciar logs de health check
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "agent_ready": True
    }

@app.post("/clear-memory")
def clear_memory():
    """Limpiar la memoria de todas las sesiones"""
    global memorias
    memorias.clear()
    return {"message": "Memory cleared successfully", "status": "success"}

@app.get("/test-fecha/{texto}")
def test_fecha(texto: str):
    """Endpoint para probar la normalización de fechas"""
    fecha_normalizada = normalizar_fecha(texto)
    return {
        "texto_original": texto,
        "fecha_normalizada": fecha_normalizada,
        "fecha_actual": datetime.datetime.now().strftime("%Y-%m-%d")
    }

# Servir archivo de prueba con botón rojo de limpiar memoria
@app.get("/test")
def get_test_page():
    """Página de prueba mejorada con botón rojo de Clear Memory"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hotel AselvIA - English Test Chat</title>
        <meta charset="utf-8">
        <style>
            body { 
                font-family: 'Segoe UI', Arial, sans-serif; 
                max-width: 900px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f5f5f5;
            }
            .header {
                text-align: center;
                margin-bottom: 20px;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-radius: 10px;
            }
            .chat { 
                border: 1px solid #ddd; 
                height: 500px; 
                overflow-y: scroll; 
                padding: 15px; 
                margin: 20px 0; 
                background-color: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .message { 
                margin: 15px 0; 
                padding: 12px 15px; 
                border-radius: 15px; 
                max-width: 80%;
                line-height: 1.4;
            }
            .user { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                margin-left: auto;
                text-align: right; 
            }
            .bot { 
                background-color: #f8f9fa; 
                border: 1px solid #e9ecef;
                margin-right: auto;
            }
            .input-container {
                display: flex;
                gap: 10px;
                margin: 20px 0;
            }
            input[type="text"] { 
                flex: 1;
                padding: 12px 15px; 
                border: 2px solid #ddd;
                border-radius: 25px;
                font-size: 16px;
                outline: none;
                transition: border-color 0.3s;
            }
            input[type="text"]:focus {
                border-color: #667eea;
            }
            .btn {
                padding: 12px 25px; 
                border: none; 
                border-radius: 25px; 
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                transition: all 0.3s;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .btn-send { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .btn-send:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
            }
            .btn-clear { 
                background: linear-gradient(135deg, #ff416c 0%, #ff4757 100%);
                color: white;
            }
            .btn-clear:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(255, 65, 108, 0.4);
            }
            .status {
                text-align: center;
                margin: 10px 0;
                padding: 10px;
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                border-radius: 5px;
                color: #155724;
            }
            .loading {
                opacity: 0.7;
                pointer-events: none;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏨 Hotel AselvIA - English Assistant Test</h1>
            <p>Testing English-only responses with GPT-4o model</p>
        </div>
        
        <div class="status" id="status">
            ✅ Ready - Bot will respond in English only
        </div>
        
        <div id="chat" class="chat"></div>
        
        <div class="input-container">
            <input type="text" id="messageInput" placeholder="Type your message in any language..." 
                   onkeypress="if(event.key==='Enter') sendMessage()">
            <button onclick="sendMessage()" class="btn btn-send">Send</button>
            <button onclick="clearMemory()" class="btn btn-clear">Clear Memory</button>
        </div>
        
        <script>
            const chatDiv = document.getElementById('chat');
            const messageInput = document.getElementById('messageInput');
            const statusDiv = document.getElementById('status');
            let isLoading = false;
            
            function addMessage(message, isUser) {
                const div = document.createElement('div');
                div.className = 'message ' + (isUser ? 'user' : 'bot');
                div.innerHTML = isUser ? '<strong>You:</strong> ' + message : '<strong>Assistant:</strong> ' + message.replace(/\\n/g, '<br>');
                chatDiv.appendChild(div);
                chatDiv.scrollTop = chatDiv.scrollHeight;
            }
            
            function setLoading(loading) {
                isLoading = loading;
                document.body.className = loading ? 'loading' : '';
                statusDiv.innerHTML = loading ? '⏳ Processing...' : '✅ Ready - Bot will respond in English only';
            }
            
            async function sendMessage() {
                if (isLoading) return;
                
                const message = messageInput.value.trim();
                if (!message) return;
                
                addMessage(message, true);
                messageInput.value = '';
                setLoading(true);
                
                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            message: message,
                            session_id: 'test-session'
                        })
                    });
                    
                    const data = await response.json();
                    addMessage(data.response, false);
                } catch (error) {
                    addMessage('❌ Error: ' + error.message, false);
                } finally {
                    setLoading(false);
                }
            }
            
            async function clearMemory() {
                if (isLoading) return;
                
                setLoading(true);
                try {
                    const response = await fetch('/clear-memory', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    
                    if (response.ok) {
                        chatDiv.innerHTML = '';
                        addMessage('✅ Memory cleared! Starting fresh conversation with English-only responses.', false);
                        addMessage('Hello! I am the digital assistant for Hotel AselvIA. I will respond only in English. How can I help you today?', false);
                        statusDiv.innerHTML = '🔄 Memory cleared - Fresh conversation started';
                        setTimeout(() => {
                            statusDiv.innerHTML = '✅ Ready - Bot will respond in English only';
                        }, 3000);
                    }
                } catch (error) {
                    addMessage('❌ Error clearing memory: ' + error.message, false);
                } finally {
                    setLoading(false);
                }
            }
            
            // Mensaje inicial
            addMessage('Hello! I am the digital assistant for Hotel AselvIA. I respond only in English. How can I help you today?', false);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- MAIN ---
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"🚀 Iniciando Hotel AselvIA API Simple en {host}:{port}")
    logger.info(f"🤖 Agente: LangChain Functions Agent")
    logger.info(f"🛠️ Herramientas: {len(tools)}")
    
    uvicorn.run(
        "main:app",  # Corregido para ejecutar main.py
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
