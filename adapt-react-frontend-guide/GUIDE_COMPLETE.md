# 🔧 Guía de Adaptación Frontend React - Hotel AselvIA

## 📋 Resumen de Cambios

Tu backend ha sido completamente refactorizado y ahora incluye nuevas funcionalidades que requieren actualizaciones en tu frontend React. Esta guía te ayudará a adaptar tu componente Chat para aprovechar todas las mejoras.

## 🚀 Nuevas Funcionalidades del Backend

### ✅ **Características Añadidas:**
1. **Sistema de herramientas inteligente** - El bot ahora reporta qué herramienta está usando
2. **Eventos `tool-used`** - Notifica al frontend cuando usa una herramienta específica
3. **Mejores respuestas** - Consultas específicas de disponibilidad con fechas y tipos
4. **Logging detallado** - Para debugging
5. **Manejo robusto de errores**

---

## 🔄 Cambios Necesarios en tu Frontend

### 1. **Actualizar la URL del Socket**

Tu código actual:
```javascript
const url = process.env.REACT_APP_SOCKET_URL || "http://localhost:8000";
```

**✅ Mantener igual** - Funciona correctamente con el nuevo backend

### 2. **Eventos Socket.IO - CAMBIOS IMPORTANTES**

#### **A. Eventos que YA FUNCIONAN:**
- ✅ `bot-message` - **Sin cambios**
- ✅ `tool-used` - **Ya implementado en tu código**

#### **B. Nuevos eventos disponibles:**
```javascript
// Nuevo evento: Estado de conexión
socketRef.current.on("connection_status", (data) => {
  console.log("Estado de conexión:", data);
  // data: {status: "connected", sid: "..."}
});

// Nuevo evento: Bot escribiendo (mejorado)
socketRef.current.on("bot-typing", (data) => {
  if (data.typing) {
    // Mostrar indicador de "escribiendo..."
    setIsTyping(true);
  } else {
    setIsTyping(false);
  }
});

// Evento ping/pong para mantener conexión
socketRef.current.on("pong", (data) => {
  console.log("Pong recibido:", data.timestamp);
});
```

### 3. **Actualizar el Envío de Mensajes**

#### **Cambio Requerido en `sendMessage`:**

**❌ Tu código actual:**
```javascript
const historial = messages.map((m) => ({
  sender: m.sender,
  text: m.text
})).filter(m => m.sender === "user" || m.sender === "bot");

socketRef.current.emit("user_message", { mensaje: text, historial });
```

**✅ Nuevo código recomendado:**
```javascript
// El backend ahora maneja la memoria automáticamente
socketRef.current.emit("user_message", { mensaje: text });

// O si quieres mantener compatibilidad:
socketRef.current.emit("user_message", text);  // También funciona
```

**🔍 Explicación:** El backend refactorizado maneja la memoria de conversación automáticamente por sesión, por lo que ya no necesitas enviar el historial.

### 4. **Mejorar el Manejo de Herramientas**

#### **Tu función `toolLabel` actual está bien, pero puedes expandirla:**

```javascript
const toolLabel = (tool) => {
  switch (tool) {
    case "consultar_disponibilidad":
      return "🔍 Consultando disponibilidad";
    case "crear_reserva":
      return "📝 Creando reserva";
    case "listar_tipos_habitaciones":
      return "🏨 Consultando tipos de habitaciones";
    case "listar_reservas":
      return "📋 Revisando reservas";
    default:
      return `🛠️ ${tool}`;
  }
};
```

---

## 🎯 Código Completo Actualizado

### **Chat.js - Versión Mejorada:**

