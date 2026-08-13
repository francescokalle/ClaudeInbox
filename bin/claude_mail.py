#!/usr/bin/env python3
"""Strumento email GLOBALE di Claude Code (disponibile in ogni sessione/progetto).

Invia resoconti/notifiche dal mittente configurato al proprietario e — se
configurata una casella IMAP dedicata — legge le risposte. Provider-agnostico:
host, porte, sicurezza e indirizzi vengono tutti dalla config (nessun default
personale nel codice).

USO
  # invio
  python3 bin/claude_mail.py send "Oggetto" "Corpo"
  echo "corpo" | python3 bin/claude_mail.py send "Oggetto"
  python3 bin/claude_mail.py send "Oggetto" "Corpo" --in-reply-to "<msgid>"

  # lettura risposte (richiede IMAP_* configurato, su una casella DEDICATA a
  # Claude, non la posta personale)
  python3 bin/claude_mail.py fetch [n]

Config: ~/.claude/claude-mail.env (chmod 600, fuori da git). Percorso
sovrascrivibile con la variabile d'ambiente CLAUDEINBOX_ENV.
Setup guidato: python3 bin/setup_web.py

Quando usarlo: SOLO se l'utente lo chiede o quando lascia un task autonomo /
dice che va via — a fine lavori inviare un resoconto. Non spammare.
"""
from __future__ import annotations

import email
import imaplib
import mailbox
import os
import smtplib
import ssl
import sys
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

DEFAULT_ENV = Path.home() / ".claude" / "claude-mail.env"
DEFAULT_SMTP_PORT = 587
DEFAULT_IMAP_PORT = 993
DEFAULT_MAILDIR = Path.home() / ".claude" / "claudeinbox-maildir"
TIMEOUT = 30

# Chiavi note del file di configurazione (usate anche dalla web app di setup).
SMTP_KEYS = ("SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_LOGIN", "SMTP_PASSWORD")
MAIL_KEYS = ("MAIL_SENDER", "MAIL_RECIPIENT")
IMAP_KEYS = ("IMAP_HOST", "IMAP_PORT", "IMAP_USER", "IMAP_PASSWORD")
ALL_KEYS = SMTP_KEYS + MAIL_KEYS + IMAP_KEYS


def inbox_backend(cfg: dict[str, str]) -> str:
    """Backend di lettura:
      - 'imap'    : casella IMAP di un gestore esterno (default)
      - 'maildir' : Maildir locale riempito dal ricevitore self-hosted
      - 'http'    : tira le risposte dall'endpoint /pull del ricevitore remoto
    """
    b = (cfg.get("INBOX_BACKEND") or "").strip().lower()
    return b if b in ("imap", "maildir", "http") else "imap"


def maildir_path(cfg: dict[str, str]) -> Path:
    p = (cfg.get("MAILDIR_PATH") or "").strip()
    return Path(p).expanduser() if p else DEFAULT_MAILDIR


def open_maildir(cfg: dict[str, str], create: bool = True) -> mailbox.Maildir:
    return mailbox.Maildir(str(maildir_path(cfg)), factory=None, create=create)


def env_path() -> Path:
    override = os.environ.get("CLAUDEINBOX_ENV")
    return Path(override).expanduser() if override else DEFAULT_ENV


def load_env(path: Path | None = None) -> dict[str, str]:
    path = path or env_path()
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def smtp_security(cfg: dict[str, str]) -> str:
    """'ssl' o 'starttls'. Esplicita se indicata, altrimenti dedotta dalla porta."""
    sec = (cfg.get("SMTP_SECURITY") or "").strip().lower()
    if sec in ("ssl", "starttls"):
        return sec
    return "ssl" if _int(cfg.get("SMTP_PORT", ""), DEFAULT_SMTP_PORT) == 465 else "starttls"


