/** Minimal .env loader (no dependency). Reads broker/.env if present; process.env wins. */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export function loadEnv() {
  const here = dirname(fileURLToPath(import.meta.url));
  const file = join(here, "..", ".env");
  if (!existsSync(file)) return {};
  const out = {};
  for (const raw of readFileSync(file, "utf8").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const k = line.slice(0, eq).trim();
    let v = line.slice(eq + 1).trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
    if (!(k in process.env)) process.env[k] = v;
    out[k] = v;
  }
  return out;
}

export function need(name) {
  const v = process.env[name];
  if (!v) throw new Error(`missing env ${name} (see broker/.env.example)`);
  return v;
}
