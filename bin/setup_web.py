#!/usr/bin/env python3
"""ClaudeInbox — web app di setup (locale, zero dipendenze).

Avvia un wizard nel browser per configurare le credenziali email e scriverle in
~/.claude/claude-mail.env (chmod 600). Riusa le funzioni di claude_mail.py per
testare SMTP/IMAP e inviare una mail di prova.

Uso:
  python3 bin/setup_web.py               # apri http://127.0.0.1:8765
  python3 bin/setup_web.py --port 9000
  python3 bin/setup_web.py --no-browser

Gira solo su 127.0.0.1 (loopback): non è esposto in rete.
"""
from __future__ import annotations

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_mail as cm  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8765

PAGE = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClaudeInbox · Setup</title>
<style>
  :root { color-scheme: light dark; --bg:#0f1220; --card:#191d31; --fg:#e8eaf2;
    --mut:#9aa0b4; --line:#2b3050; --acc:#7c8cff; --ok:#3ecf8e; --err:#ff6b6b; }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    background:var(--bg); color:var(--fg); }
  .wrap { max-width:720px; margin:0 auto; padding:32px 20px 64px; }
  h1 { font-size:22px; margin:0 0 4px; }
  h2 { font-size:14px; text-transform:uppercase; letter-spacing:.06em;
    color:var(--mut); margin:28px 0 12px; }
  p.sub { color:var(--mut); margin:0 0 8px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px;
    padding:20px; }
  label { display:block; font-size:13px; color:var(--mut); margin:12px 0 4px; }
  input, select { width:100%; padding:10px 12px; border-radius:9px;
    border:1px solid var(--line); background:#12162a; color:var(--fg); font-size:14px; }
  input:focus, select:focus { outline:2px solid var(--acc); border-color:var(--acc); }
  .row { display:flex; gap:12px; } .row > * { flex:1; }
  .actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }
  button { padding:10px 16px; border-radius:9px; border:1px solid var(--line);
    background:#232845; color:var(--fg); font-size:14px; cursor:pointer; }
  button:hover { border-color:var(--acc); }
  button.primary { background:var(--acc); border-color:var(--acc); color:#0b0e1a;
    font-weight:600; }
  button:disabled { opacity:.5; cursor:progress; }
  .status { margin-top:16px; padding:12px 14px; border-radius:9px; font-size:14px;
    white-space:pre-wrap; display:none; }
  .status.ok { display:block; background:rgba(62,207,142,.12); color:var(--ok);
    border:1px solid rgba(62,207,142,.4); }
  .status.err { display:block; background:rgba(255,107,107,.12); color:var(--err);
    border:1px solid rgba(255,107,107,.4); }
  .hint { font-size:12px; color:var(--mut); margin-top:4px; }
  a { color:var(--acc); }
</style>
</head>
<body>
<div class="wrap">
  <h1>ClaudeInbox · Setup</h1>
  <p class="sub">Configura l'email di Claude Code. I dati vengono salvati solo in
    locale in <code>~/.claude/claude-mail.env</code> (chmod 600).</p>

  <div class="card">
    <h2>Indirizzi</h2>
    <label>Mittente (from) — la casella da cui Claude invia</label>
    <input id="MAIL_SENDER" placeholder="claude@tuo-dominio.com">
    <label>Destinatario (to) — dove ricevi le notifiche</label>
    <input id="MAIL_RECIPIENT" placeholder="tu@tuo-dominio.com">

    <h2>Invio · SMTP</h2>
    <div class="row">
      <div><label>Host</label><input id="SMTP_HOST" placeholder="smtp.provider.com"></div>
      <div><label>Porta</label><input id="SMTP_PORT" placeholder="587" inputmode="numeric"></div>
      <div><label>Sicurezza</label>
        <select id="SMTP_SECURITY">
          <option value="">auto (dalla porta)</option>
          <option value="starttls">STARTTLS (587)</option>
          <option value="ssl">SSL/TLS (465)</option>
        </select></div>
    </div>
    <label>Login SMTP</label><input id="SMTP_LOGIN" autocomplete="off">
    <label>Password SMTP</label><input id="SMTP_PASSWORD" type="password" autocomplete="off">
    <div class="actions">
      <button onclick="test('smtp')">Testa SMTP</button>
      <button onclick="test('send')">Invia mail di prova</button>
    </div>

    <h2>Lettura risposte · IMAP <span style="text-transform:none;color:var(--mut)">(opzionale)</span></h2>
    <p class="hint">Serve una casella <b>dedicata a Claude</b> (non la tua posta
      personale) dove instradare le risposte. Puoi lasciarlo vuoto per ora.</p>
    <div class="row">
      <div><label>Host</label><input id="IMAP_HOST" placeholder="imap.gmail.com"></div>
      <div><label>Porta</label><input id="IMAP_PORT" placeholder="993" inputmode="numeric"></div>
    </div>
    <label>Utente IMAP</label><input id="IMAP_USER" autocomplete="off">
    <label>Password IMAP (app password)</label><input id="IMAP_PASSWORD" type="password" autocomplete="off">
    <div class="actions">
      <button onclick="test('imap')">Testa IMAP</button>
    </div>

    <div class="actions" style="margin-top:24px">
      <button class="primary" onclick="save()">Salva configurazione</button>
    </div>
    <div id="status" class="status"></div>
  </div>
</div>
<script>
const FIELDS = ["MAIL_SENDER","MAIL_RECIPIENT","SMTP_HOST","SMTP_PORT","SMTP_SECURITY",
  "SMTP_LOGIN","SMTP_PASSWORD","IMAP_HOST","IMAP_PORT","IMAP_USER","IMAP_PASSWORD"];
const $ = id => document.getElementById(id);
function collect(){ const c={}; for(const f of FIELDS) c[f]=$(f).value.trim(); return c; }
function show(ok,msg){ const s=$("status"); s.className="status "+(ok?"ok":"err"); s.textContent=msg; }
async function api(path,body){
  const r = await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body||{})});
  return r.json();
}
async function load(){
  try{ const d = await (await fetch("/api/load")).json();
    for(const f of FIELDS) if(d[f]!==undefined) $(f).value = d[f];
  }catch(e){}
}
function busy(b){ document.querySelectorAll("button").forEach(x=>x.disabled=b); }
async function test(kind){
  busy(true); show(true,"Verifica in corso…");
  try{
    const map={smtp:"/api/test-smtp",imap:"/api/test-imap",send:"/api/send-test"};
    const d = await api(map[kind], collect());
    show(d.ok, d.message);
  }catch(e){ show(false,"Errore: "+e); } finally{ busy(false); }
}
async function save(){
  busy(true); show(true,"Salvataggio…");
  try{ const d = await api("/api/save", collect()); show(d.ok, d.message); }
  catch(e){ show(false,"Errore: "+e); } finally{ busy(false); }
}
load();
</script>
</body>
</html>
"""


def write_env(cfg: dict[str, str]) -> Path:
    """Scrive il file di configurazione con permessi 0600."""
    path = cm.env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# ClaudeInbox — configurazione email (generato da setup_web.py)",
        "# NON committare questo file. Permessi: chmod 600.",
        "",
        "# --- Invio (SMTP) ---",
    ]
    lines += [f"{k}={cfg.get(k, '').strip()}" for k in cm.SMTP_KEYS]
    lines += ["", "# --- Indirizzi ---"]
    lines += [f"{k}={cfg.get(k, '').strip()}" for k in cm.MAIL_KEYS]
    lines += ["", "# --- Lettura risposte (IMAP, casella DEDICATA a Claude) ---"]
    lines += [f"{k}={cfg.get(k, '').strip()}" for k in cm.IMAP_KEYS]
    content = "\n".join(lines) + "\n"
    # Scrittura atomica con permessi ristretti fin dalla creazione.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(path, 0o600)
    return path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silenzia il logging su stderr
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/load":
            env = cm.load_env()
            self._json({k: env.get(k, "") for k in cm.ALL_KEYS})
        else:
            self._json({"ok": False, "message": "not found"}, 404)

    def do_POST(self):
        cfg = self._read_json()
        try:
            if self.path == "/api/test-smtp":
                ok, msg = cm.verify_smtp(cfg)
            elif self.path == "/api/test-imap":
                ok, msg = cm.verify_imap(cfg)
            elif self.path == "/api/send-test":
                ok, msg = self._send_test(cfg)
            elif self.path == "/api/save":
                ok, msg = self._save(cfg)
            else:
                ok, msg = False, "endpoint sconosciuto"
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, f"Errore: {exc}"
        self._json({"ok": ok, "message": msg})

    def _send_test(self, cfg: dict) -> tuple[bool, str]:
        if not cfg.get("MAIL_RECIPIENT"):
            return False, "Imposta il destinatario prima di inviare la prova."
        cm.send(
            "ClaudeInbox — email di prova",
            "Questa è una mail di prova inviata dal wizard di setup di ClaudeInbox.\n"
            "Se la ricevi, l'invio è configurato correttamente.",
            cfg=cfg,
        )
        return True, f"Mail di prova inviata a {cfg['MAIL_RECIPIENT']}. Controlla la casella."

    def _save(self, cfg: dict) -> tuple[bool, str]:
        if not (cfg.get("SMTP_HOST") and cfg.get("SMTP_LOGIN") and cfg.get("SMTP_PASSWORD")):
            return False, "SMTP host/login/password sono obbligatori per l'invio."
        if not (cfg.get("MAIL_SENDER") and cfg.get("MAIL_RECIPIENT")):
            return False, "Mittente e destinatario sono obbligatori."
        path = write_env(cfg)
        imap_on = bool(cfg.get("IMAP_HOST") and cfg.get("IMAP_USER") and cfg.get("IMAP_PASSWORD"))
        extra = " Lettura risposte IMAP attiva." if imap_on else " (IMAP non configurato: solo invio.)"
        return True, f"Salvato in {path} (chmod 600).{extra}"


def main(argv: list[str]) -> int:
    port = DEFAULT_PORT
    open_browser = True
    i = 0
    while i < len(argv):
        if argv[i] == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1]); i += 2; continue
        if argv[i] == "--no-browser":
            open_browser = False
        i += 1
    url = f"http://{HOST}:{port}"
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"ClaudeInbox setup su {url}  (Ctrl-C per uscire)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChiuso.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
