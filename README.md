# ClaudeInbox

Canale email **per Claude Code**: permette a Claude di **notificarti** (resoconti a
fine lavori, avvisi quando lo lasci lavorare in autonomia) e di **leggere le tue
risposte** per replicare con un ACK conciso.

È **provider-agnostico** (qualsiasi SMTP/IMAP), **self-hosted** e a **zero
dipendenze** (solo Python 3, nessun `pip install`). La ricezione delle risposte ha
due modi:

- **A — IMAP** verso una casella di un gestore esterno (la via semplice).
- **B — Ricevitore self-hosted** che gira su un tuo server (anche **dietro
  CGNAT**, senza aprire porte) usando un **tunnel cloudflared** + un **Email Worker**
  di Cloudflare. Nessuna casella esterna.

| Comando | Ruolo |
| --- | --- |
| `bin/claude_mail.py send` | Invia notifiche/resoconti (SMTP) |
| `bin/claude_mail.py fetch` | Legge le risposte (backend `imap` o `maildir`) |
| `bin/receiver.py` | Ricevitore HTTP → Maildir (modo B) |
| `bin/reply_loop.py` | Loop: Claude legge e risponde con ACK+domande |
| `bin/setup_web.py` | Wizard di configurazione nel browser |
| `cloudflare/` | Email Worker + config per il modo B |

---

## Setup invio (comune a tutti)

```bash
git clone <questo-repo> ClaudeInbox && cd ClaudeInbox
python3 bin/setup_web.py            # wizard: http://127.0.0.1:8765
```

Inserisci mittente/destinatario e SMTP, premi **Testa SMTP** e **Invia mail di
prova**, poi **Salva** (scrive `~/.claude/claude-mail.env`, `chmod 600`). Da qui in
poi Claude può inviarti notifiche da qualsiasi sessione.

> Alternativa manuale: copia `.env.example` in `~/.claude/claude-mail.env` e
> compilalo.

---

## Ricezione — perché serve un pezzo "sempre acceso"

Ricevere email significa **essere un mail server**: qualcosa di **sempre acceso e
raggiungibile da internet sulla porta 25** deve accettare la posta. Un PC/portatile
o un server dietro **CGNAT** (IP pubblico condiviso, tipico delle linee
residenziali) **non può** farlo: la porta 25 in ingresso non arriva. Per questo si
usa sempre un ricevitore esterno; la differenza è *quale*.

### Modo A — IMAP (gestore esterno)

Il ricevitore è la casella di un provider; ClaudeInbox la legge e basta.

1. Crea una casella **dedicata a Claude** (non la tua personale) con **IMAP** e una
   **app password**.
2. Instrada le risposte a `MAIL_SENDER` verso quella casella (forwarding del
   provider o Cloudflare Email Routing).
3. Nel wizard imposta `INBOX_BACKEND=imap` e i campi `IMAP_*`, premi **Testa IMAP**.

### Modo B — Ricevitore self-hosted dietro CGNAT (tunnel + Worker)

Il ricevitore gira **sul tuo server**, ma l'ingresso pubblico lo fa **Cloudflare**:
riceve la posta come MX (sempre acceso) e la *spinge* al tuo server tramite un
tunnel HTTP in **uscita** (che attraversa il CGNAT).

```
  Mittente ─SMTP─▶ Cloudflare Email Routing ─▶ Email Worker ─HTTPS POST─▶ inbox.tuodominio
   (MX pubblico di Cloudflare, sempre acceso)   (legge il MIME)             │ cloudflared
                                                                            ▼ (tunnel in uscita)
                                              receiver.py (127.0.0.1) ─▶ Maildir ─▶ fetch/loop
```

Nessuna porta aperta sul server, niente porta 25, niente casella esterna.

---

## Guida modo B, passo-passo (esempio reale)

Prerequisiti sul server: Python 3, `cloudflared` **autenticato** (`cloudflared
tunnel login`, crea `~/.cloudflared/cert.pem`), un dominio su Cloudflare con
**Email Routing** attivo, e Node/npm per il deploy del Worker.

### 1. Porta il codice sul server e configura l'env
```bash
# sul server, es. in ~/Documenti/ClaudeInbox
python3 - <<'PY'
import secrets; print("RECEIVER_TOKEN=", secrets.token_urlsafe(32), sep="")
PY
# scrivi ~/.claude/claude-mail.env (chmod 600):
#   INBOX_BACKEND=maildir
#   MAILDIR_PATH=/home/<utente>/.claude/claudeinbox-maildir
#   RECEIVER_PORT=8899
#   RECEIVER_TOKEN=<quello generato sopra>
```

### 2. Avvia il receiver come servizio (systemd)
`/etc/systemd/system/claudeinbox-receiver.service`:
```ini
[Unit]
Description=ClaudeInbox receiver - HTTP to Maildir
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<utente>
Environment=HOME=/home/<utente>
ExecStart=/usr/bin/python3 /home/<utente>/Documenti/ClaudeInbox/bin/receiver.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now claudeinbox-receiver
curl -s http://127.0.0.1:8899/health   # -> ok
```

