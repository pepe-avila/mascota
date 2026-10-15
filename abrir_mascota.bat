@echo off
REM Abre la mascota con doble clic, sin pasar por Claude Code.
REM
REM Usa pythonw en vez de python para que no aparezca ninguna ventana negra:
REM es el mismo interprete, pero sin consola.
REM
REM %~dp0 es la carpeta donde esta este archivo, asi que el .bat funciona
REM aunque muevas el proyecto de lugar.

start "" pythonw "%~dp0plugins\mascota\scripts\arrancar.py"
