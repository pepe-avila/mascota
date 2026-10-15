"""
Descubrimiento de los dibujos.

Cada "piel" es un conjunto completo de dibujos: el gato, el perro, el robot.
Son carpetas dentro de sprites/, y se aceptan dos formas de nombrar:

    sprites/<piel>/<estado>_<n>.png     p. ej. sprites_cat/pensando_0.png
    sprites/<piel>/<estado>/<n>.png     p. ej. mi_piel/pensando/0.png

Si un estado no tiene dibujos, se usa el de reserva que indique RESPALDO,
y si tampoco hay, la mascota muestra el emoji de ese estado.

Solo librería estándar: acá no se abre ninguna imagen, se buscan rutas.
"""
import re
from pathlib import Path

from config import CARPETA_SPRITES, ESTADOS

# Qué usar cuando un estado no tiene dibujos propios.
# Un gato dormido sirve igual para "cansado".
RESPALDO = {
    "cansado": "esperando",
}

NUMERO = re.compile(r"(\d+)")


def _orden(ruta):
    """Ordena 0, 1, 2, 10 por número, no alfabéticamente."""
    numeros = NUMERO.findall(ruta.stem)
    return (int(numeros[-1]) if numeros else 0, ruta.name)


def _archivos_directos(carpeta, estado):
    """Forma <estado>_<n>.png dentro de la carpeta de la piel."""
    return sorted(carpeta.glob(f"{estado}_*.png"), key=_orden)


def _archivos_en_subcarpeta(carpeta, estado):
    """Forma <estado>/<n>.png dentro de la carpeta de la piel."""
    sub = carpeta / estado
    return sorted(sub.glob("*.png"), key=_orden) if sub.is_dir() else []


def _propios(carpeta, estado):
    return _archivos_directos(carpeta, estado) or _archivos_en_subcarpeta(carpeta, estado)


def pieles():
    """
    Nombres de los conjuntos de dibujos disponibles, en orden alfabético.

    Una carpeta cuenta como piel si tiene dibujos de al menos un estado.
    """
    if not CARPETA_SPRITES.is_dir():
        return []
    encontradas = []
    for carpeta in sorted(CARPETA_SPRITES.iterdir()):
        if not carpeta.is_dir():
            continue
        if any(_propios(carpeta, estado) for estado in ESTADOS):
            encontradas.append(carpeta.name)
    return encontradas


def nombre_corto(piel):
    """'sprites_cat' se muestra como 'cat'."""
    return piel[len("sprites_"):] if piel.startswith("sprites_") else piel


def elegir(preferida=""):
    """
    Devuelve la piel a usar: la pedida si existe, si no la primera que haya,
    y "" si no hay ningún dibujo (la mascota cae a los emojis).
    """
    disponibles = pieles()
    if not disponibles:
        return ""
    if preferida in disponibles:
        return preferida
    # Permitimos escribir "cat" en lugar de "sprites_cat"
    for piel in disponibles:
        if nombre_corto(piel) == preferida:
            return piel
    return disponibles[0]


def rutas(piel, estado):
    """
    Archivos PNG de un estado, en orden. Lista vacía si no hay nada.

    Si el estado no tiene dibujos propios, prueba con el de respaldo.
    """
    if not piel:
        return []
    carpeta = CARPETA_SPRITES / piel
    if not carpeta.is_dir():
        return []

    archivos = _propios(carpeta, estado)
    if archivos:
        return archivos

    suplente = RESPALDO.get(estado)
    return _propios(carpeta, suplente) if suplente else []
