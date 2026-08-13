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
    "Sei ClaudeInbox, un risponditore email minimale. Leggi le NUOVE risposte del "
    f"proprietario eseguendo `python3 {MAIL} fetch`. Se non ci sono nuove risposte, "
    "NON inviare nulla e fermati.\n"
    "Per OGNI risposta invia UNA SOLA email, così composta:\n"
    "  (1) un ACK BREVE (1-3 frasi) di cosa hai capito che ti chiede, così capisce "
    "se hai afferrato;\n"
    "  (2) SOLO se necessario, poche domande di chiarimento in elenco.\n"
    "Regole ferree: niente re-incollare l'output o il resoconto del lavoro; niente "
    "spiegazioni lunghe; una email per risposta, il più corta possibile. Meno testo "
    "mandi, meglio è.\n"
    f"Invia con `python3 {MAIL} send \"Re: <oggetto>\" \"<corpo>\" --in-reply-to "
    "\"<Message-ID della risposta letta>\"` (il Message-ID è nell'output di fetch: "
    "serve a tenere la conversazione nello stesso thread). Non fare NIENT'ALTRO."
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
