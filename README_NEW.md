# Hotel AselvIA - API de Reservas con IA

Sistema de gestión de reservas de hotel con asistente de IA integrado usando FastAPI, Socket.IO y LangChain.

## 🚀 Características

- **API REST** con FastAPI para operaciones básicas
- **Chat en tiempo real** con Socket.IO
- **Asistente IA** integrado con GPT-4 y LangChain
- **Gestión de reservas** automática
- **Consulta de disponibilidad** en tiempo real
- **Memoria de conversación** por sesión

## 📋 Requisitos

- Python 3.8+
- Clave API de OpenAI
- Dependencias listadas en `requirements.txt`

## 🛠️ Instalación Rápida

### Opción 1: Script Automático (Windows)
```bash
# Ejecutar el instalador automático
install.bat
```

### Opción 2: Instalación Manual

1. **Clonar el repositorio**
   ```bash
   git clone <url-del-repositorio>
   cd backA
   ```

2. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar variables de entorno**
   ```bash
   # Copiar archivo de ejemplo
   copy .env.example .env
   
   # Editar .env y agregar tu API key de OpenAI
   OPENAI_API_KEY=sk-tu-clave-aqui
   ```

4. **Ejecutar setup**
   ```bash
   python setup.py
   ```

## 🚦 Uso

### Iniciar el servidor

```bash
# Opción 1: Usando el script principal
python main.py

# Opción 2: Usando uvicorn directamente
uvicorn main:asgi_app --host 0.0.0.0 --port 8000 --reload
```

### Endpoints disponibles

- `GET /` - Estado de la API
- `GET /health` - Health check
- `GET /habitaciones` - Lista de tipos de habitaciones
- `GET /reservas` - Lista de todas las reservas
- **Socket.IO** en la misma URL para chat en tiempo real

## 📁 Estructura del Proyecto

```
backA/
├── main.py              # Aplicación principal
├── requirements.txt     # Dependencias
├── setup.py            # Script de configuración
├── install.bat         # Instalador para Windows
├── .env.example        # Ejemplo de variables de entorno
├── hotel_data.json     # Datos de las habitaciones
├── reservas.json       # Base de datos de reservas
└── README.md          # Este archivo
```

## 🔧 Configuración

### Variables de entorno (.env)

```bash
# Obligatorio
OPENAI_API_KEY=sk-tu-clave-api-de-openai

# Opcional
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

### Datos del hotel (hotel_data.json)

```json
{
  "habitaciones": [
    {
      "tipo": "Doble Estándar",
      "descripcion": "Habitación para dos personas...",
      "precio": 85,
      "moneda": "EUR",
      "total": 10
    }
  ]
}
```

## 🤖 Uso del Chat IA

El asistente puede ayudar con:

- ✅ Consultar disponibilidad de habitaciones
- ✅ Crear nuevas reservas
- ✅ Listar tipos de habitaciones y precios
- ✅ Mostrar reservas existentes
- ✅ Responder preguntas sobre el hotel

### Ejemplo de conversación:

```
Usuario: "Hola, ¿hay habitaciones disponibles para el 25 de julio?"
Bot: "¡Hola! Te consulto la disponibilidad para el 25 de julio. ¿Qué tipo de habitación te interesa?"

Usuario: "Una doble estándar"
Bot: "Consultando disponibilidad... ✅ Hay 8 habitaciones Doble Estándar disponibles para el 25/07/2024. La tarifa es de 85 EUR por noche."
```

## 🔍 Solución de Problemas

### Error: "OPENAI_API_KEY no está configurada"
- Asegúrate de tener un archivo `.env` con tu clave API
- Verifica que la clave sea válida en tu cuenta de OpenAI

### Error de importación de langgraph
- Ejecuta: `pip install --upgrade langgraph langchain`
- Verifica que todas las dependencias estén instaladas

### Error de conexión Socket.IO
- Verifica que el puerto no esté en uso
- Revisa los logs del servidor para más detalles

### Problemas con archivos JSON
- Ejecuta `python setup.py` para recrear archivos de datos
- Verifica que los archivos JSON tengan formato válido

## 📝 Logs y Debugging

El sistema incluye logging detallado:

```bash
# Habilitar modo debug
DEBUG=true

# Ver logs en tiempo real
python main.py
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

## 🆘 Soporte

Si tienes problemas:

1. Revisa este README
2. Ejecuta `python setup.py` para verificar la configuración
3. Revisa los logs del servidor
4. Abre un issue en el repositorio

---

**¡Gracias por usar Hotel AselvIA!** 🏨✨
