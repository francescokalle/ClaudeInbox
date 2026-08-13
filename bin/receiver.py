#!/usr/bin/env python3
"""ClaudeInbox — ricevitore HTTP (self-hosted, zero dipendenze).

Riceve le email in ingresso spinte dall'Email Worker Cloudflare (via tunnel
cloudflared) e le salva nel Maildir locale. Da lì `claude_mail.py fetch` (backend
maildir) le legge. Pensato per girare sempre acceso sul server casalingo dietro
CGNAT: NON apre porte verso internet, ascolta solo su 127.0.0.1 e l'esposizione
pubblica la fa il tunnel.

Flusso:
  mittente --SMTP--> Cloudflare Email Routing --> Email Worker --HTTPS POST-->
  inbox.<dominio> (cloudflared) --> questo receiver (127.0.0.1) --> Maildir

Endpoint:
  GET  /health     -> "ok" (per test/monitor)
  POST /incoming   -> body = MIME grezzo (message/rfc822); header
                      Authorization: Bearer <RECEIVER_TOKEN>. Salva in Maildir.
  POST /pull       -> Authorization: Bearer <RECEIVER_TOKEN>. Ritorna le mail non
                      lette come JSON e le marca lette. Lo usa una macchina con la
                      CLI `claude` (es. il laptop) per elaborare e rispondere.

Config (in ~/.claude/claude-mail.env, override con CLAUDEINBOX_ENV):
  RECEIVER_TOKEN   segreto condiviso col Worker (obbligatorio)
  RECEIVER_PORT    porta locale (default 8899)
  MAILDIR_PATH     Maildir di destinazione (default ~/.claude/claudeinbox-maildir)

Uso:
  python3 bin/receiver.py
"""
from __future__ import annotations

import hmac
import json
import mailbox
import sys
from email.utils import parseaddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claude_mail as cm  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8899
MAX_BYTES = 25 * 1024 * 1024  # 25 MB, limite di sicurezza sul corpo


def _token(cfg: dict[str, str]) -> str:
    return (cfg.get("RECEIVER_TOKEN") or "").strip()


def store_message(raw: bytes, cfg: dict[str, str]) -> str:
    """Salva il MIME grezzo nel Maildir (in new/, quindi 'non letto'). Ritorna la key."""
    md = cm.open_maildir(cfg, create=True)
    msg = mailbox.MaildirMessage(raw)
    msg.set_subdir("new")
    return md.add(msg)


def drain_unread(cfg: dict[str, str]) -> list[dict]:
    """Ritorna le mail non lette (subdir new/) come dict e le marca lette."""
    md = cm.open_maildir(cfg, create=True)
    out: list[dict] = []
    for key in list(md.iterkeys()):
        msg = md.get_message(key)
        if msg.get_subdir() != "new":
            continue
        out.append({
            "from": parseaddr(msg.get("From", ""))[1],
            "subject": cm._decode(msg.get("Subject")),
            "date": msg.get("Date", ""),
            "message_id": (msg.get("Message-ID", "") or "").strip(),
            "body": cm._body_text(msg).strip()[:8000],
        })
        msg.set_subdir("cur")
        msg.add_flag("S")
        md[key] = msg
    md.flush()
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # niente log su stderr
        pass

    def _text(self, code: int, body: str) -> None:
        self._send(code, body.encode("utf-8"), "text/plain; charset=utf-8")

    def _send(self, code: int, data: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authed(self, cfg: dict) -> bool:
        want = _token(cfg)
        got = self.headers.get("Authorization", "")
        return bool(want) and got.startswith("Bearer ") and hmac.compare_digest(got[7:], want)

    def do_GET(self):
        if self.path == "/health":
            self._text(200, "ok")
        else:
            self._text(404, "not found")

    def do_POST(self):
        cfg = cm.load_env()
        if not _token(cfg):
            self._text(500, "RECEIVER_TOKEN non configurato")
            return
        if not self._authed(cfg):
            self._text(401, "unauthorized")
            return
        if self.path == "/incoming":
            self._incoming(cfg)
        elif self.path == "/pull":
            self._pull(cfg)
        else:
            self._text(404, "not found")

    def _incoming(self, cfg: dict) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0 or length > MAX_BYTES:
            self._text(413, "corpo mancante o troppo grande")
            return
        raw = self.rfile.read(length)
        try:
            key = store_message(raw, cfg)
        except Exception as exc:  # noqa: BLE001
            self._text(500, f"errore salvataggio: {exc}")
            return
        self._text(200, f"stored {key}")

    def _pull(self, cfg: dict) -> None:
        """Ritorna le mail non lette come JSON e le marca lette."""
        try:
            messages = drain_unread(cfg)
        except Exception as exc:  # noqa: BLE001
            self._text(500, f"errore lettura: {exc}")
            return
        self._send(200, json.dumps({"messages": messages}).encode("utf-8"),
                   "application/json; charset=utf-8")


def main(argv: list[str]) -> int:
    cfg = cm.load_env()
    if not _token(cfg):
        print(
            "RECEIVER_TOKEN mancante in "
            f"{cm.env_path()}: impostane uno (condiviso con il Worker).",
            file=sys.stderr,
        )
        return 1
    port = cm._int(cfg.get("RECEIVER_PORT", ""), DEFAULT_PORT)
    if len(argv) >= 2 and argv[0] == "--port":
        port = int(argv[1])
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"ClaudeInbox receiver in ascolto su http://{HOST}:{port}  "
          f"(Maildir: {cm.maildir_path(cfg)})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChiuso.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
