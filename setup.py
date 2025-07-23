#!/usr/bin/env python3
"""
Script de instalación y configuración para el proyecto AselvIA
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def install_requirements():
    """Instala las dependencias del proyecto"""
    print("📦 Instalando dependencias...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencias instaladas correctamente")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error instalando dependencias: {e}")
        return False

def setup_env_file():
    """Configura el archivo .env"""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("📄 El archivo .env ya existe")
        return True
    
    if env_example.exists():
        print("📄 Copiando .env.example a .env...")
        with open(env_example, 'r') as f:
            content = f.read()
        
        with open(env_file, 'w') as f:
            f.write(content)
        
        print("⚠️  IMPORTANTE: Edita el archivo .env y configura tu OPENAI_API_KEY")
        print("   Ejemplo: OPENAI_API_KEY=sk-tu-clave-aqui")
        return True
    else:
        print("❌ No se encontró .env.example")
        return False

def verify_data_files():
    """Verifica y crea archivos de datos necesarios"""
    hotel_data_file = Path("hotel_data.json")
    reservas_file = Path("reservas.json")
    
    # Verificar hotel_data.json
    if not hotel_data_file.exists():
        print("📄 Creando hotel_data.json...")
        default_hotel_data = {
            "habitaciones": [
                {
                    "tipo": "Doble Estándar",
                    "descripcion": "Habitación para dos personas con todas las comodidades",
                    "precio": 85,
                    "moneda": "EUR",
                    "total": 10
                },
                {
                    "tipo": "Suite Junior",
                    "descripcion": "Suite espaciosa con sala de estar separada",
                    "precio": 140,
                    "moneda": "EUR",
                    "total": 3
                }
            ]
        }
        
        with open(hotel_data_file, 'w', encoding='utf-8') as f:
            json.dump(default_hotel_data, f, indent=2, ensure_ascii=False)
        
        print("✅ hotel_data.json creado")
    else:
        print("✅ hotel_data.json ya existe")
    
    # Verificar reservas.json
    if not reservas_file.exists():
        print("📄 Creando reservas.json...")
        with open(reservas_file, 'w', encoding='utf-8') as f:
            json.dump([], f, indent=2)
        print("✅ reservas.json creado")
    else:
        print("✅ reservas.json ya existe")

def run_tests():
    """Ejecuta pruebas básicas"""
    print("🧪 Ejecutando pruebas básicas...")
    
    try:
        # Probar importaciones
        import fastapi
        import socketio
        import uvicorn
        from dotenv import load_dotenv
        print("✅ Todas las dependencias principales se importan correctamente")
        
        # Probar carga de archivos
        import json
        with open("hotel_data.json", 'r', encoding='utf-8') as f:
            data = json.load(f)
        print("✅ hotel_data.json se carga correctamente")
        
        with open("reservas.json", 'r', encoding='utf-8') as f:
            reservas = json.load(f)
        print("✅ reservas.json se carga correctamente")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en las pruebas: {e}")
        return False

def main():
    """Función principal de instalación"""
    print("🚀 Configurando proyecto AselvIA...\n")
    
    success = True
    
    # Instalar dependencias
    if not install_requirements():
        success = False
    
    print()
    
    # Configurar archivo .env
    if not setup_env_file():
        success = False
    
    print()
    
    # Verificar archivos de datos
    verify_data_files()
    
    print()
    
    # Ejecutar pruebas
    if not run_tests():
        success = False
    
    print("\n" + "="*50)
    
    if success:
        print("✅ ¡Configuración completada exitosamente!")
        print("\n📋 Próximos pasos:")
        print("1. Edita el archivo .env y configura tu OPENAI_API_KEY")
        print("2. Ejecuta: python main.py")
        print("3. O ejecuta: uvicorn main:asgi_app --host 0.0.0.0 --port 8000 --reload")
    else:
        print("❌ Hubo errores durante la configuración")
        print("   Revisa los mensajes anteriores y corrige los problemas")
    
    print("="*50)

if __name__ == "__main__":
    main()
