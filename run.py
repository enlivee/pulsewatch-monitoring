#!/usr/bin/env python3
"""
PulseWatch - Скрипт запуска приложения.
Запуск: python3 run.py
"""
import sys
import uvicorn

if __name__ == "__main__":
    port = 8000
    host = "127.0.0.1"

    print("=" * 65)
    print(" 🚀  PulseWatch — Система мониторинга веб-сервисов")
    print(f" 🌐  Веб-интерфейс:   http://{host}:{port}/")
    print(f" 📚  Swagger API:     http://{host}:{port}/docs")
    print(f" 📑  ReDoc API:       http://{host}:{port}/redoc")
    print("=" * 65)

    uvicorn.run("app.main:app", host=host, port=port, reload=True)
