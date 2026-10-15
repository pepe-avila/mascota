#!/usr/bin/env python3
"""
Status line de Claude Code (Base 6).

Claude Code ejecuta este script y le pasa por stdin un JSON con información
de la sesión. Nosotros hacemos dos cosas con eso:

  1. Imprimir la barra que se ve abajo en Claude Code.
  2. Guardar el uso restante en ~/.claude-mascota/uso.json, que es lo que
     después lee la mascota.

Regla de oro: este script nunca debe romper. Si falla, Claude Code se queda
sin barra de estado. Por eso todo está envuelto en try/except.

No necesita PySide6: usa solo la librería estándar, así arranca rápido.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

CARPETA_DATOS = Path.home() / ".claude-mascota"
ARCHIVO_USO = CARPETA_DATOS / "uso.json"


def extraer(datos):
    """Se queda solo con los campos que nos interesan, con nombres en castellano."""
    limites = datos.get("rate_limits") or {}

    def ventana(clave):
        bloque = limites.get(clave)
        if not isinstance(bloque, dict):
            return None
        return {
            "usado": bloque.get("used_percentage"),
            "renueva": bloque.get("resets_at"),
        }

    contexto = datos.get("context_window") or {}
    modelo = datos.get("model") or {}

    return {
        "actualizado": time.time(),
        "modelo": modelo.get("display_name"),
        "contexto_usado": contexto.get("used_percentage"),
        "limites": {
            "cinco_horas": ventana("five_hour"),
            "siete_dias": ventana("seven_day"),
        },
    }


def guardar(resumen):
    """
    Escribe uso.json de forma atómica: primero un archivo temporal y después
    lo renombra. Así la mascota nunca lee un archivo a medio escribir.
    """
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    temporal = tempfile.NamedTemporaryFile(
        "w", delete=False, dir=CARPETA_DATOS, encoding="utf-8", suffix=".tmp"
    )
    try:
        json.dump(resumen, temporal, ensure_ascii=False)
        temporal.flush()
        os.fsync(temporal.fileno())
    finally:
        temporal.close()
    os.replace(temporal.name, ARCHIVO_USO)


def barra(datos, resumen):
    """Arma el texto de una línea que se ve abajo en Claude Code."""
    GRIS = "\033[2m"
    FIN = "\033[0m"

    espacio = datos.get("workspace") or {}
    carpeta = Path(espacio.get("current_dir") or datos.get("cwd") or ".").name

    trozos = [carpeta]

    if resumen.get("modelo"):
        trozos.append(f"{GRIS}{resumen['modelo']}{FIN}")

    contexto = resumen.get("contexto_usado")
    if contexto is not None:
        trozos.append(f"{GRIS}ctx {float(contexto):.0f}%{FIN}")

    limites = []
    for etiqueta, clave in (("5h", "cinco_horas"), ("7d", "siete_dias")):
        ventana = resumen["limites"].get(clave)
        if ventana and ventana.get("usado") is not None:
            restante = 100 - float(ventana["usado"])
            limites.append(f"{etiqueta} {restante:.0f}%")
    if limites:
        trozos.append(f"{GRIS}queda {' · '.join(limites)}{FIN}")

    return " | ".join(trozos)


def main():
    datos = json.load(sys.stdin)
    if not isinstance(datos, dict):
        return

    resumen = extraer(datos)

    # Guardamos aunque la impresión falle, y viceversa: son independientes.
    try:
        guardar(resumen)
    except OSError:
        pass

    print(barra(datos, resumen))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Nunca dejamos que un error nuestro rompa la barra de Claude Code.
        pass
