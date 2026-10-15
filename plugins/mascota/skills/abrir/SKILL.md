---
name: abrir
description: Abre la mascota de escritorio. Normalmente se abre sola al empezar una sesión de Claude Code; este comando es para abrirla a mano si la cerraste, o si la apertura automática está desactivada.
disable-model-invocation: true
allowed-tools:
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/arrancar.py"*)
  - Bash(python "${CLAUDE_PLUGIN_ROOT}/scripts/arrancar.py"*)
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py"*)
  - Bash(python "${CLAUDE_PLUGIN_ROOT}/scripts/control.py"*)
---

# Mascota

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/arrancar.py" || python "${CLAUDE_PLUGIN_ROOT}/scripts/arrancar.py"`

La salida de arriba dice qué pasó al abrir la mascota. Interpretala así:

- **Si dice que la mascota quedó andando**, contale al usuario en una línea que ya
  está activa. No repitas la lista de estados.
- **Si dice que tuvo que preparar el entorno**, mencionalo: la primera vez instala
  PySide6 y tarda un minuto, pero las próximas veces arranca al instante.
- **Si falló porque no encontró Python**, decíselo y pedile que instale Python 3.9
  o superior desde python.org. No intentes instalarlo vos.
- **Si falló por otra razón**, mostrale el error y ofrecé ayuda para resolverlo.

Los hooks que hacen reaccionar a la mascota vienen con el plugin y están siempre
activos, así que funcionan aunque esta respuesta falle.

## Si el usuario pide algo más

Para que diga algo, cambie de estado o informe el uso restante:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" decir "el mensaje" 6
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" estado pensando
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" uso
```

Si `python3` no existe en esa máquina, usá `python`.

Los estados son: `esperando`, `pensando`, `permiso`, `listo` y `cansado`.

## Si pregunta por la apertura automática

La mascota se abre sola al empezar cada sesión de Claude Code. Para desactivarlo,
hay que poner `"abrir_al_iniciar": false` en el `config.json`, cuya ruta imprime:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" config
```

## Sobre el uso restante

El dato de cuánto uso queda lo provee la *status line* de Claude Code, y un plugin
no puede configurarla solo. Si el usuario quiere esa función y
`control.py uso` responde que no hay datos, explicale que tiene que agregar esto a
su `~/.claude/settings.json`, con la ruta que imprime
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/control.py" barra`:

```json
"statusLine": { "type": "command", "command": "<lo que imprimió ese comando>" }
```

Solo funciona en planes Pro y Max: en una cuenta de API por consumo, Claude Code
no expone los porcentajes de uso.
