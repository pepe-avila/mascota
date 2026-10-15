// Pruebas del servidor de la extensión. Correr desde la raíz del repo con: node --test
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

const { sincronizar, separarComando, llamarHerramienta, METODOS } = require("../server/servidor");

function carpetaTemporal(t) {
  const carpeta = fs.mkdtempSync(path.join(os.tmpdir(), "mascota-"));
  t.after(() => fs.rmSync(carpeta, { recursive: true, force: true }));
  return carpeta;
}

test("separarComando separa argumentos e ignora lo vacío", () => {
  assert.deepEqual(separarComando("py -3"), ["py", ["-3"]]);
  assert.deepEqual(separarComando("python3"), ["python3", []]);
  assert.equal(separarComando(""), null);
  assert.equal(separarComando(undefined), null);
  assert.equal(separarComando("${user_config.python}"), null);
});

test("separarComando no parte una ruta existente con espacios", (t) => {
  const carpeta = path.join(carpetaTemporal(t), "con espacios");
  fs.mkdirSync(carpeta);
  const ejecutable = path.join(carpeta, "python.exe");
  fs.writeFileSync(ejecutable, "");
  assert.deepEqual(separarComando(ejecutable), [ejecutable, []]);
  assert.deepEqual(separarComando(`"${ejecutable}"`), [ejecutable, []]);
});

test("sincronizar copia solo lo que cambió y limpia lo que sobra", (t) => {
  const raiz = carpetaTemporal(t);
  const origen = path.join(raiz, "origen");
  const destino = path.join(raiz, "destino");
  fs.mkdirSync(path.join(origen, "sub"), { recursive: true });
  fs.writeFileSync(path.join(origen, "a.py"), "a");
  fs.writeFileSync(path.join(origen, "sub", "b.png"), "b");

  assert.equal(sincronizar(origen, destino), 2);
  assert.equal(sincronizar(origen, destino), 0, "la segunda vez no copia nada");

  fs.writeFileSync(path.join(origen, "a.py"), "a cambiado");
  fs.writeFileSync(path.join(destino, "viejo.py"), "sobrante");
  fs.mkdirSync(path.join(destino, "__pycache__"));
  assert.equal(sincronizar(origen, destino), 1);
  assert.equal(fs.readFileSync(path.join(destino, "a.py"), "utf-8"), "a cambiado");
  assert.ok(!fs.existsSync(path.join(destino, "viejo.py")), "borra lo que ya no viene");
  assert.ok(fs.existsSync(path.join(destino, "__pycache__")), "respeta lo que genera Python");
});

test("initialize anuncia herramientas e instrucciones", () => {
  const respuesta = METODOS.initialize({ protocolVersion: "2025-06-18" });
  assert.equal(respuesta.protocolVersion, "2025-06-18");
  assert.deepEqual(respuesta.capabilities, { tools: {} });
  assert.match(respuesta.instructions, /mascota_estado/);
});

test("tools/list expone las dos herramientas", () => {
  const nombres = METODOS["tools/list"]().tools.map((h) => h.name);
  assert.deepEqual(nombres, ["mascota_estado", "mascota_decir"]);
});

test("las herramientas validan sus argumentos sin tocar la mascota", async () => {
  assert.equal((await llamarHerramienta("mascota_estado", { estado: "volando" }))[1], true);
  assert.equal((await llamarHerramienta("mascota_decir", { texto: "  " }))[1], true);
  assert.equal((await llamarHerramienta("inexistente", {}))[1], true);
});
