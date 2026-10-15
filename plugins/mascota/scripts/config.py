"""
Configuración central del proyecto.

Acá viven los valores que comparten todos los archivos (la mascota, el
control y la status line), así no hay que repetirlos ni mantenerlos
sincronizados.

La primera vez que se ejecuta crea un config.json en la carpeta de datos.
Si editás ese archivo, tus valores pisan a los de acá.
"""
import json
import os
from pathlib import Path

# --- Rutas ---
CARPETA_SCRIPTS = Path(__file__).resolve().parent
CARPETA_PLUGIN = CARPETA_SCRIPTS.parent
CARPETA_SPRITES = CARPETA_PLUGIN / "sprites"


def _carpeta_datos():
    """
    Dónde guardamos configuración, entorno de Python y último uso conocido.

    Claude Code le da a cada plugin una carpeta propia que sobrevive a las
    actualizaciones: CLAUDE_PLUGIN_DATA. Fuera del plugin usamos la de siempre.
    """
    del_plugin = os.environ.get("CLAUDE_PLUGIN_DATA")
    if del_plugin:
        return Path(del_plugin)
    return Path.home() / ".claude-mascota"


CARPETA_DATOS = _carpeta_datos()
ARCHIVO_CONFIG = CARPETA_DATOS / "config.json"

# El uso lo escribe la status line, que puede correr sin el plugin cargado
# (y por lo tanto sin CLAUDE_PLUGIN_DATA). Por eso va siempre en el home.
ARCHIVO_USO = Path.home() / ".claude-mascota" / "uso.json"

# --- Valores por defecto ---
PREDETERMINADA = {
    "host": "127.0.0.1",        # solo tu máquina; no lo cambies salvo que sepas por qué
    "puerto": 8765,
    "piel": "",                 # qué dibujos usar; "" = el primero que encuentre
    "tamanio": 128,             # alto y ancho del personaje, en píxeles
    "ancho_ventana": 240,
    "alto_globo": 115,
    "ms_por_frame": 400,        # velocidad de la animación
    "segundos_festejo": 3,      # cuánto dura "listo" antes de volver a "esperando"
    "segundos_globo": 6,        # cuánto dura un mensaje suelto
    "minutos_aviso_uso": 30,    # cada cuánto avisa el uso restante (0 = nunca)
    "abrir_al_iniciar": True,   # abrirla sola al empezar una sesión de Claude Code
    "margen_pantalla": 40,
}


def cargar():
    """Devuelve la configuración: los valores por defecto, pisados por config.json."""
    valores = dict(PREDETERMINADA)
    try:
        CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
        if ARCHIVO_CONFIG.exists():
            guardados = json.loads(ARCHIVO_CONFIG.read_text(encoding="utf-8"))
            if isinstance(guardados, dict):
                valores.update(guardados)
        else:
            ARCHIVO_CONFIG.write_text(
                json.dumps(PREDETERMINADA, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    except (OSError, json.JSONDecodeError):
        # Si algo falla, seguimos con los valores por defecto: nunca romper por esto.
        pass
    return valores


CFG = cargar()

# --- Estados de la mascota ---
# El orden define el del menú y el de las teclas 1..N.
# Cada estado es una lista de frames de reserva, por si todavía no hay dibujos.
FRAMES_EMOJI = {
    "esperando": ["😴", "💤"],
    "pensando": ["🤔", "🧐", "🤔", "💭"],
    "permiso": ["❗", "🙋"],
    "listo": ["🎉", "🥳"],
    "cansado": ["😵", "😮‍💨"],
}

ESTADOS = list(FRAMES_EMOJI)

# Qué dice la mascota en cada estado: (texto, segundos visible).
# segundos = None  -> el globo queda hasta que cambie el estado.
# valor None       -> no dice nada (y oculta el globo).
MENSAJES = {
    "esperando": None,
    "pensando": ("Preparando respuesta…", None),
    "permiso": ("¡Necesito tu permiso!", None),
    "listo": ("¡Ya está!", CFG["segundos_festejo"]),
    "cansado": ("Llegamos al límite de uso 😮‍💨", None),
}

# Avisos que no son un estado en sí: se mandan como /estado/<clave> y
# equivalen a un estado más un mensaje.
AVISOS = {
    "error": ("esperando", "La respuesta falló ⚠️"),
}

# Qt permite "vestir" los widgets con una sintaxis parecida a CSS
ESTILO_GLOBO = """
QLabel {
    background-color: #ffffff;
    color: #222222;
    border: 2px solid #222222;
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 13px;
}
"""
