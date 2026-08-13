#!/usr/bin/env python3
"""ClaudeInbox — loop di risposta.

Recupera le nuove risposte email del proprietario (casella DEDICATA a Claude via
IMAP) e per ciascuna invoca Claude Code headless (`claude -p`) affinché:
  1) elabori un ACK breve di cosa ha capito (così il proprietario capisce),
  2) se ha domande, le includa,
poi lo strumento invia il tutto via email (claude_mail.py send).

Pensato per essere lanciato periodicamente (cron / routine), MA solo dopo aver
configurato la casella IMAP dedicata (vedi README). Se IMAP non è configurato,
esce senza fare nulla.

Uso:
  python3 bin/reply_loop.py            # un giro
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIL = HERE / "claude_mail.py"
ENV = Path.home() / ".claude" / "claude-mail.env"


def imap_ready() -> bool:
    if not ENV.exists():
        return False
    txt = ENV.read_text(encoding="utf-8")
    return all(
        any(line.startswith(k + "=") and line.strip() != k + "=" for line in txt.splitlines())
        for k in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD")
    )


TASK = (
    "Sei ClaudeInbox. Leggi le NUOVE risposte email del proprietario eseguendo "
    f"`python3 {MAIL} fetch`. Per OGNI risposta: (1) scrivi un ACK breve e chiaro di "
    "cosa hai capito che ti chiede (così capisce se hai capito); (2) se hai domande, "
    "elencale in modo conciso. Poi invia il messaggio con "
    f"`python3 {MAIL} send \"Re: <oggetto>\" \"<corpo>\"`. Non fare NIENT'ALTRO: solo "
    "leggere e rispondere via email. Se non ci sono nuove risposte, non inviare nulla."
)


def main() -> int:
    if not imap_ready():
        print(
            "IMAP non configurato: imposta IMAP_HOST/IMAP_USER/IMAP_PASSWORD in "
            f"{ENV} (casella DEDICATA a Claude, non la gmail personale). Vedi README."
        )
        return 0
    if not _has_claude():
        print("CLI `claude` non trovata: impossibile far elaborare la risposta.")
        return 1
    # invoca Claude Code headless per elaborare + inviare
    subprocess.run(["claude", "-p", TASK], check=False)
    return 0


def _has_claude() -> bool:
    from shutil import which

    return which("claude") is not None


if __name__ == "__main__":
    raise SystemExit(main())
