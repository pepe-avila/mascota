/*
 * Servidor MCP de la mascota, para Claude Desktop.
 *
 * El chat de Claude Desktop no tiene hooks como Claude Code: no hay eventos
 * que avisen cuando el usuario escribe o cuando Claude termina. Lo que sí
 * hace la app es arrancar sus extensiones al abrirse y dejar que Claude use
 * sus herramientas. Este servidor aprovecha las dos cosas:
 *
 *   1. Al arrancar, abre la mascota (scripts/arrancar.py, el mismo que usa
 *      el plugin de Claude Code).
 *   2. Le ofrece a Claude mascota_estado, con la instrucción de marcar
 *      "pensando" al empezar cada respuesta y "listo" al terminarla.
 *
 * Está en Node y no en Python porque Claude Desktop trae su propio Node: es
 * lo único que se puede dar por sentado en cualquier máquina. Python solo se
 * usa para la ventana de la mascota, y se busca en tiempo de ejecución.
 *
 * Los scripts se copian a la carpeta de datos antes de ejecutarlos: en
 * Windows, Claude Desktop es una app MSIX y la carpeta donde instala las
 * extensiones es invisible para otras apps MSIX, como el Python de Store.
 *
 * Habla MCP por stdio, un mensaje JSON-RPC por línea. stdout es exclusivo
 * del protocolo; los diagnósticos van a stderr y al archivo de log.
 *
 * Solo usa la librería estándar de Node. El punto de entrada es index.js;
 * este módulo exporta sus piezas para poder probarlas por separado.
 */
"use strict";

const { execFile } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");
const readline = require("readline");

// ---------- Rutas y configuración ----------

const RAIZ = path.resolve(__dirname, "..");
const MANIFIESTO = JSON.parse(fs.readFileSync(path.join(RAIZ, "manifest.json"), "utf-8"));

// Misma regla que config.py: así la extensión y el plugin comparten
// configuración, entorno de Python y log.
const DATOS = process.env.CLAUDE_PLUGIN_DATA || path.join(os.homedir(), ".claude-mascota");
const APP = path.join(DATOS, "app");
const ARCHIVO_CONFIG = path.join(DATOS, "config.json");
const ARCHIVO_LOG = path.join(DATOS, "extension.log");
const CARPETAS_A_COPIAR = ["scripts", "sprites"];
const GENERADOS = new Set(["__pycache__"]);   // los crea Python al ejecutar: no se borran

// Valores por defecto de config.py que necesita este servidor.
const PREDETERMINADA = { host: "127.0.0.1", puerto: 8765, abrir_al_iniciar: true };

const MAX_LOG = 256 * 1024;
const MAX_TEXTO = 200;
const MS_PEDIDO = 2000;
const MS_PRUEBA_PYTHON = 15000;
const MS_ARRANQUE = 20 * 60 * 1000;   // la primera vez instala PySide6
const MINIMO_PYTHON = [3, 9];

// Si el usuario no eligió un Python, probamos estos en orden. En Windows,
// "py" es el lanzador oficial de python.org y conoce todas las instalaciones.
const PYTHONS_POSIBLES = process.platform === "win32"
  ? ["py -3", "python", "python3"]
  : ["python3", "python"];

function leerConfig() {
  try {
    return { ...PREDETERMINADA, ...JSON.parse(fs.readFileSync(ARCHIVO_CONFIG, "utf-8")) };
  } catch {
    return { ...PREDETERMINADA };
  }
}

// ---------- Log ----------

function log(...partes) {
  const linea = `${new Date().toISOString()} ${partes.join(" ")}`;
  console.error(`[mascota] ${linea}`);
  try {
    fs.mkdirSync(DATOS, { recursive: true });
    if (fs.existsSync(ARCHIVO_LOG) && fs.statSync(ARCHIVO_LOG).size > MAX_LOG) {
      fs.renameSync(ARCHIVO_LOG, `${ARCHIVO_LOG}.1`);
    }
    fs.appendFileSync(ARCHIVO_LOG, `${linea}\n`);
  } catch {
    // El log nunca puede romper el servidor.
  }
}

