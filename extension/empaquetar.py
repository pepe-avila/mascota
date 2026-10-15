#!/usr/bin/env python3
"""
Arma la extensión de Claude Desktop: dist/mascota.mcpb.

Un .mcpb es un zip con el manifest.json en la raíz y el código al lado.
Los scripts de Python no se duplican: se toman del plugin de Claude Code,
así las dos versiones usan siempre el mismo código.

Del plugin entran solo los scripts que la extensión ejecuta (ENTRADAS) y
los módulos que estos importan, que se descubren leyendo los imports. Lo
que usa únicamente Claude Code (la status line, control.py) queda afuera.

    python extension/empaquetar.py

Para instalarla, doble clic en el .mcpb, o en Claude Desktop:
Configuración → Extensiones → Instalar extensión.
"""
import ast
import json
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
PLUGIN = RAIZ / "plugins" / "mascota"
SCRIPTS = PLUGIN / "scripts"
SALIDA = RAIZ / "dist" / "mascota.mcpb"

# Lo que la extensión ejecuta: server/index.js lanza arrancar.py, y
# arrancar.py lanza mascota.py como proceso aparte (no lo importa).
ENTRADAS = ("arrancar.py", "mascota.py")

# Archivos propios de la extensión, relativos a esta carpeta.
PROPIOS = ("manifest.json", "icon.png", "server")


def modulos_locales(script):
    """Nombres de los módulos de la carpeta de scripts que importa un archivo."""
    arbol = ast.parse(script.read_text(encoding="utf-8"))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
            nombres.add(nodo.module.split(".")[0])
    return {n for n in nombres if (SCRIPTS / f"{n}.py").exists()}


def scripts_necesarios():
    """Las entradas más todo lo que importan, directa o indirectamente."""
    pendientes = [SCRIPTS / nombre for nombre in ENTRADAS]
    vistos = set()
    while pendientes:
        script = pendientes.pop()
        if script in vistos:
            continue
        vistos.add(script)
        pendientes.extend(SCRIPTS / f"{m}.py" for m in modulos_locales(script))
    return sorted(vistos)


def archivos(carpeta):
    """Todos los archivos de una carpeta, sin cachés de Python."""
    for ruta in sorted(carpeta.rglob("*")):
        if ruta.is_file() and "__pycache__" not in ruta.parts:
            yield ruta


def main():
    manifiesto = json.loads((AQUI / "manifest.json").read_text(encoding="utf-8"))
    plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if manifiesto["version"] != plugin["version"]:
        print(f"Las versiones no coinciden: extensión {manifiesto['version']}, "
              f"plugin {plugin['version']}. Igualalas antes de publicar.")
        return 1

    contenido = {}
    for nombre in PROPIOS:
        ruta = AQUI / nombre
        for archivo in (archivos(ruta) if ruta.is_dir() else [ruta]):
            contenido[archivo.relative_to(AQUI).as_posix()] = archivo
    for script in scripts_necesarios():
        contenido[script.relative_to(PLUGIN).as_posix()] = script
    for archivo in archivos(PLUGIN / "sprites"):
        contenido[archivo.relative_to(PLUGIN).as_posix()] = archivo
    contenido["LICENSE"] = RAIZ / "LICENSE"

    SALIDA.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(SALIDA, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zip_:
        for destino, origen in sorted(contenido.items()):
            zip_.write(origen, destino)

    scripts = [p for p in contenido if p.startswith("scripts/")]
    print(f"Listo: {SALIDA} ({SALIDA.stat().st_size // 1024} KB, {len(contenido)} archivos)")
    print("Scripts incluidos:", ", ".join(Path(p).name for p in scripts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
