#!/usr/bin/env python3
"""Strumento email GLOBALE di Claude Code (disponibile in ogni sessione/progetto).

Invia resoconti/notifiche da claude.code@francescocallegaro.com al proprietario
(mail@francescocallegaro.com) e — se configurata una casella IMAP dedicata —
legge le risposte.

USO
  # invio
  python3 ~/.claude/tools/claude_mail.py send "Oggetto" "Corpo"
  echo "corpo" | python3 ~/.claude/tools/claude_mail.py send "Oggetto"

  # lettura risposte (richiede IMAP_* configurato in ~/.claude/claude-mail.env,
  # su una casella DEDICATA a Claude, non la gmail personale)
  python3 ~/.claude/tools/claude_mail.py fetch [n]

Credenziali: ~/.claude/claude-mail.env (chmod 600, fuori da git).
Quando usarlo: SOLO se l'utente lo chiede o quando lascia un task autonomo /
dice che va via — a fine lavori inviare un resoconto. Non spammare.
"""
from __future__ import annotations

import email
import imaplib
import smtplib
import ssl
import sys
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

ENV = Path.home() / ".claude" / "claude-mail.env"
SMTP_PORT = 587
IMAP_PORT = 993
TIMEOUT = 30


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def send(subject: str, body: str) -> None:
    e = load_env()
    login, pw = e.get("SMTP_LOGIN", ""), e.get("SMTP_PASSWORD", "")
    sender = e.get("MAIL_SENDER", "claude.code@francescocallegaro.com")
    recipient = e.get("MAIL_RECIPIENT", "mail@francescocallegaro.com")
    host = e.get("SMTP_HOST", "smtp.tem.scaleway.com")
    if not (login and pw):
        raise SystemExit(f"Credenziali SMTP mancanti in {ENV}")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"Claude Code <{sender}>"
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    s = smtplib.SMTP(host, SMTP_PORT, timeout=TIMEOUT)
    try:
        s.starttls(context=ssl.create_default_context())
        s.login(login, pw)
        s.sendmail(sender, [recipient], msg.as_string())
    finally:
        try:
            s.quit()
        except Exception:
            pass
    print(f"Email inviata a {recipient}: {subject!r}")


def _decode(v: str | None) -> str:
    if not v:
        return ""
    try:
        return str(make_header(decode_header(v)))
    except Exception:
        return v


def _body_text(m: email.message.Message) -> str:
    if m.is_multipart():
        for part in m.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition", "")
            ):
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace"
                    )
                except Exception:
                    continue
        return ""
    try:
        return m.get_payload(decode=True).decode(m.get_content_charset() or "utf-8", "replace")
    except Exception:
        return str(m.get_payload())


def fetch(limit: int = 5) -> None:
    e = load_env()
    host, user, pw = e.get("IMAP_HOST", ""), e.get("IMAP_USER", ""), e.get("IMAP_PASSWORD", "")
    if not (host and user and pw):
        raise SystemExit(
            "IMAP non configurato. Serve una CASELLA DEDICATA a Claude (non la gmail "
            "personale): imposta IMAP_HOST/IMAP_USER/IMAP_PASSWORD in ~/.claude/claude-mail.env "
            "e instrada claude.code@francescocallegaro.com verso quella casella (Cloudflare Email Routing)."
        )
    M = imaplib.IMAP4_SSL(host, IMAP_PORT)
    try:
        M.login(user, pw)
        M.select("INBOX")
        typ, data = M.search(None, "UNSEEN")
        ids = data[0].split() if data and data[0] else []
        if not ids:
            print("Nessuna nuova risposta.")
            return
        for mid in ids[-limit:]:
            typ, raw = M.fetch(mid, "(RFC822)")
            m = email.message_from_bytes(raw[0][1])
            frm = parseaddr(m.get("From", ""))[1]
            print("=" * 60)
            print(f"Da: {frm}")
            print(f"Oggetto: {_decode(m.get('Subject'))}")
            print(f"Data: {m.get('Date','')}")
            print("-" * 60)
            print(_body_text(m).strip()[:4000])
    finally:
        try:
            M.logout()
        except Exception:
            pass


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("send", "fetch"):
        print(__doc__)
        return 2
    if argv[1] == "send":
        subject = argv[2] if len(argv) >= 3 else "(senza oggetto)"
        body = argv[3] if len(argv) >= 4 else sys.stdin.read()
        send(subject, body.strip() or "(nessun contenuto)")
    else:
        fetch(int(argv[2]) if len(argv) >= 3 else 5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