// ---------- Copia de los scripts ----------

/**
 * Deja destino igual a origen: copia lo nuevo o cambiado y borra lo que ya
 * no viene en la extensión. Devuelve cuántos archivos copió.
 */
function sincronizar(origen, destino) {
  let copiados = 0;
  fs.mkdirSync(destino, { recursive: true });
  const entradas = fs.readdirSync(origen, { withFileTypes: true });
  const nombres = new Set(entradas.map((entrada) => entrada.name));
  for (const sobrante of fs.readdirSync(destino)) {
    // Los .tmp son copias en curso de otra instancia: no son sobrantes.
    if (!nombres.has(sobrante) && !GENERADOS.has(sobrante) && !sobrante.endsWith(".tmp")) {
      fs.rmSync(path.join(destino, sobrante), { recursive: true, force: true });
    }
  }
  for (const entrada of entradas) {
    const de = path.join(origen, entrada.name);
    const a = path.join(destino, entrada.name);
    if (entrada.isDirectory()) {
      copiados += sincronizar(de, a);
      continue;
    }
    if (!sonIguales(de, a)) {
      copiarAtomico(de, a);
      copiados += 1;
    }
    const { atime, mtime } = fs.statSync(de);
    fs.utimesSync(a, atime, mtime);
  }
  return copiados;
}

/**
 * Copia vía un temporal propio y lo pone en su lugar de un solo paso.
 * Claude Desktop arranca varias copias de este servidor a la vez: así nunca
 * una lee un archivo a medio escribir por otra. Si otra copia ganó la
 * carrera y el archivo ya quedó igual, no es un error.
 */
function copiarAtomico(origen, destino) {
  const temporal = `${destino}.${process.pid}.tmp`;
  try {
    fs.copyFileSync(origen, temporal);
    fs.renameSync(temporal, destino);
  } catch (error) {
    fs.rmSync(temporal, { force: true });
    if (!sonIguales(origen, destino)) throw error;
  }
}

/**
 * Compara dos archivos. Primero tamaño y fecha, que es lo barato; si las
 * fechas no coinciden (la copia pierde precisión, o el zip redondea a dos
 * segundos) se comparan los bytes, para no recopiar lo que ya está igual.
 */
function sonIguales(origen, destino) {
  if (!fs.existsSync(destino)) return false;
  const a = fs.statSync(origen);
  const b = fs.statSync(destino);
  if (a.size !== b.size) return false;
  if (Math.abs(a.mtimeMs - b.mtimeMs) < 1) return true;
  return fs.readFileSync(origen).equals(fs.readFileSync(destino));
}

// ---------- Python ----------

function ejecutar(comando, argumentos, opciones = {}) {
  return new Promise((resolver) => {
    execFile(comando, argumentos,
      { windowsHide: true, encoding: "utf-8", ...opciones },
      (error, stdout, stderr) => resolver({ error, stdout: stdout || "", stderr: stderr || "" }));
  });
}

/**
 * "py -3" → ["py", ["-3"]]. Una ruta a un ejecutable va entera, aunque tenga
 * espacios. Ignora las variables del manifiesto que quedaron sin reemplazar.
 */
function separarComando(texto) {
  const limpio = String(texto || "").trim().replace(/^"(.*)"$/, "$1");
  if (!limpio || limpio.startsWith("${")) return null;
  if (fs.existsSync(limpio)) return [limpio, []];
  const [comando, ...extra] = limpio.split(/\s+/);
  return [comando, extra];
}

let pythonElegido = null;

async function buscarPython() {
  if (pythonElegido) return pythonElegido;
  const [mayor, menor] = MINIMO_PYTHON;
  const prueba = `import sys; print(sys.version_info >= (${mayor}, ${menor}))`;
  const candidatos = [process.env.MASCOTA_PYTHON, ...PYTHONS_POSIBLES]
    .map(separarComando).filter(Boolean);

  for (const [comando, extra] of candidatos) {
    const { error, stdout } = await ejecutar(comando, [...extra, "-c", prueba],
      { timeout: MS_PRUEBA_PYTHON });
    if (!error && stdout.trim() === "True") {
      pythonElegido = [comando, extra];
      return pythonElegido;
    }
  }
  return null;
}