```javascript
import React, { useEffect, useRef, useState } from "react";
import io from "socket.io-client";
import "./Chat.css";

function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [toolInUse, setToolInUse] = useState(null);
  const [isTyping, setIsTyping] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState("disconnected");
  const socketRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    const url = process.env.REACT_APP_SOCKET_URL || "http://localhost:8000";
    
    socketRef.current = io(url, {
      transports: ["websocket"],
      secure: true
    });

    // EVENTO: Conexión establecida
    socketRef.current.on("connect", () => {
      console.log("✅ Conectado al servidor");
      setConnectionStatus("connected");
    });

    // EVENTO: Desconexión
    socketRef.current.on("disconnect", () => {
      console.log("❌ Desconectado del servidor");
      setConnectionStatus("disconnected");
    });

    // EVENTO: Estado de conexión (nuevo)
    socketRef.current.on("connection_status", (data) => {
      console.log("Estado de conexión:", data);
      setConnectionStatus(data.status);
    });

    // EVENTO: Mensaje del bot
    socketRef.current.on("bot-message", (text) => {
      setMessages((prev) => [...prev, { sender: "bot", text }]);
      setIsTyping(false); // Detener indicador de escribiendo
    });

    // EVENTO: Herramienta en uso (mejorado)
    socketRef.current.on("tool-used", (data) => {
      if (data.tool) {
        setToolInUse(data.tool);
        setMessages((prev) => [
          ...prev,
          {
            sender: "tool",
            text: `${toolLabel(data.tool)}...`,
            toolData: data.input // Datos adicionales de la herramienta
          }
        ]);
      } else {
        // Quitar el indicador de herramienta
        setToolInUse(null);
        setMessages((prev) => prev.filter((msg) => msg.sender !== "tool"));
      }
    });

    // EVENTO: Bot escribiendo (mejorado)
    socketRef.current.on("bot-typing", (data) => {
      setIsTyping(data.typing);
    });

    // EVENTO: Ping/Pong para mantener conexión
    socketRef.current.on("pong", (data) => {
      console.log("🏓 Pong recibido:", data.timestamp);
    });

    // Limpieza al desmontar
    return () => {
      socketRef.current.disconnect();
    };
  }, []);

  useEffect(() => {
    // Scroll automático al nuevo mensaje
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  // Función mejorada para etiquetas de herramientas
  const toolLabel = (tool) => {
    switch (tool) {
      case "consultar_disponibilidad":
        return "🔍 Consultando disponibilidad";
      case "crear_reserva":
        return "📝 Procesando reserva";
      case "listar_tipos_habitaciones":
        return "🏨 Consultando habitaciones";
      case "listar_reservas":
        return "📋 Revisando reservas";
      default:
        return `🛠️ ${tool}`;
    }
  };

  // Enviar mensaje (simplificado)
  const sendMessage = (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;

    // Agregar mensaje del usuario
    setMessages((prev) => [...prev, { sender: "user", text }]);
    
    // Enviar al servidor (simplificado - el backend maneja la memoria)
    socketRef.current.emit("user_message", { mensaje: text });
    
    // Limpiar input
    setInput("");
    
    // Mostrar indicador de escribiendo
    setIsTyping(true);
  };

  return (
    <div className="chat-container">
      {/* Indicador de conexión */}
      <div className={`connection-status ${connectionStatus}`}>
        {connectionStatus === "connected" ? "🟢 Conectado" : "🔴 Desconectado"}
      </div>

      <div className="chat-messages">
        {messages.map((m, idx) => (
          <div
            key={idx}
            className={`message ${
              m.sender === "user" 
                ? "user" 
                : m.sender === "tool" 
                ? "bot tool-used" 
                : "bot"
            }`}
          >
            {m.text}
          </div>
        ))}
        
        {/* Indicador de escribiendo */}
        {isTyping && (
          <div className="message bot typing-indicator">
            <div className="typing-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
            El asistente está escribiendo...
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-area" onSubmit={sendMessage}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu mensaje..."
          autoFocus
          disabled={connectionStatus !== "connected"}
        />
        <button 
          type="submit" 
          disabled={connectionStatus !== "connected" || !input.trim()}
        >
          Enviar
        </button>
      </form>
    </div>
  );
}

export default Chat;
```

---

## 🎨 CSS Adicional Recomendado

### **Agregar a tu Chat.css:**

```css
/* Indicador de conexión */
.connection-status {
  padding: 8px 12px;
  margin-bottom: 10px;
  border-radius: 5px;
  font-size: 14px;
  font-weight: bold;
  text-align: center;
}

.connection-status.connected {
  background-color: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.connection-status.disconnected {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

/* Indicador de escribiendo */
.typing-indicator {
  opacity: 0.8;
  font-style: italic;
}

.typing-dots {
  display: inline-block;
  margin-right: 10px;
}

.typing-dots span {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #999;
  margin: 0 1px;
  animation: typingAnimation 1.4s infinite ease-in-out both;
}

.typing-dots span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes typingAnimation {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

/* Mejorar herramientas */
.message.tool-used {
  background-color: #e3f2fd;
  color: #1565c0;
  border-left: 4px solid #2196f3;
  font-weight: 500;
}

/* Deshabilitar input cuando no está conectado */
input:disabled, button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
```

---

## 🧪 Testing de la Integración

### **Consultas de Prueba Recomendadas:**

1. **Disponibilidad general:**
   - "¿Qué habitaciones tienen disponibles?"
   - Debe usar: `listar_tipos_habitaciones`

2. **Disponibilidad específica:**
   - "¿Hay disponibilidad para doble estándar el 25 de julio?"
   - Debe usar: `consultar_disponibilidad`

3. **Crear reserva:**
   - "Quiero hacer una reserva"
   - Debe mostrar formulario de datos

4. **Listar reservas:**
   - "Muestra las reservas actuales"
   - Debe usar: `listar_reservas`

---

## 📊 Diferencias Principales

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **Herramientas** | Siempre `listar_tipos_habitaciones` | Herramienta específica según consulta |
| **Eventos** | Solo `bot-message`, `tool-used` | + `connection_status`, `bot-typing`, `pong` |
| **Envío** | Con historial completo | Solo mensaje (memoria automática) |
| **Respuestas** | Genéricas | Específicas con datos reales |
| **Estado** | Sin indicadores | Conexión + escribiendo |

---

## 🚨 Problemas Comunes y Soluciones

### **1. Error de conexión WebSocket**
```javascript
// Agregar manejo de reconexión
socketRef.current.on("connect_error", (error) => {
  console.error("Error de conexión:", error);
  setConnectionStatus("error");
});
```

### **2. Herramientas no se muestran**
- Verifica que el evento `tool-used` esté correctamente configurado
- Revisa la consola del navegador para errores

### **3. Bot no responde**
- Verifica que `OPENAI_API_KEY` esté configurada en el backend
- Revisa los logs del servidor backend

---

## ✅ Checklist de Implementación

- [ ] Actualizar eventos Socket.IO
- [ ] Simplificar envío de mensajes
- [ ] Agregar indicador de conexión
- [ ] Implementar indicador de "escribiendo"
- [ ] Actualizar CSS con nuevos estilos
- [ ] Probar todas las consultas de ejemplo
- [ ] Verificar manejo de errores
- [ ] Testing en diferentes dispositivos

---

**🎉 ¡Con estos cambios tu frontend estará completamente sincronizado con el nuevo backend refactorizado!**