def _open_smtp(cfg: dict[str, str]) -> smtplib.SMTP:
    host = cfg.get("SMTP_HOST", "").strip()
    port = _int(cfg.get("SMTP_PORT", ""), DEFAULT_SMTP_PORT)
    if not host:
        raise ValueError("SMTP_HOST mancante")
    ctx = ssl.create_default_context()
    if smtp_security(cfg) == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=ctx)
    else:
        s = smtplib.SMTP(host, port, timeout=TIMEOUT)
        s.starttls(context=ctx)
    login, pw = cfg.get("SMTP_LOGIN", ""), cfg.get("SMTP_PASSWORD", "")
    if login and pw:
        s.login(login, pw)
    return s


def verify_smtp(cfg: dict[str, str]) -> tuple[bool, str]:
    """Testa host+login SMTP senza inviare. Usato dalla web app di setup."""
    if not (cfg.get("SMTP_HOST") and cfg.get("SMTP_LOGIN") and cfg.get("SMTP_PASSWORD")):
        return False, "Servono SMTP_HOST, SMTP_LOGIN e SMTP_PASSWORD."
    try:
        s = _open_smtp(cfg)
        try:
            s.noop()
        finally:
            _quiet_quit(s)
        return True, f"Login SMTP riuscito su {cfg['SMTP_HOST']} ({smtp_security(cfg)})."
    except Exception as exc:  # noqa: BLE001 — messaggio d'errore leggibile nella UI
        return False, f"SMTP fallito: {exc}"


def verify_imap(cfg: dict[str, str]) -> tuple[bool, str]:
    """Testa host+login IMAP. Usato dalla web app di setup."""
    host = cfg.get("IMAP_HOST", "").strip()
    user, pw = cfg.get("IMAP_USER", ""), cfg.get("IMAP_PASSWORD", "")
    if not (host and user and pw):
        return False, "Servono IMAP_HOST, IMAP_USER e IMAP_PASSWORD."
    port = _int(cfg.get("IMAP_PORT", ""), DEFAULT_IMAP_PORT)
    try:
        M = imaplib.IMAP4_SSL(host, port)
        try:
            M.login(user, pw)
            M.select("INBOX")
        finally:
            _quiet_logout(M)
        return True, f"Login IMAP riuscito su {host}."
    except Exception as exc:  # noqa: BLE001
        return False, f"IMAP fallito: {exc}"


def send(subject: str, body: str, in_reply_to: str | None = None, cfg: dict | None = None) -> None:
    cfg = cfg or load_env()
    sender = cfg.get("MAIL_SENDER", "").strip()
    recipient = cfg.get("MAIL_RECIPIENT", "").strip()
    if not (cfg.get("SMTP_LOGIN") and cfg.get("SMTP_PASSWORD")):
        raise SystemExit(f"Credenziali SMTP mancanti in {env_path()}")
    if not (sender and recipient):
        raise SystemExit(f"MAIL_SENDER/MAIL_RECIPIENT mancanti in {env_path()}")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"Claude Code <{sender}>"
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    s = _open_smtp(cfg)
    try:
        s.sendmail(sender, [recipient], msg.as_string())
    finally:
        _quiet_quit(s)
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
    cfg = load_env()
    backend = inbox_backend(cfg)
    if backend == "maildir":
        _fetch_maildir(limit, cfg)
    elif backend == "http":
        _fetch_http(limit, cfg)
    else:
        _fetch_imap(limit, cfg)