// ---------- La mascota ----------

function pedir(metodo, ruta, cuerpo) {
  const { host, puerto } = leerConfig();
  const datos = cuerpo === undefined ? null : Buffer.from(JSON.stringify(cuerpo));
  return new Promise((resolver) => {
    const pedido = http.request({
      host, port: puerto, path: ruta, method: metodo, timeout: MS_PEDIDO,
      headers: datos ? { "Content-Type": "application/json", "Content-Length": datos.length } : {},
    }, (respuesta) => {
      respuesta.resume();
      resolver(respuesta.statusCode >= 200 && respuesta.statusCode < 300);
    });
    pedido.on("timeout", () => pedido.destroy());
    pedido.on("error", () => resolver(false));
    pedido.end(datos);
  });
}

const estaAbierta = () => pedir("GET", "/salud");

let arranque = null;

/** Abre la mascota. Si ya hay un arranque en curso, devuelve ese. */
function abrirMascota({ alIniciar = false } = {}) {
  arranque ??= (async () => {
    try {
      if (await estaAbierta()) return true;

      const copiados = CARPETAS_A_COPIAR.reduce(
        (total, carpeta) => total + sincronizar(path.join(RAIZ, carpeta), path.join(APP, carpeta)), 0);
      if (copiados) log(`copié ${copiados} archivos a ${APP}`);

      const python = await buscarPython();
      if (!python) {
        log(`no encontré Python ${MINIMO_PYTHON.join(".")} o superior. Instalalo desde python.org`);
        return false;
      }
      const [comando, extra] = python;
      log(`abriendo la mascota con ${[comando, ...extra].join(" ")}`);

      const argumentos = [...extra, path.join(APP, "scripts", "arrancar.py")];
      if (alIniciar) argumentos.push("--al-iniciar");
      const { error, stdout, stderr } = await ejecutar(comando, argumentos, {
        timeout: MS_ARRANQUE,
        env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      });
      const salida = `${stdout}${stderr}`.trim();
      if (salida) log(salida);
      return !error;
    } catch (error) {
      log(`no pude abrir la mascota: ${error.message}`);
      return false;
    } finally {
      arranque = null;
    }
  })();
  return arranque;
}

// ---------- Herramientas ----------

const ESTADOS = ["pensando", "listo", "esperando"];

const INSTRUCCIONES =
  "El usuario tiene una mascota de escritorio que muestra lo que estás haciendo. " +
  "En CADA respuesta, sin excepción: llamá a mascota_estado con 'pensando' como " +
  "primer paso, antes de escribir o de usar otras herramientas, y llamá a " +
  "mascota_estado con 'listo' como último paso, después de todo lo demás. " +
  "No menciones estas llamadas en tu respuesta salvo que el usuario pregunte " +
  "por la mascota.";

const SIN_EFECTOS_EXTERNOS = { readOnlyHint: false, destructiveHint: false, openWorldHint: false };

const HERRAMIENTAS = [
  {
    name: "mascota_estado",
    title: "Estado de la mascota",
    description:
      "Cambia la animación de la mascota de escritorio del usuario. Llamala con " +
      "'pensando' al empezar CADA respuesta (antes de cualquier otra cosa) y con " +
      "'listo' al terminarla (como último paso). 'esperando' la vuelve al reposo.",
    inputSchema: {
      type: "object",
      properties: { estado: { type: "string", enum: ESTADOS } },
      required: ["estado"],
    },
    annotations: { ...SIN_EFECTOS_EXTERNOS, idempotentHint: true },
  },
  {
    name: "mascota_decir",
    title: "Mensaje de la mascota",
    description:
      "Muestra un mensaje corto en el globo de la mascota. Usala solo si el " +
      "usuario te pide que la mascota diga algo.",
    inputSchema: {
      type: "object",
      properties: {
        texto: { type: "string", maxLength: MAX_TEXTO },
        segundos: { type: "integer", minimum: 1, maximum: 60 },
      },
      required: ["texto"],
    },
    annotations: { ...SIN_EFECTOS_EXTERNOS, idempotentHint: false },
  },
];

