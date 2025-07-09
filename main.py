# main.py
# Punto de entrada principal: Gestiona el servidor y conecta la lógica del agente con los canales de comunicación.

from typing import List, Dict
import socketio
from fastapi import FastAPI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage

# Importaciones desde nuestros módulos locales
from config import llm
from agent import agent_app, GUEST_SYSTEM_PROMPT, MANAGER_SYSTEM_PROMPT
from tools.guest_tools import GUEST_TOOLS
from tools.manager_tools import MANAGER_TOOLS

# --- PASO 1: Inicializar FastAPI y Socket.IO ---
app = FastAPI(title="Servidor de Agente Unificado")
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# --- PASO 2: Definir todas las rutas HTTP en la app de FastAPI ---
# ¡IMPORTANTE! Todas las rutas @app.get, @app.post, etc., deben definirse aquí,
# ANTES de envolver la app con Socket.IO.
@app.get("/")
def read_root():
    """Endpoint de prueba para verificar que el servidor HTTP está funcionando."""
    return {"status": "Servidor FastAPI funcionando correctamente."}

# --- PASO 3: Envolver la app de FastAPI con Socket.IO ---
# Esto crea la aplicación final que Uvicorn debe ejecutar.
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)


# --- PASO 4: Definir la lógica y los eventos de Socket.IO ---
# El estado de la conversación se guarda en memoria.
conversation_histories: Dict[str, List[BaseMessage]] = {}

@sio.event
async def connect(sid, environ):
    print(f"Cliente conectado: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Cliente desconectado: {sid}")
    session_id = f"socket:{sid}"
    if session_id in conversation_histories:
        del conversation_histories[session_id]
        print(f"Historial de conversación para {sid} eliminado.")

@sio.event
async def chat_message(sid, data):
    query = data.get('query')
    is_manager = data.get('is_manager', False)
    
    # Selección dinámica de herramientas y prompt según el rol
    if is_manager:
        active_tools, active_prompt = MANAGER_TOOLS, MANAGER_SYSTEM_PROMPT
        print(f"Sesión {sid} en MODO GERENTE.")
    else:
        active_tools, active_prompt = GUEST_TOOLS, GUEST_SYSTEM_PROMPT
        print(f"Sesión {sid} en MODO HUÉSPED.")
        
    session_id = f"socket:{sid}"
    history = conversation_histories.get(session_id, [])
    
    # Vinculamos las herramientas al modelo para esta petición específica
    model_with_active_tools = llm.bind_tools(active_tools)
    
    # Construimos el estado inicial para la ejecución del grafo
    inputs = {
        "messages": [SystemMessage(content=active_prompt)] + history + [HumanMessage(content=query)],
        "tools": active_tools,
        "model_with_tools": model_with_active_tools
    }
    
    try:
        async for event in agent_app.astream_events(inputs, version="v2", config={"recursion_limit": 10}):
            kind = event["event"]
            if kind == "on_tool_start":
                await sio.emit('tool_call', {'name': event.get('name'), 'args': event['data'].get('input')}, to=sid)
            elif kind == "on_chain_end" and event.get("name") == "agent":
                final_output = event["data"].get("output", {})
                if final_output and final_output.get("messages"):
                    response_message = final_output["messages"][-1]
                    # Asegurarse de que el mensaje de respuesta sea de tipo AIMessage
                    if isinstance(response_message, AIMessage):
                        response_text = response_message.content
                        # Actualizar historial
                        conversation_histories[session_id] = history + [HumanMessage(content=query), AIMessage(content=response_text)]
                        # Enviar respuesta final
                        await sio.emit('final_response', {'content': response_text}, to=sid)
    except Exception as e:
        print(f"ERROR en la sesión {sid}: {e}")
        await sio.emit('error', {'content': f"Ha ocurrido un error en el servidor: {e}"}, to=sid)