def _fetch_http(limit: int, cfg: dict[str, str]) -> None:
    """Tira le risposte dall'endpoint /pull del ricevitore remoto (via tunnel).
    Il ricevitore le marca come lette. Usato dalla macchina con la CLI `claude`."""
    import json as _json
    import urllib.request

    url = (cfg.get("PULL_URL") or "").strip()
    token = (cfg.get("RECEIVER_TOKEN") or "").strip()
    if not (url and token):
        raise SystemExit(
            "Backend http non configurato: servono PULL_URL e RECEIVER_TOKEN in "
            f"{env_path()}."
        )
    req = urllib.request.Request(
        url, data=b"", method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            # Cloudflare blocca lo UA di default di urllib: usane uno normale.
            "User-Agent": "ClaudeInbox/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        payload = _json.loads(resp.read().decode("utf-8"))
    messages = payload.get("messages", [])
    if not messages:
        print("Nessuna nuova risposta.")
        return
    for m in messages[-limit:]:
        print("=" * 60)
        print(f"Da: {m.get('from','')}")
        print(f"Oggetto: {m.get('subject','')}")
        print(f"Data: {m.get('date','')}")
        print(f"Message-ID: {m.get('message_id','')}")
        print("-" * 60)
        print((m.get("body", "") or "").strip()[:4000])


def _print_message(m: email.message.Message) -> None:
    frm = parseaddr(m.get("From", ""))[1]
    print("=" * 60)
    print(f"Da: {frm}")
    print(f"Oggetto: {_decode(m.get('Subject'))}")
    print(f"Data: {m.get('Date','')}")
    print(f"Message-ID: {m.get('Message-ID','').strip()}")
    print("-" * 60)
    print(_body_text(m).strip()[:4000])


def _fetch_maildir(limit: int, cfg: dict[str, str]) -> None:
    """Legge le mail NON lette dal Maildir locale (ricevitore self-hosted) e le
    marca come lette spostandole da new/ a cur/."""
    md = open_maildir(cfg, create=True)
    unread = [k for k in md.iterkeys() if md.get_message(k).get_subdir() == "new"]
    if not unread:
        print("Nessuna nuova risposta.")
        return
    for key in unread[-limit:]:
        msg = md.get_message(key)
        _print_message(msg)
        # marca come letto: sposta in cur/ con flag Seen
        msg.set_subdir("cur")
        msg.add_flag("S")
        md[key] = msg
    md.flush()


def _fetch_imap(limit: int, cfg: dict[str, str]) -> None:
    host = cfg.get("IMAP_HOST", "").strip()
    user, pw = cfg.get("IMAP_USER", ""), cfg.get("IMAP_PASSWORD", "")
    if not (host and user and pw):
        raise SystemExit(
            "IMAP non configurato. Serve una CASELLA DEDICATA a Claude (non la posta "
            "personale): imposta IMAP_HOST/IMAP_USER/IMAP_PASSWORD in "
            f"{env_path()} e instrada le risposte verso quella casella. "
            "Setup guidato: python3 bin/setup_web.py"
        )
    port = _int(cfg.get("IMAP_PORT", ""), DEFAULT_IMAP_PORT)
    M = imaplib.IMAP4_SSL(host, port)
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
            _print_message(email.message_from_bytes(raw[0][1]))
    finally:
        _quiet_logout(M)


def _quiet_quit(s: smtplib.SMTP) -> None:
    try:
        s.quit()
    except Exception:
        pass


def _quiet_logout(M: imaplib.IMAP4) -> None:
    try:
        M.logout()
    except Exception:
        pass


def _parse_send_args(argv: list[str]) -> tuple[str, str, str | None]:
    """Estrae oggetto, corpo e --in-reply-to dagli argomenti di `send`."""
    in_reply_to = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--in-reply-to" and i + 1 < len(argv):
            in_reply_to = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    subject = rest[0] if len(rest) >= 1 else "(senza oggetto)"
    body = rest[1] if len(rest) >= 2 else sys.stdin.read()
    return subject, body, in_reply_to


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("send", "fetch"):
        print(__doc__)
        return 2
    if argv[1] == "send":
        subject, body, in_reply_to = _parse_send_args(argv[2:])
        send(subject, body.strip() or "(nessun contenuto)", in_reply_to=in_reply_to)
    else:
        fetch(int(argv[2]) if len(argv) >= 3 else 5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
