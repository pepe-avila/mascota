"""
Mascota de escritorio para Claude Code.

Una ventana sin bordes, transparente y siempre visible, con un personaje
que reacciona a lo que hace Claude Code y avisa cuánto uso te queda.

    python mascota.py

Atajos: clic izquierdo para arrastrar, clic derecho para el menú,
teclas 1..5 para forzar un estado (útil para probar).
"""
import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QMenu, QSystemTrayIcon,
)
from PySide6.QtGui import QPixmap, QPainter, QFont, QIcon
from PySide6.QtCore import Qt, QTimer

import arte
import uso
from config import (
    CFG, CARPETA_SPRITES, ESTADOS, FRAMES_EMOJI, MENSAJES, ESTILO_GLOBO,
    ARCHIVO_CONFIG,
)
from servidor import Puente, hay_otra_mascota, iniciar_servidor

# Teclas 1..5 → estados, en el orden de config.ESTADOS
TECLAS = {
    getattr(Qt.Key, f"Key_{i + 1}"): estado
    for i, estado in enumerate(ESTADOS[:9])
}


def escalar(ruta):
    """Carga un PNG al tamaño de la mascota. Devuelve None si no se pudo."""
    pixmap = QPixmap(str(ruta))
    if pixmap.isNull():
        return None
    return pixmap.scaled(
        CFG["tamanio"], CFG["tamanio"],
        Qt.AspectRatioMode.KeepAspectRatio,
        # Nearest, no Smooth: el pixel art tiene que quedar nítido, no borroso
        Qt.TransformationMode.FastTransformation,
    )


def cargar_frames(piel, estado):
    """Frames de un estado con los dibujos de esa piel, o el emoji de reserva."""
    frames = [p for p in (escalar(a) for a in arte.rutas(piel, estado)) if p]
    return frames or FRAMES_EMOJI[estado]


def icono_bandeja(piel=""):
    """Ícono para la bandeja: icono.png, el primer dibujo de la piel, o una huella."""
    archivo = CARPETA_SPRITES / "icono.png"
    if archivo.exists():
        pixmap = QPixmap(str(archivo))
        if not pixmap.isNull():
            return QIcon(pixmap)

    dibujos = arte.rutas(piel, "esperando")
    if dibujos:
        pixmap = QPixmap(str(dibujos[0]))
        if not pixmap.isNull():
            return QIcon(pixmap)

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pixmap)
    fuente = QFont()
    fuente.setPointSize(40)
    pintor.setFont(fuente)
    pintor.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🐾")
    pintor.end()
    return QIcon(pixmap)


