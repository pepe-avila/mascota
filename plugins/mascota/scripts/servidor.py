"""
Servidor local de la mascota.

Escucha SOLO en 127.0.0.1 (tu propia máquina) y entiende:

    POST /estado/<nombre>   la vía de los hooks: el estado va en la ruta,
                            el cuerpo se ignora
    POST /estado            {"estado": "pensando"}   para curl y control.py
    POST /decir             {"texto": "Hola", "segundos": 5}
    GET  /salud             responde 204: sirve para preguntar "¿estás abierta?"

Los hooks de Claude Code son del tipo HTTP y le pegan directo a
/estado/<nombre>. Por eso el estado viaja en la ruta: así el plugin no
depende de encontrar un intérprete de Python en cada máquina, ni de que el
cuerpo del evento tenga una forma determinada.

El servidor corre en un hilo aparte. Como Qt no permite tocar la interfaz
desde otro hilo, el servidor NO llama a la mascota directamente: emite una
signal del "Puente", y Qt la entrega en el hilo principal de forma segura.

Siempre responde 2xx o 4xx con el cuerpo vacío, para que Claude Code lo lea
como "sin decisión" y nunca se frene por nuestra culpa.
"""
import json
import socket
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, Signal

from config import CFG, AVISOS

MAX_BYTES = 1024 * 1024    # el cuerpo de un evento puede ser grande; lo descartamos
MAX_TEXTO = 200            # largo máximo de un mensaje del globo


class Puente(QObject):
    """Lleva los pedidos del hilo del servidor al hilo de la interfaz."""
    pedido_estado = Signal(str)
    pedido_decir = Signal(str, int)


def crear_manejador(puente, estados_validos):
    """Arma la clase que atiende cada pedido HTTP."""

    class Manejador(BaseHTTPRequestHandler):

        protocol_version = "HTTP/1.1"   # los hooks reutilizan la conexión

        # ---------- Rutas ----------

        def do_GET(self):
            self.responder(204 if self.path == "/salud" else 404)

        def do_POST(self):
            # 1) La vía de los hooks: el estado viene en la ruta.
            if self.path.startswith("/estado/"):
                nombre = self.path[len("/estado/"):].strip("/")
                self.descartar_cuerpo()
                return self.aplicar(nombre)

            # Para el resto necesitamos leer el cuerpo.
            datos = self.leer_json()
            if datos is None:
                return self.responder(400)

            # 2) La vía de curl y control.py.
            if self.path == "/estado":
                return self.aplicar(datos.get("estado"))

            if self.path == "/decir":
                texto = str(datos.get("texto", "")).strip()[:MAX_TEXTO]
                try:
                    segundos = int(datos.get("segundos", CFG["segundos_globo"]))
                except (TypeError, ValueError):
                    return self.responder(400)
                if not texto:
                    return self.responder(400)
                puente.pedido_decir.emit(texto, segundos)
                return self.responder(204)

            self.responder(404)

        # ---------- Lógica ----------

        def aplicar(self, nombre):
            """Cambia el estado, o aplica un aviso (estado + mensaje)."""
            if nombre in estados_validos:
                puente.pedido_estado.emit(nombre)
                return self.responder(204)

            if nombre in AVISOS:
                estado, texto = AVISOS[nombre]
                puente.pedido_estado.emit(estado)
                puente.pedido_decir.emit(texto, CFG["segundos_globo"])
                return self.responder(204)

            self.responder(400)

        # ---------- Plomería ----------

        def largo_del_cuerpo(self):
            try:
                largo = int(self.headers.get("Content-Length", 0))
            except ValueError:
                return 0
            return largo if 0 < largo <= MAX_BYTES else 0

        def descartar_cuerpo(self):
            """Hay que leer el cuerpo aunque no lo usemos, o la conexión se traba."""
            largo = self.largo_del_cuerpo()
            if largo:
                self.rfile.read(largo)

        def leer_json(self):
            """Lee el cuerpo del pedido. Devuelve un dict, o None si algo no cierra."""
            largo = self.largo_del_cuerpo()
            if not largo:
                return None
            try:
                datos = json.loads(self.rfile.read(largo))
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                return None
            return datos if isinstance(datos, dict) else None

        def responder(self, codigo):
            self.send_response(codigo)
            self.send_header("Content-Length", "0")
            self.end_headers()
            print(f"[servidor] {self.command} {self.path} → {codigo}", flush=True)

        def log_message(self, formato, *args):
            pass  # silenciamos el log por defecto; usamos el nuestro en responder()

    return Manejador


class ServidorExclusivo(ThreadingHTTPServer):
    """
    Un servidor que no comparte el puerto con nadie.

    HTTPServer activa SO_REUSEADDR, y en Windows eso deja que otro proceso
    escuche en el mismo puerto: una segunda mascota arrancaría sin enterarse
    de la primera. SO_EXCLUSIVEADDRUSE hace que el segundo bind falle.
    En macOS y Linux SO_REUSEADDR no permite eso, así que lo dejamos.
    """
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def hay_otra_mascota():
    """True si en el puerto configurado ya responde una mascota."""
    try:
        urllib.request.urlopen(f"http://{CFG['host']}:{CFG['puerto']}/salud", timeout=1).close()
        return True
    except Exception:
        return False


def iniciar_servidor(puente, estados_validos):
    """Arranca el servidor en un hilo de fondo. Lanza OSError si el puerto está ocupado."""
    direccion = (CFG["host"], CFG["puerto"])
    servidor = ServidorExclusivo(direccion, crear_manejador(puente, estados_validos))
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    print(f"[servidor] escuchando en http://{direccion[0]}:{direccion[1]}", flush=True)
    return servidor
