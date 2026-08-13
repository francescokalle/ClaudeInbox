# ClaudeInbox

Sistema email **globale** di Claude Code per il proprietario di
`francescocallegaro.com`:

- **Invio** — Claude manda resoconti/notifiche da `claude.code@francescocallegaro.com`
  a `mail@francescocallegaro.com`. **Funziona già.**
- **Risposte (bidirezionale)** — quando il proprietario risponde a quelle email,
  Claude legge la risposta, elabora un **ACK breve** di cosa ha capito e, se ha
  **domande**, gliele rimanda via email. *Da attivare* (vedi Setup).

È un progetto **separato e globale**: le sue funzioni sono disponibili da
qualsiasi sessione Claude Code (documentato in `~/.claude/CLAUDE.md`).

## Componenti
- `bin/claude_mail.py` — `send` (Scaleway SMTP) e `fetch` (IMAP, legge le risposte).
- `bin/reply_loop.py` — recupera le nuove risposte e fa elaborare+inviare la
  risposta a Claude (`claude -p`). Da schedulare (cron) quando l'IMAP è configurato.

## Credenziali
Stanno **fuori dal repo**, in `~/.claude/claude-mail.env` (chmod 600):
```
# INVIO (Scaleway TEM) — già impostato
SMTP_HOST=smtp.tem.scaleway.com
SMTP_LOGIN=...
SMTP_PASSWORD=...
MAIL_SENDER=claude.code@francescocallegaro.com
MAIL_RECIPIENT=mail@francescocallegaro.com
# LETTURA (IMAP) — da riempire con una casella DEDICATA
IMAP_HOST=
IMAP_USER=
IMAP_PASSWORD=
```

## Setup della lettura risposte (una tantum)
La lettura NON usa la tua gmail personale (né deve). Serve una **casella dedicata
a Claude**:
1. Crea una casella dedicata (es. una Gmail nuova `claude.inbox.fcallegaro@gmail.com`),
   attiva **IMAP** e genera una **app password**.
2. Su **Cloudflare → Email Routing** instrada
   `claude.code@francescocallegaro.com` → quella casella dedicata.
3. Metti host/utente/app-password in `IMAP_HOST/IMAP_USER/IMAP_PASSWORD` di
   `~/.claude/claude-mail.env` (per Gmail: `IMAP_HOST=imap.gmail.com`).
4. Prova: `python3 bin/claude_mail.py fetch`.

## Attivare il loop automatico (dopo il setup IMAP)
Esegui periodicamente `bin/reply_loop.py` (es. cron ogni 10 min):
```
*/10 * * * * cd ~/Documenti/ClaudeInbox && /usr/bin/python3 bin/reply_loop.py >> /tmp/claudeinbox.log 2>&1
```
Il loop invoca Claude solo se ci sono nuove risposte; Claude si limita a leggere
e rispondere via email (ACK + domande), niente altro.

## Uso manuale
```
python3 bin/claude_mail.py send "Oggetto" "Corpo"
echo "corpo" | python3 bin/claude_mail.py send "Oggetto"
python3 bin/claude_mail.py fetch          # richiede IMAP configurato
```