class Mascota(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Mascota de Claude")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint      # sin bordes ni barra de título
            | Qt.WindowType.WindowStaysOnTopHint   # siempre por encima
            | Qt.WindowType.Tool                   # no aparece en la barra de tareas
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # --- El globo ---
        self.globo = QLabel()
        self.globo.setWordWrap(True)
        self.globo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Ancho fijo: así el alto que calcula heightForWidth() es el real,
        # y el texto largo no se corta al envolver en varias líneas.
        self.ancho_globo = CFG["ancho_ventana"] - 16
        self.globo.setFixedWidth(self.ancho_globo)
        self.globo.setStyleSheet(ESTILO_GLOBO)
        self.globo.hide()

        # Un solo timer para el globo: al reiniciarlo se cancela la cuenta anterior
        self.timer_globo = QTimer(self)
        self.timer_globo.setSingleShot(True)
        self.timer_globo.timeout.connect(self.globo.hide)

        # --- El personaje ---
        self.sprite = QLabel()
        self.sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite.setFixedHeight(CFG["tamanio"])
        fuente = self.sprite.font()
        fuente.setPointSize(72)   # tamaño de los emojis de reserva
        self.sprite.setFont(fuente)

        # Espacio elástico arriba: cuando el globo se oculta, el personaje no salta
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addStretch()
        layout.addWidget(self.globo, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.sprite)

        self.setFixedSize(CFG["ancho_ventana"], CFG["tamanio"] + CFG["alto_globo"])
        self.ubicar_abajo_a_la_derecha()

        # --- Dibujos, estados y animación ---
        self.piel = arte.elegir(CFG["piel"])
        self.frames = {}
        self.cargar_dibujos()

        self.estado = "esperando"
        self.indice = 0

        self.timer_animacion = QTimer(self)
        self.timer_animacion.timeout.connect(self.siguiente_frame)
        self.timer_animacion.start(CFG["ms_por_frame"])

        # --- Aviso periódico del uso restante ---
        self.timer_uso = QTimer(self)
        self.timer_uso.timeout.connect(self.avisar_uso)
        minutos = CFG["minutos_aviso_uso"]
        if minutos > 0:
            self.timer_uso.start(minutos * 60 * 1000)

        self.mostrar_frame()

    # ---------- Dibujos ----------

    def cargar_dibujos(self):
        self.frames = {e: cargar_frames(self.piel, e) for e in ESTADOS}

    def cambiar_piel(self, piel):
        """Cambia el conjunto de dibujos en caliente y recuerda la elección."""
        self.piel = piel
        self.cargar_dibujos()
        self.indice = 0
        self.mostrar_frame()
        self.decir(f"Ahora soy {arte.nombre_corto(piel)}", 3)
        self.recordar_piel(piel)

    @staticmethod
    def recordar_piel(piel):
        """Guarda la piel elegida en config.json, para la próxima vez."""
        try:
            datos = {}
            if ARCHIVO_CONFIG.exists():
                datos = json.loads(ARCHIVO_CONFIG.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                datos = {}
            datos["piel"] = piel
            ARCHIVO_CONFIG.write_text(
                json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except (OSError, json.JSONDecodeError):
            pass  # si no se puede guardar, igual el cambio vale para esta sesión

    # ---------- Globo ----------

    def decir(self, texto, segundos=None):
        """Muestra un mensaje. Con segundos=None queda hasta que algo lo oculte."""
        self.globo.setText(texto)
        # Ajustamos el alto a las líneas que realmente ocupa el texto
        self.globo.setFixedHeight(self.globo.heightForWidth(self.ancho_globo))
        self.globo.show()
        if segundos:
            self.timer_globo.start(int(segundos) * 1000)
        else:
            self.timer_globo.stop()

    def callar(self):
        self.timer_globo.stop()
        self.globo.hide()

    # ---------- Estados ----------

    def cambiar_estado(self, nuevo):
        if nuevo not in self.frames:
            return
        self.estado = nuevo
        self.indice = 0
        self.mostrar_frame()

        mensaje = MENSAJES.get(nuevo)
        if mensaje:
            texto, segundos = mensaje
            self.decir(texto, segundos)
        else:
            self.callar()

        if nuevo == "listo":
            QTimer.singleShot(
                CFG["segundos_festejo"] * 1000, self.volver_a_esperar
            )

    def volver_a_esperar(self):
        # Solo si sigue festejando: si mientras tanto pasó a "pensando",
        # no queremos pisar ese estado.
        if self.estado == "listo":
            self.cambiar_estado("esperando")

    # ---------- Uso restante ----------

    def avisar_uso(self):
        """Muestra el uso restante. Si no hay datos, lo dice sin alarmar."""
        frase = uso.resumen()
        if frase:
            self.decir(frase, CFG["segundos_globo"])
        else:
            self.decir("Todavía no sé cuánto uso te queda", CFG["segundos_globo"])

    # ---------- Animación ----------

    def siguiente_frame(self):
        frames = self.frames[self.estado]
        self.indice = (self.indice + 1) % len(frames)
        self.mostrar_frame()

    def mostrar_frame(self):
        frame = self.frames[self.estado][self.indice]
        if isinstance(frame, QPixmap):
            self.sprite.setPixmap(frame)
        else:
            self.sprite.setText(frame)

    # ---------- Posición y mouse ----------

    def ubicar_abajo_a_la_derecha(self):
        pantalla = QApplication.primaryScreen().availableGeometry()
        margen = CFG["margen_pantalla"]
        self.move(
            pantalla.right() - self.width() - margen,
            pantalla.bottom() - self.height() - margen,
        )

    def mousePressEvent(self, evento):
        if evento.button() == Qt.MouseButton.LeftButton:
            self.windowHandle().startSystemMove()

    def contextMenuEvent(self, evento):
        self.menu().exec(evento.globalPos())

    def menu(self):
        """El mismo menú sirve para el clic derecho y para la bandeja."""
        menu = QMenu(self)

        accion_uso = menu.addAction("¿Cuánto uso me queda?")
        accion_uso.triggered.connect(self.avisar_uso)

        pieles = arte.pieles()
        if len(pieles) > 1:
            elegir_piel = menu.addMenu("Mascota")
            for piel in pieles:
                accion = elegir_piel.addAction(arte.nombre_corto(piel))
                accion.setCheckable(True)
                accion.setChecked(piel == self.piel)
                accion.triggered.connect(
                    lambda _marcado=False, p=piel: self.cambiar_piel(p)
                )

        submenu = menu.addMenu("Estado")
        for estado in ESTADOS:
            accion = submenu.addAction(estado)
            accion.triggered.connect(
                lambda _marcado=False, e=estado: self.cambiar_estado(e)
            )

        menu.addSeparator()
        menu.addAction("Salir").triggered.connect(QApplication.quit)
        return menu

    # ---------- Teclado ----------

    def keyPressEvent(self, evento):
        estado = TECLAS.get(evento.key())
        if estado:
            self.cambiar_estado(estado)


def main():
    app = QApplication(sys.argv)
    # Que cerrar el menú no cierre la aplicación cuando la ventana esté oculta
    app.setQuitOnLastWindowClosed(False)

    # --- Servidor local: por acá entran los avisos de Claude ---
    # Va antes que la ventana: el puerto es lo que garantiza una sola mascota.
    # Si ya lo tiene otra, nos vamos sin mostrar nada.
    puente = Puente()
    try:
        iniciar_servidor(puente, set(ESTADOS))
        puerto_ocupado = False
    except OSError:
        if hay_otra_mascota():
            return 0
        puerto_ocupado = True   # lo tiene otro programa: avisamos

    mascota = Mascota()
    puente.pedido_estado.connect(mascota.cambiar_estado)
    puente.pedido_decir.connect(mascota.decir)
    mascota.show()

    # --- Ícono en la bandeja del sistema ---
    bandeja = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        bandeja = QSystemTrayIcon(icono_bandeja(mascota.piel), app)
        bandeja.setToolTip("Mascota de Claude")
        bandeja.setContextMenu(mascota.menu())
        bandeja.show()

    if puerto_ocupado:
        mascota.decir(f"El puerto {CFG['puerto']} está ocupado 😿", 10)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
