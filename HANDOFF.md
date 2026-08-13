# HANDOFF — continuazione ClaudeInbox

Istruzioni per **un altro agente** che riprende il lavoro. Obiettivo finale:
il proprietario risponde alle email di Claude → Claude legge, manda un **ACK
breve** di cosa ha capito e, se ha domande, le rimanda via email.

## ✅ Stato attuale (già fatto)
- Progetto creato in `~/Documenti/ClaudeInbox` (repo git dedicato).
- **Invio email FUNZIONANTE**: `bin/claude_mail.py send` via Scaleway TEM
  (da `claude.code@francescocallegaro.com` a `mail@francescocallegaro.com`).
  Testato più volte, arriva.
- **Lettura (`fetch`) e loop (`reply_loop.py`) SCRITTI e pronti**, ma inerti finché
  non è configurata la casella IMAP dedicata.
- Credenziali di invio in `~/.claude/claude-mail.env` (le righe IMAP_* sono vuote).
- Disponibilità globale documentata in `~/.claude/CLAUDE.md`.

## ⛔ Perché non è già completo
Per LEGGERE le risposte serve una casella di posta che Claude possa leggere via
IMAP. **Non si usa la gmail personale dell'utente** (accesso bloccato e giustamente:
è personale e la app-password non era autorizzata a questo scopo). Serve una
**casella DEDICATA a Claude**.

## 👤 Cosa deve fornire l'UTENTE (una tantum)
1. Una **casella dedicata** (es. una Gmail nuova tipo
   `claude.inbox.fcallegaro@gmail.com`) con **IMAP attivo** e una **app password**.
2. Su **Cloudflare → Email Routing**, una regola:
   `claude.code@francescocallegaro.com` → inoltra a quella casella dedicata.
   (Serve perché le risposte dell'utente vanno a `claude.code@`.)
3. Comunicare host/utente/app-password IMAP.

## 🤖 Cosa deve fare L'AGENTE quando ha i dati sopra
1. Compilare in `~/.claude/claude-mail.env`:
   ```
   IMAP_HOST=imap.gmail.com
   IMAP_USER=<casella dedicata>
   IMAP_PASSWORD=<app password, senza spazi>
   ```
   (mantieni chmod 600; NON mettere questi valori nel repo).
2. Testare la lettura:
   ```
   python3 ~/Documenti/ClaudeInbox/bin/claude_mail.py fetch
   ```
   Deve elencare le risposte non lette indirizzate a `claude.code@`.
3. **Test round-trip**: manda una email di prova all'utente
   (`claude_mail.py send "Test" "..."`), fatti rispondere, poi lancia
   `python3 bin/reply_loop.py` e verifica che Claude produca l'ACK + domande e le invii.
4. **Automatizzare**: aggiungi un cron (l'agente può proporlo, l'utente lo conferma):
   ```
   */10 * * * * cd ~/Documenti/ClaudeInbox && /usr/bin/python3 bin/reply_loop.py >> /tmp/claudeinbox.log 2>&1
   ```
   Verifica che il `reply_loop.py` invochi `claude -p` correttamente e che le
   autorizzazioni per cron siano a posto (potrebbe servire configurare i permessi
   dei tool in settings, o eseguire il loop in una modalità non interattiva).
5. Aggiornare questo HANDOFF con lo stato finale.

## Note tecniche
- `reply_loop.py` esce senza fare nulla finché IMAP non è configurato → sicuro da
  schedulare anche prima.
- Il loop fa fare a Claude SOLO ack + domande via email; nessuna altra azione.
- Provenienza credenziali: SMTP Scaleway = fornite dall'utente in chat; IMAP = da
  fornire come sopra. Non riusare credenziali personali non autorizzate.
- Repo GitHub: privato, `francescokalle/ClaudeInbox` (i segreti NON sono nel repo).
