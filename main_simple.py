import os
import json
import uuid
import datetime
import logging
from typing import Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

# Configuración
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# --- HERRAMIENTAS PARA EL AGENTE ---
@tool
def consultar_disponibilidad(tipo_habitacion: str, fecha: str) -> str:
    """Consulta la disponibilidad de habitaciones para una fecha específica"""
    logger.info(f"🔍 Consultando disponibilidad: {tipo_habitacion} para {fecha}")
    
    try:
        data = cargar_hotel_data()
        
        # Buscar información de la habitación
        habitacion_info = None
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                habitacion_info = hab
                break
        
        if not habitacion_info:
            return f"No encontré el tipo de habitación '{tipo_habitacion}'. Los tipos disponibles son: {', '.join([h['tipo'] for h in data.get('habitaciones', [])])}"
        
        # Contar reservas para esa fecha
        reservas = cargar_reservas()
        reservas_count = sum(
            1 for r in reservas 
            if r["tipo_habitacion"].lower() == tipo_habitacion.lower() 
            and r["fecha"] == fecha
        )
        
        disponibles = habitacion_info["total"] - reservas_count
        
        resultado = f"📊 Disponibilidad para {fecha}:\n"
        resultado += f"🛏️ {habitacion_info['tipo']}\n"
        resultado += f"💰 {habitacion_info['precio']} {habitacion_info.get('moneda', 'EUR')} por noche\n"
        resultado += f"🏠 Disponibles: {max(0, disponibles)} de {habitacion_info['total']} habitaciones\n"
        
        if disponibles > 0:
            resultado += f"✅ Hay habitaciones disponibles para reservar"
        else:
            resultado += f"❌ No hay habitaciones disponibles para esta fecha"
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error en consultar_disponibilidad: {e}")
        return f"Error consultando disponibilidad: {str(e)}"

@tool
def listar_tipos_habitaciones() -> str:
    """Lista todos los tipos de habitaciones disponibles en el hotel"""
    logger.info("📋 Listando tipos de habitaciones")
    
    try:
        data = cargar_hotel_data()
        
        if not data.get("habitaciones"):
            return "No hay información de habitaciones disponible"
        
        resultado = "🏨 **Habitaciones Disponibles - Hotel AselvIA**\n\n"
        
        for hab in data["habitaciones"]:
            resultado += f"🛏️ **{hab['tipo']}**\n"
            resultado += f"📝 {hab.get('descripcion', 'Sin descripción')}\n"
            resultado += f"💰 {hab['precio']} {hab.get('moneda', 'EUR')} por noche\n"
            resultado += f"🏠 Total de habitaciones: {hab['total']}\n\n"
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error en listar_tipos_habitaciones: {e}")
        return f"Error obteniendo tipos de habitaciones: {str(e)}"

@tool
def crear_reserva(nombre: str, tipo_habitacion: str, fecha: str, email: str = "", telefono: str = "", personas: int = 1) -> str:
    """Crea una nueva reserva para el hotel"""
    logger.info(f"🎫 Creando reserva: {nombre}, {tipo_habitacion}, {fecha}")
    
    try:
        # Verificar disponibilidad primero
        data = cargar_hotel_data()
        habitacion_info = None
        
        for hab in data.get("habitaciones", []):
            if hab["tipo"].lower() == tipo_habitacion.lower():
                habitacion_info = hab
                break
        
        if not habitacion_info:
            return f"❌ Error: No existe el tipo de habitación '{tipo_habitacion}'"
        
        # Verificar disponibilidad
        reservas = cargar_reservas()
        reservas_count = sum(
            1 for r in reservas 
            if r["tipo_habitacion"].lower() == tipo_habitacion.lower() 
            and r["fecha"] == fecha
        )
        
        if habitacion_info["total"] - reservas_count <= 0:
            return f"❌ No hay habitaciones {tipo_habitacion} disponibles para {fecha}"
        
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
            resultado = f"✅ **¡Reserva Confirmada!**\n\n"
            resultado += f"🎫 **ID:** {nueva_reserva['id']}\n"
            resultado += f"👤 **Cliente:** {nueva_reserva['nombre']}\n"
            resultado += f"🛏️ **Habitación:** {nueva_reserva['tipo_habitacion']}\n"
            resultado += f"📅 **Fecha:** {nueva_reserva['fecha']}\n"
            resultado += f"👥 **Personas:** {nueva_reserva['personas']}\n"
            if nueva_reserva['email']:
                resultado += f"📧 **Email:** {nueva_reserva['email']}\n"
            resultado += f"\n¡Gracias por elegir Hotel AselvIA! 🏨"
            
            logger.info(f"✅ Reserva creada: {nueva_reserva['id']}")
            return resultado
        else:
            return "❌ Error guardando la reserva"
            
    except Exception as e:
        logger.error(f"Error en crear_reserva: {e}")
        return f"❌ Error creando reserva: {str(e)}"

