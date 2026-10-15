#!/usr/bin/env python3
"""
Control de la mascota desde la línea de comandos.

Lo usa Claude cuando le pedís algo sobre la mascota, y también sirve para
probar a mano.

    python control.py estado pensando    cambia el estado
    python control.py decir "Hola" 5     muestra un mensaje N segundos
    python control.py uso                imprime el uso restante
    python control.py barra              imprime la línea para la status line
    python control.py config             imprime dónde está el config.json

Para abrirla, el comando es arrancar.py.

Usa solo la librería estándar: no necesita PySide6.
"""
import json
import sys
import urllib.request
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))

from config import CFG, ESTADOS, ARCHIVO_CONFIG  # noqa: E402

BASE = f"http://{CFG['host']}:{CFG['puerto']}"


def _pedir(ruta, cuerpo):
    pedido = urllib.request.Request(
        BASE + ruta,
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(pedido, timeout=2).close()


def estado(nombre):
    if nombre not in ESTADOS:
        print(f"Estado desconocido: {nombre}. Los válidos son: {', '.join(ESTADOS)}")
        return 1
    try:
        _pedir("/estado", {"estado": nombre})
        print(f"Estado: {nombre}")
        return 0
    except Exception:
        print("La mascota no responde. Abrila con el comando /mascota:abrir.")
        return 1


def decir(texto, segundos=None):
    cuerpo = {"texto": texto}
    if segundos is not None:
        cuerpo["segundos"] = segundos
    try:
        _pedir("/decir", cuerpo)
        print(f"Dijo: {texto}")
        return 0
    except Exception:
        print("La mascota no responde. Abrila con el comando /mascota:abrir.")
        return 1


def mostrar_uso():
    import uso  # se importa acá para no cargarlo cuando no hace falta

    frase = uso.resumen()
    if frase:
        print(frase)
    else:
        print("Todavía no hay datos de uso. Hace falta configurar la status line "
              "(ver el comando 'barra'), y solo funciona en planes Pro y Max.")
    return 0


def mostrar_barra():
    """Imprime el valor exacto para statusLine.command en settings.json."""
    guion = (CARPETA / "statusline.py").as_posix()
    print(f'"{sys.executable}" "{guion}"')
    return 0


def mostrar_config():
    """Imprime dónde está el archivo de configuración."""
    print(ARCHIVO_CONFIG)
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 1

    orden, resto = argv[0], argv[1:]

    if orden == "estado" and resto:
        return estado(resto[0])
    if orden == "decir" and resto:
        segundos = int(resto[1]) if len(resto) > 1 and resto[1].isdigit() else None
        return decir(resto[0], segundos)
    if orden == "uso":
        return mostrar_uso()
    if orden == "barra":
        return mostrar_barra()
    if orden == "config":
        return mostrar_config()

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