### 3. Esponi il receiver via tunnel su un subdomain
```bash
# crea il record DNS che punta al tunnel esistente
cloudflared tunnel route dns <TUNNEL_ID> inbox.tuodominio.com
```
Aggiungi al `config.yml` del tunnel (prima del catch-all `http_status:404`):
```yaml
  - hostname: inbox.tuodominio.com
    service: http://localhost:8899
```
```bash
cloudflared --config /etc/cloudflared/config.yml tunnel ingress validate
sudo systemctl restart cloudflared
curl -s https://inbox.tuodominio.com/health   # dall'esterno -> ok
```

### 4. Deploy dell'Email Worker
```bash
cd cloudflare
npx wrangler deploy
npx wrangler secret put RECEIVER_URL     # https://inbox.tuodominio.com/incoming
npx wrangler secret put RECEIVER_TOKEN   # lo stesso RECEIVER_TOKEN del receiver
```
Poi in **Cloudflare → Email → Email Routing → Routing rules**: instrada
l'indirizzo (es. `claude.code@tuodominio.com`) su **Send to a Worker →
claudeinbox-email**.

### 5. Prova end-to-end
Manda una email a `claude.code@tuodominio.com`; deve comparire con:
```bash
python3 bin/claude_mail.py fetch
```

---

## Chi elabora e invia le risposte

`bin/reply_loop.py` legge le nuove risposte e, solo se ce ne sono, invoca Claude
(`claude -p`) per inviare **una** email breve: ACK di cosa ha capito + eventuali
domande, nient'altro. Va eseguito **dove c'è la CLI `claude`**.

Se il ricevitore è su un server senza `claude` (tipico: server sempre acceso solo
per ricevere) e vuoi elaborare da un'altra macchina (es. il laptop), usa il backend
**`http`**: il receiver espone `/pull` e il laptop tira le risposte via tunnel.
Sul laptop, in `~/.claude/claude-mail.env`:
```ini
INBOX_BACKEND=http
PULL_URL=https://inbox.tuodominio.com/pull
RECEIVER_TOKEN=<lo stesso del receiver>
```

Modalità **ascoltatore** (parte quando lasci Claude a lavorare / vai via, resta in
attesa della tua risposta):
```bash
python3 bin/reply_loop.py --watch        # controlla ogni 60s
python3 bin/reply_loop.py --watch 120    # ...ogni 120s
```
Oppure un giro singolo via cron:
```cron
*/10 * * * * cd ~/Documenti/ClaudeInbox && /usr/bin/python3 bin/reply_loop.py >> /tmp/claudeinbox.log 2>&1
```

---

## Configurazione (`~/.claude/claude-mail.env`, chmod 600)

Fuori dal repo. Percorso sovrascrivibile con `CLAUDEINBOX_ENV`. Vedi `.env.example`.

```ini
# Invio (SMTP)
SMTP_HOST=smtp.provider.com
SMTP_PORT=587            # 587=STARTTLS, 465=SSL
SMTP_SECURITY=starttls   # starttls | ssl | (vuoto = dedotto dalla porta)
SMTP_LOGIN=...
SMTP_PASSWORD=...
MAIL_SENDER=claude@tuodominio.com
MAIL_RECIPIENT=tu@tuodominio.com

# Lettura: scegli il backend
INBOX_BACKEND=imap       # imap | maildir

# se imap:
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=...
IMAP_PASSWORD=...

# se maildir (ricevitore self-hosted):
MAILDIR_PATH=~/.claude/claudeinbox-maildir
RECEIVER_PORT=8899
RECEIVER_TOKEN=...        # condiviso col Worker
```

---

## Uso manuale

```bash
python3 bin/claude_mail.py send "Oggetto" "Corpo"
echo "corpo" | python3 bin/claude_mail.py send "Oggetto"      # da stdin
python3 bin/claude_mail.py send "Oggetto" "Corpo" --in-reply-to "<msgid>"
python3 bin/claude_mail.py fetch          # legge le ultime 5 non lette
python3 bin/claude_mail.py fetch 20
```

### Quando Claude invia
Solo se **lo chiedi** o quando lasci un **task autonomo** / dici che vai via: in tal
caso invia un resoconto a fine lavori. **Niente spam.**

---

## Troubleshooting

- **`/health` pubblico non risponde** — verifica `systemctl status cloudflared` e
  che l'ingress del subdomain sia nel `config.yml`; il record DNS deve puntare al
  tunnel.
- **`/incoming` risponde 401** — il `Bearer` del Worker non combacia con
  `RECEIVER_TOKEN`. Riallinea i due valori.
- **`fetch` (maildir) non trova nulla** — controlla che il receiver sia attivo e che
  `MAILDIR_PATH` coincida tra receiver ed env di chi legge.
- **`fetch` (imap) non trova nulla** — legge solo i messaggi **UNSEEN** in `INBOX`.
- **Il server è spento quando arriva la mail** — il Worker riceve un errore dal
  receiver e Cloudflare restituisce un fallimento temporaneo: il mittente **ritenta**
  più tardi, la mail non è persa.

---

## Sicurezza

- Segreti **fuori dal repo** (`~/.claude/claude-mail.env`, `chmod 600`); `.gitignore`
  esclude `.env*`, log e cache.
- Wizard e receiver ascoltano **solo su `127.0.0.1`**; l'esposizione pubblica del
  receiver passa solo dal tunnel e da `/incoming` protetto da token.
- La lettura non usa mai credenziali personali non autorizzate.
