// Headless Chromium via CDP (Node 22): open <url>, wait for the page's app.js, evaluate the JS in <file>, print its JSON.
// Usage: node tests/cdp_eval.mjs <chrome-binary> <url> <file.js>
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [bin, url, file] = process.argv.slice(2);
const port = 9600 + Math.floor(Math.random() * 300);
const prof = mkdtempSync(join(tmpdir(), "trk-cdp-"));
const chrome = spawn(bin, ["--headless=new", "--no-sandbox", "--disable-gpu", `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, "--window-size=1200,1400", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const done = (code) => { try { chrome.kill("SIGKILL"); } catch {} try { rmSync(prof, { recursive: true, force: true }); } catch {} process.exit(code); };
setTimeout(() => { console.error("timeout"); done(2); }, 60000);
let target;
for (let i = 0; i < 80 && !target; i++) { await sleep(250); try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch {} }
if (!target) { console.error("no chrome"); done(2); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let n = 0; const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); } };
const call = (method, params = {}) => new Promise((r) => { const id = ++n; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
await call("Page.enable");
await call("Page.navigate", { url });
for (let i = 0; i < 60; i++) {
  await sleep(250);
  const r = await call("Runtime.evaluate", { returnByValue: true, expression: "typeof itemCard === 'function' && typeof modalBar === 'function'" });
  if (r?.result?.value === true) break;
}
const r = await call("Runtime.evaluate", { returnByValue: true, awaitPromise: true, expression: readFileSync(file, "utf8") });
if (r?.exceptionDetails) { console.error(JSON.stringify(r.exceptionDetails).slice(0, 1500)); done(1); }
console.log(JSON.stringify(r?.result?.value));
done(0);
