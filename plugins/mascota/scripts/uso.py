"""
Lectura del uso restante (Base 6).

statusline.py guarda en ~/.claude-mascota/uso.json los datos que Claude Code
le pasa a la status line. Acá los leemos y los convertimos en una frase
corta para el globo de la mascota.

Importante: los planes de Claude miden el uso en dos ventanas, una de
5 horas y otra de 7 días. No hay un "saldo de tokens" para mostrar.
"""
import json
import time
from datetime import datetime

from config import ARCHIVO_USO

# Si el archivo es más viejo que esto, avisamos que el dato está desactualizado
SEGUNDOS_VIEJO = 6 * 60 * 60
UMBRAL_ALERTA = 85  # porcentaje usado a partir del cual conviene avisar


def leer():
    """Devuelve el contenido de uso.json, o None si no existe o está roto."""
    try:
        datos = json.loads(ARCHIVO_USO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return datos if isinstance(datos, dict) else None


def _usado(ventana):
    """Porcentaje usado de una ventana, como número entero, o None."""
    if not isinstance(ventana, dict):
        return None
    try:
        return max(0, min(100, round(float(ventana["usado"]))))
    except (KeyError, TypeError, ValueError):
        return None


def _hora_de_renovacion(ventana):
    """La hora en que se renueva la ventana, en formato HH:MM, o None."""
    if not isinstance(ventana, dict):
        return None
    try:
        return datetime.fromtimestamp(float(ventana["renueva"])).strftime("%H:%M")
    except (KeyError, TypeError, ValueError, OSError):
        return None


def resumen():
    """
    Frase corta con el uso restante, lista para el globo.
    Devuelve None si todavía no hay datos.
    """
    datos = leer()
    if not datos:
        return None

    limites = datos.get("limites") or {}
    cinco_h = limites.get("cinco_horas")
    semana = limites.get("siete_dias")

    usado_5h = _usado(cinco_h)
    usado_7d = _usado(semana)

    if usado_5h is None and usado_7d is None:
        return None

    partes = []
    if usado_5h is not None:
        partes.append(f"{100 - usado_5h}% en estas 5 h")
    if usado_7d is not None:
        partes.append(f"{100 - usado_7d}% esta semana")

    frase = "Te queda " + " y ".join(partes)

    # Si la ventana corta está por llenarse, decimos cuándo se renueva
    if usado_5h is not None and usado_5h >= UMBRAL_ALERTA:
        hora = _hora_de_renovacion(cinco_h)
        if hora:
            frase += f". Se renueva {hora}"

    # Aviso si el dato quedó viejo (por ejemplo, hace rato que no usás Claude Code)
    try:
        if time.time() - float(datos.get("actualizado", 0)) > SEGUNDOS_VIEJO:
            frase += " (dato viejo)"
    except (TypeError, ValueError):
        pass

    return frase


def en_alerta():
    """True si alguna ventana superó el umbral: sirve para que la mascota se preocupe."""
    datos = leer()
    if not datos:
        return False
    limites = datos.get("limites") or {}
    for clave in ("cinco_horas", "siete_dias"):
        usado = _usado(limites.get(clave))
        if usado is not None and usado >= UMBRAL_ALERTA:
            return True
    return False