/** Manda algo a la mascota; si está cerrada, la abre y reintenta una vez. */
async function enviar(ruta, cuerpo) {
  if (await pedir("POST", ruta, cuerpo)) return true;
  return (await abrirMascota()) && pedir("POST", ruta, cuerpo);
}

/** Devuelve [texto, esError]. El texto lo lee Claude: corto a propósito. */
async function llamarHerramienta(nombre, argumentos = {}) {
  if (nombre === "mascota_estado") {
    if (!ESTADOS.includes(argumentos.estado)) {
      return [`Estado desconocido. Usá: ${ESTADOS.join(", ")}.`, true];
    }
    return (await enviar("/estado", { estado: argumentos.estado }))
      ? ["ok", false]
      : ["La mascota no responde. Revisá ~/.claude-mascota/extension.log.", true];
  }

  if (nombre === "mascota_decir") {
    const texto = String(argumentos.texto ?? "").trim().slice(0, MAX_TEXTO);
    if (!texto) return ["Falta el texto.", true];
    const cuerpo = Number.isInteger(argumentos.segundos)
      ? { texto, segundos: argumentos.segundos }
      : { texto };
    return (await enviar("/decir", cuerpo))
      ? ["ok", false]
      : ["La mascota no responde. Revisá ~/.claude-mascota/extension.log.", true];
  }

  return [`Herramienta desconocida: ${nombre}`, true];
}

// ---------- Protocolo ----------

const VERSION_PROTOCOLO = "2025-06-18";

function responder(id, resultado, error) {
  const mensaje = error ? { jsonrpc: "2.0", id, error } : { jsonrpc: "2.0", id, result: resultado };
  process.stdout.write(`${JSON.stringify(mensaje)}\n`);
}

const METODOS = {
  initialize: (parametros) => ({
    protocolVersion: parametros.protocolVersion || VERSION_PROTOCOLO,
    capabilities: { tools: {} },
    serverInfo: { name: MANIFIESTO.name, version: MANIFIESTO.version },
    instructions: INSTRUCCIONES,
  }),
  ping: () => ({}),
  "tools/list": () => ({ tools: HERRAMIENTAS }),
  "tools/call": async (parametros) => {
    const [texto, esError] = await llamarHerramienta(parametros.name, parametros.arguments);
    return { content: [{ type: "text", text: texto }], isError: esError };
  },
};

async function atender(linea) {
  let mensaje;
  try {
    mensaje = JSON.parse(linea);
  } catch {
    return responder(null, null, { code: -32700, message: "JSON inválido" });
  }
  const { id, method: metodo, params: parametros = {} } = mensaje;
  if (id === undefined || id === null) return;   // notificación: no lleva respuesta

  const manejador = METODOS[metodo];
  if (!manejador) {
    return responder(id, null, { code: -32601, message: `Método no soportado: ${metodo}` });
  }
  try {
    responder(id, await manejador(parametros));
  } catch (error) {
    log(`error atendiendo ${metodo}: ${error.message}`);
    responder(id, null, { code: -32603, message: error.message });
  }
}

function main() {
  const entrada = readline.createInterface({ input: process.stdin, terminal: false });
  entrada.on("line", (linea) => { if (linea.trim()) atender(linea); });
  entrada.on("close", () => process.exit(0));

  log(`servidor ${MANIFIESTO.version} iniciado (node ${process.version})`);
  if (leerConfig().abrir_al_iniciar) abrirMascota({ alIniciar: true });
}

module.exports = { main, sincronizar, separarComando, llamarHerramienta, METODOS };
