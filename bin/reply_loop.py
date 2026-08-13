#!/usr/bin/env python3
"""ClaudeInbox — loop di risposta.

Controlla se sono arrivate NUOVE risposte del proprietario (backend imap/maildir/
http, secondo la config) e, solo se ce ne sono, invoca Claude Code headless
(`claude -p`) per far inviare UNA email breve: un ACK di cosa ha capito + eventuali
domande. Nient'altro. Se non c'è nuova posta non fa nulla (non spawna Claude).

Va eseguito su una macchina con la CLI `claude` installata.

Uso:
  python3 bin/reply_loop.py              # un giro solo
  python3 bin/reply_loop.py --watch      # ascoltatore: continua a controllare
  python3 bin/reply_loop.py --watch 120  # ...ogni 120 secondi (default 60)
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from shutil import which

HERE = Path(__file__).resolve().parent
MAIL = HERE / "claude_mail.py"

NO_NEW = "Nessuna nuova risposta."

PROMPT_HEAD = (
    "Sei ClaudeInbox, un risponditore email minimale. Qui sotto ci sono le NUOVE "
    "risposte email del proprietario a messaggi che gli avevi mandato. Per OGNI "
    "risposta invia UNA SOLA email così composta:\n"
    "  1) un ACK BREVE (1-3 frasi) di cosa hai capito che ti chiede;\n"
    "  2) SOLO se serve, poche domande di chiarimento in elenco.\n"
    "Regole ferree: niente re-incollare output o resoconti; niente spiegazioni "
    "lunghe; una email per risposta, la più corta possibile.\n"
    f"Invia con: python3 {MAIL} send \"Re: <oggetto>\" \"<corpo>\" --in-reply-to "
    "\"<Message-ID della risposta>\"\n"
    "Non fare NIENT'ALTRO.\n\n"
    "=== NUOVE RISPOSTE ===\n"
)


def _has_claude() -> bool:
    return which("claude") is not None


def one_pass() -> bool:
    """Un giro. Ritorna True se ha elaborato posta nuova."""
    try:
        res = subprocess.run(
            [sys.executable, str(MAIL), "fetch"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"fetch fallito: {exc}", file=sys.stderr)
        return False
    out = (res.stdout or "").strip()
    if not out or out == NO_NEW:
        return False
    prompt = PROMPT_HEAD + out
    subprocess.run(["claude", "-p", prompt], check=False)
    return True


def main(argv: list[str]) -> int:
    if not _has_claude():
        print("CLI `claude` non trovata: impossibile elaborare le risposte.",
              file=sys.stderr)
        return 1
    watch = "--watch" in argv
    interval = 60
    for i, a in enumerate(argv):
        if a == "--watch" and i + 1 < len(argv):
            try:
                interval = max(15, int(argv[i + 1]))
            except ValueError:
                pass
    if not watch:
        one_pass()
        return 0
    print(f"ClaudeInbox in ascolto: controllo ogni {interval}s. Ctrl-C per uscire.")
    try:
        while True:
            if one_pass():
                print("Risposta elaborata e inviata.")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nAscoltatore fermato.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
