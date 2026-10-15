#!/usr/bin/env python3
"""
Arranque de la mascota. Es lo que ejecuta el comando /mascota:abrir.

Hace tres cosas, en orden, de a un arranque por vez en toda la máquina:

  1. Si la mascota ya está abierta, no hace nada más.
  2. Se asegura de que exista un entorno de Python con PySide6. La primera
     vez lo crea e instala la dependencia; después ya está listo.
  3. Lanza la ventana y espera a que responda.

Todo lo que imprime lo lee Claude, así que los mensajes están escritos para
que se entiendan tal cual.

Usa solo la librería estándar: tiene que poder correr con el Python del
sistema, antes de que exista ningún entorno.
"""
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA))

from config import CFG, CARPETA_DATOS, ARCHIVO_CONFIG  # noqa: E402

SALUD = f"http://{CFG['host']}:{CFG['puerto']}/salud"
VENV = CARPETA_DATOS / "venv"
ARCHIVO_CANDADO = CARPETA_DATOS / "arrancar.lock"
SEGUNDOS_ARRANQUE = 20
MINIMO_PYTHON = (3, 9)


def esta_abierta(espera=1):
    try:
        urllib.request.urlopen(SALUD, timeout=espera).close()
        return True
    except Exception:
        return False


def python_del_entorno():
    """Ruta al intérprete dentro del entorno, exista o no todavía."""
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def tiene_pyside(interprete):
    try:
        resultado = subprocess.run(
            [str(interprete), "-c", "import PySide6"],
            capture_output=True, timeout=60,
        )
        return resultado.returncode == 0
    except Exception:
        return False


def preparar_entorno():
    """
    Devuelve (interprete, hubo_que_instalar).

    Si el Python que nos está ejecutando ya tiene PySide6, lo usamos tal cual.
    Si no, armamos un entorno propio en la carpeta de datos del plugin.
    """
    if tiene_pyside(sys.executable):
        return sys.executable, False

    interprete = python_del_entorno()
    if interprete.exists() and tiene_pyside(interprete):
        return str(interprete), False

    print("Preparando el entorno de Python por primera vez. Puede tardar un minuto…",
          flush=True)

    if not interprete.exists():
        CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)],
            check=True, capture_output=True, timeout=300,
        )

    subprocess.run(
        [str(interprete), "-m", "pip", "install", "--quiet",
         "--disable-pip-version-check", "PySide6"],
        check=True, capture_output=True, timeout=900,
    )
    return str(interprete), True


def sin_consola(interprete):
    """
    En Windows, python.exe es una aplicación de consola: al lanzarla aparece
    una ventana negra vacía detrás de la mascota. pythonw.exe es el mismo
    intérprete pero sin consola, que es lo que necesita una app con ventana.
    """
    if sys.platform != "win32":
        return interprete
    alternativa = Path(interprete).with_name("pythonw.exe")
    return str(alternativa) if alternativa.exists() else interprete


def lanzar(interprete):
    """Abre la ventana en segundo plano, desprendida de este proceso."""
    opciones = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(CARPETA),
    }
    if sys.platform == "win32":
        # CREATE_NO_WINDOW. No lo combinamos con DETACHED_PROCESS porque
        # Windows ignora el primero cuando están los dos.
        opciones["creationflags"] = 0x08000000
    else:
        opciones["start_new_session"] = True

    subprocess.Popen([sin_consola(interprete), str(CARPETA / "mascota.py")], **opciones)


@contextmanager
def candado():
    """
    Deja pasar un solo arranque a la vez en toda la máquina.

    Claude Desktop lanza varias copias de la extensión casi juntas (chat,
    Cowork, Code), y una sesión de Claude Code puede sumarse con su hook. Sin
    esto, todas ven la mascota cerrada al mismo tiempo y cada una abre la
    suya, o dos pip install escriben a la vez en el mismo entorno.

    El candado lo tiene el sistema operativo: si el proceso muere, se libera
    solo, así que nunca queda trabado.
    """
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVO_CANDADO, "a+b") as archivo:
        if sys.platform == "win32":
            import msvcrt
            archivo.seek(0)
            while True:
                try:
                    # LK_LOCK reintenta durante 10 s y se rinde: seguimos esperando.
                    msvcrt.locking(archivo.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                archivo.seek(0)
                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(archivo, fcntl.LOCK_EX)
            yield   # se libera al cerrar el archivo


def main():
    # El hook de SessionStart pasa --al-iniciar. En ese caso respetamos la
    # preferencia del usuario y no decimos nada: nadie está leyendo.
    al_iniciar = "--al-iniciar" in sys.argv
    if al_iniciar and not CFG.get("abrir_al_iniciar", True):
        return 0

    if sys.version_info < MINIMO_PYTHON:
        version = ".".join(str(n) for n in MINIMO_PYTHON)
        print(f"Hace falta Python {version} o superior. "
              f"Este es {sys.version.split()[0]}. Instalalo desde python.org.")
        return 1

    with candado():
        return abrir()


def abrir():
    """Abre la mascota si hace falta. Se llama con el candado tomado."""
    if esta_abierta():
        print("La mascota ya estaba abierta y sigue conectada.")
        return 0

    try:
        interprete, se_instalo = preparar_entorno()
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or b"").decode(errors="replace").strip()
        print("No pude preparar el entorno de Python.")
        print(detalle[-800:] if detalle else "Sin detalle del error.")
        return 1
    except subprocess.TimeoutExpired:
        print("La instalación de PySide6 tardó demasiado y la corté. "
              "Probá de nuevo con mejor conexión.")
        return 1

    try:
        lanzar(interprete)
    except Exception as error:
        print(f"No pude lanzar la ventana: {error}")
        return 1

    limite = time.time() + SEGUNDOS_ARRANQUE
    while time.time() < limite:
        if esta_abierta():
            if se_instalo:
                print("Listo: preparé el entorno y la mascota quedó andando. "
                      "Las próximas veces abre al instante.")
            else:
                print("La mascota quedó andando.")
            return 0
        time.sleep(0.3)

    print("Lancé la mascota pero todavía no responde. "
          "Fijate si apareció la ventana; si no, puede faltar un entorno gráfico.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