@tool
def listar_reservas() -> str:
    """Lista todas las reservas existentes en el hotel"""
    logger.info("📝 Listando reservas")
    
    try:
        reservas = cargar_reservas()
        
        if not reservas:
            return "📝 No hay reservas registradas actualmente."
        
        resultado = f"📝 **Reservas Actuales ({len(reservas)} total)**\n\n"
        
        for reserva in reservas:
            resultado += f"🎫 **{reserva['id']}**\n"
            resultado += f"👤 {reserva['nombre']}\n"  
            resultado += f"🛏️ {reserva['tipo_habitacion']}\n"
            resultado += f"📅 {reserva['fecha']}\n"
            resultado += f"👥 {reserva['personas']} persona(s)\n"
            if reserva.get('email'):
                resultado += f"📧 {reserva['email']}\n"
            resultado += "\n"
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error en listar_reservas: {e}")
        return f"Error obteniendo reservas: {str(e)}"

# --- CONFIGURACIÓN DEL AGENTE ---
# Herramientas disponibles
tools = [consultar_disponibilidad, listar_tipos_habitaciones, crear_reserva, listar_reservas]

# Prompt del sistema
prompt = hub.pull("hwchase17/openai-functions-agent")

# LLM
llm = ChatOpenAI(
    model="gpt-4-turbo",
    temperature=0,
    api_key=openai_api_key
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
        
        # Agregar mensaje del sistema
        system_message = SystemMessage(content=
            "Eres el asistente digital del hotel AselvIA. Solo gestionas reservas, tarifas y disponibilidad de este hotel. "
            "Responde siempre en español de manera amigable y profesional. "
            "Utiliza las herramientas disponibles para consultar información actualizada. "
            "Si necesitas crear una reserva, asegúrate de tener nombre, tipo de habitación y fecha mínimo. "
            "Presenta la información de manera clara y atractiva usando emojis cuando sea apropiado."
        )
        memory.chat_memory.add_message(system_message)
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
    """Endpoint principal para chat con el agente"""
    try:
        logger.info(f"💬 Mensaje de {message.session_id}: {message.message}")
        
        # Obtener executor para la sesión
        executor = get_agent_executor(message.session_id)
        
        # Ejecutar el agente
        result = executor.invoke({"input": message.message})
        
        response_text = result["output"]
        logger.info(f"🤖 Respuesta: {response_text[:100]}...")
        
        return ChatResponse(
            response=response_text,
            session_id=message.session_id
        )
        
    except Exception as e:
        logger.error(f"❌ Error en chat: {str(e)}")
        return ChatResponse(
            response=f"Disculpa, ha ocurrido un error: {str(e)}",
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

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "agent_ready": True
    }

# Servir archivo de prueba
@app.get("/test")
def get_test_page():
    """Página de prueba simple"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hotel AselvIA - Test Simple</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .chat { border: 1px solid #ccc; height: 400px; overflow-y: scroll; padding: 10px; margin: 10px 0; }
            .message { margin: 10px 0; padding: 10px; border-radius: 5px; }
            .user { background-color: #e3f2fd; text-align: right; }
            .bot { background-color: #f5f5f5; }
            input[type="text"] { width: 70%; padding: 10px; }
            button { padding: 10px 20px; background-color: #2196f3; color: white; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <h1>🏨 Hotel AselvIA - Test Chat</h1>
        <div id="chat" class="chat"></div>
        <input type="text" id="messageInput" placeholder="Escribe tu mensaje..." onkeypress="if(event.key==='Enter') sendMessage()">
        <button onclick="sendMessage()">Enviar</button>
        
        <script>
            const chatDiv = document.getElementById('chat');
            const messageInput = document.getElementById('messageInput');
            
            function addMessage(message, isUser) {
                const div = document.createElement('div');
                div.className = 'message ' + (isUser ? 'user' : 'bot');
                div.innerHTML = isUser ? '<strong>Tú:</strong> ' + message : '<strong>Bot:</strong> ' + message.replace(/\\n/g, '<br>');
                chatDiv.appendChild(div);
                chatDiv.scrollTop = chatDiv.scrollHeight;
            }
            
            async function sendMessage() {
                const message = messageInput.value.trim();
                if (!message) return;
                
                addMessage(message, true);
                messageInput.value = '';
                
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
                    addMessage('Error: ' + error.message, false);
                }
            }
            
            // Mensaje inicial
            addMessage('¡Hola! Soy el asistente del Hotel AselvIA. ¿En qué puedo ayudarte?', false);
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)

# --- MAIN ---
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"🚀 Iniciando Hotel AselvIA API Simple en {host}:{port}")
    logger.info(f"🤖 Agente: LangChain Functions Agent")
    logger.info(f"🛠️ Herramientas: {len(tools)}")
    
    uvicorn.run(
        "main_simple:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
